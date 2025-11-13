from __future__ import annotations

import markdown
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import snowflake.connector

from services import campaigns_service, email_service, briefings_service
from services.db import get_db_connection
from services.agent_service import (
    Summary, 
    get_summaries_for_briefings, 
    get_briefing_summary_status
)
from agent.graph import run_agent
from dependencies import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignOut(BaseModel):
    id: str
    user_id: str
    name: str
    status: str
    description: Optional[str]
    briefing_ids: List[str]
    recipient_emails: List[str]
    schedule_description: Optional[str]
    created_at: datetime
    updated_at: datetime


class BriefingStatus(BaseModel):
    """Status of a briefing for campaign preview."""
    id: str
    name: str
    summary_exists: bool
    last_run_at: Optional[datetime]
    summary_age_hours: Optional[float]


class CampaignPreviewResponse(BaseModel):
    """Response for campaign preview endpoint."""
    status: str  # 'ready', 'partial', 'not_ready'
    html: Optional[str]
    campaign: dict
    briefings: List[BriefingStatus]
    message: Optional[str]
    missing_briefing_ids: List[str]
    actions: dict


def _render_summaries_to_html(
    campaign_name: str, 
    summaries: List[tuple[str, Summary]],  # (briefing_name, summary)
    missing_briefings: List[str] = None,
    failed_briefings: List[tuple[str, str]] = None  # (briefing_name, error_message)
) -> str:
    """Renders multiple summaries into a formatted HTML email."""
    missing_briefings = missing_briefings or []
    
    # Build sections for each summary
    sections_html = ""
    for briefing_name, summary in summaries:
        html_body = markdown.markdown(summary.summary_markdown)
        
        # Format bullet points if available
        bullets_html = ""
        if summary.bullet_points:
            bullets_html = "<div style='margin-top: 20px;'><h4 style='color: #333; font-size: 1.1em; font-weight: 600; margin-bottom: 12px;'>Key Points:</h4><ul style='margin: 0; padding-left: 30px;'>" + "".join(
                f"<li style='color: #555; line-height: 1.7; margin: 8px 0;'>{bp}</li>" for bp in summary.bullet_points
            ) + "</ul></div>"
        
        # Format citations
        citations_html = ""
        if summary.citations:
            citations_html = "<div style='margin-top: 15px; font-size: 0.9em;'>"
            citations_html += "<strong>Sources:</strong><br>"
            citations_html += " • ".join([
                f"<a href=\"{c['url']}\" style='color: #0066cc;'>{c.get('label', c['url'])}</a>"
                for c in summary.citations
            ])
            citations_html += "</div>"
        
        sections_html += f"""
        <div style="margin-bottom: 40px; border-bottom: 1px solid #e0e0e0; padding-bottom: 30px;">
            <h2 style="color: #0066cc; font-size: 1.8em; margin-bottom: 20px; font-weight: 700;">{briefing_name}</h2>
            <div class="markdown-content">
                {html_body}
            </div>
            {bullets_html if bullets_html else ''}
            {citations_html}
        </div>
        """
    
    # Add warning for missing briefings
    missing_html = ""
    if missing_briefings:
        missing_list = ", ".join(missing_briefings)
        missing_html = f"""
        <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 30px;">
            <strong>⚠️ Incomplete Preview:</strong> The following briefings haven't been run yet: {missing_list}
        </div>
        """
    
    # Add warning for failed briefings (from scheduled runs)
    failed_html = ""
    if failed_briefings:
        failed_items = []
        for briefing_name, error_msg in failed_briefings:
            failed_items.append(f"<li><strong>{briefing_name}</strong>: {error_msg}</li>")
        failed_list = "".join(failed_items)
        failed_html = f"""
        <div style="background-color: #f8d7da; border-left: 4px solid #dc3545; padding: 15px; margin-bottom: 30px;">
            <strong>⚠️ No Summary Extracted:</strong> The following briefings failed during this run. Please check your briefing configuration.
            <ul style="margin: 10px 0 0 20px; padding-left: 20px;">
                {failed_list}
            </ul>
        </div>
        """
    
    # Complete HTML template with comprehensive styling
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{campaign_name}</title>
        <style>
            /* Markdown content styling */
            .markdown-content h1 {{
                font-size: 1.8em;
                font-weight: 700;
                color: #1a1a1a;
                margin: 24px 0 16px 0;
                line-height: 1.3;
                border-bottom: 2px solid #e0e0e0;
                padding-bottom: 8px;
            }}
            
            .markdown-content h2 {{
                font-size: 1.5em;
                font-weight: 700;
                color: #2a2a2a;
                margin: 20px 0 14px 0;
                line-height: 1.4;
            }}
            
            .markdown-content h3 {{
                font-size: 1.3em;
                font-weight: 600;
                color: #333;
                margin: 18px 0 12px 0;
                line-height: 1.4;
            }}
            
            .markdown-content h4 {{
                font-size: 1.1em;
                font-weight: 600;
                color: #444;
                margin: 16px 0 10px 0;
                line-height: 1.5;
            }}
            
            .markdown-content p {{
                font-size: 1em;
                color: #555;
                line-height: 1.7;
                margin: 0 0 16px 0;
            }}
            
            .markdown-content ul, .markdown-content ol {{
                margin: 16px 0;
                padding-left: 30px;
            }}
            
            .markdown-content li {{
                font-size: 1em;
                color: #555;
                line-height: 1.7;
                margin: 8px 0;
            }}
            
            .markdown-content strong {{
                font-weight: 600;
                color: #333;
            }}
            
            .markdown-content em {{
                font-style: italic;
                color: #666;
            }}
            
            .markdown-content code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
                color: #d63384;
            }}
            
            .markdown-content pre {{
                background-color: #f4f4f4;
                padding: 16px;
                border-radius: 6px;
                overflow-x: auto;
                margin: 16px 0;
            }}
            
            .markdown-content blockquote {{
                border-left: 4px solid #0066cc;
                padding-left: 16px;
                margin: 16px 0;
                color: #666;
                font-style: italic;
            }}
            
            .markdown-content a {{
                color: #0066cc;
                text-decoration: none;
            }}
            
            .markdown-content a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
                 margin: 0; padding: 5px; background-color: #f8f9fa;">
        <div style="background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
                    max-width: 900px; margin: 0 auto;">
            <div style="border-bottom: 3px solid #0066cc; padding-bottom: 20px; margin-bottom: 30px;">
                <h1 style="color: #0066cc; margin: 0; font-size: 2em;">{campaign_name}</h1>
                <p style="color: #666; margin: 10px 0 0 0;">{datetime.now().strftime('%B %d, %Y')}</p>
            </div>
            
            {missing_html}
            {failed_html}
            {sections_html}
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0; 
                        text-align: center; color: #999; font-size: 0.85em;">
                <p>Generated by Marico News Summarizer</p>
            </div>
        </div>
        </body>
    </html>
    """
    return html


class CampaignCreate(BaseModel):
    """Request body for creating a campaign."""
    name: str
    description: Optional[str] = None
    briefing_ids: List[str]
    recipient_emails: List[str]
    schedule_description: Optional[str] = None
    status: str = "active"


@router.post("", status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> CampaignOut:
    """Creates a new campaign."""
    try:
        campaign = campaigns_service.create_campaign(
            name=payload.name,
            description=payload.description,
            briefing_ids=payload.briefing_ids,
            recipient_emails=payload.recipient_emails,
            schedule_description=payload.schedule_description,
            status=payload.status,
            user_id=current_user["id"],
            conn=conn
        )
        
        # Schedule the campaign if it's active and has a schedule
        if campaign.status == "active" and campaign.schedule_description:
            from services.scheduler_service import schedule_campaign
            schedule_campaign(campaign.id, campaign.schedule_description)
        
        return CampaignOut(
            id=campaign.id,
            user_id=campaign.user_id,
            name=campaign.name,
            status=campaign.status,
            description=campaign.description,
            briefing_ids=campaign.briefing_ids,
            recipient_emails=campaign.recipient_emails,
            schedule_description=campaign.schedule_description,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )
    except Exception as e:
        logger.exception(f"Failed to create campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {str(e)}")


@router.get("")
async def list_campaigns(
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> dict:
    campaigns_list = campaigns_service.list_campaigns(user_id=current_user["id"], conn=conn)
    items = [
        CampaignOut(
            id=c.id,
            user_id=c.user_id,
            name=c.name,
            status=c.status,
            description=c.description,
            briefing_ids=c.briefing_ids,
            recipient_emails=c.recipient_emails,
            schedule_description=c.schedule_description,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in campaigns_list
    ]
    return {"items": items}


@router.get("/{campaign_id}/preview")
async def preview_campaign_email(
    campaign_id: str,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """
    Smart preview endpoint that checks summary status and returns structured data.
    Frontend can decide how to handle different states (ready/partial/not_ready).
    """
    # Get campaign (filtered by user)
    campaign = campaigns_service.get_campaign_by_id(campaign_id, user_id=current_user["id"], conn=conn)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get all briefings for this campaign
    briefing_ids = campaign.briefing_ids
    if not briefing_ids:
        return CampaignPreviewResponse(
            status="not_ready",
            html=None,
            campaign={"id": campaign.id, "name": campaign.name, "subject": campaign.name},
            briefings=[],
            message="Campaign has no briefings assigned",
            missing_briefing_ids=[],
            actions={}
        )
    
    # Get summaries for all briefings
    summaries_map = get_summaries_for_briefings(briefing_ids, conn=conn)
    
    # Build briefing status list and collect data
    briefing_statuses = []
    missing_briefing_ids = []
    summaries_with_names = []
    missing_names = []
    
    for briefing_id in briefing_ids:
        # Get briefing details
        briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
        if not briefing:
            logger.warning(f"Briefing {briefing_id} not found in campaign {campaign_id}")
            continue
        
        # Get status
        status_info = get_briefing_summary_status(briefing_id, conn=conn)
        summary = summaries_map.get(briefing_id)
        
        briefing_statuses.append(BriefingStatus(
            id=briefing_id,
            name=briefing.name,
            summary_exists=summary is not None,
            last_run_at=status_info.get('last_run_at'),
            summary_age_hours=status_info.get('age_hours')
        ))
        
        if summary:
            summaries_with_names.append((briefing.name, summary))
        else:
            missing_briefing_ids.append(briefing_id)
            missing_names.append(briefing.name)
    
    # Determine overall status
    total_briefings = len(briefing_ids)
    missing_count = len(missing_briefing_ids)
    
    if missing_count == total_briefings:
        # No summaries at all
        status = "not_ready"
        html = None
        message = "No briefings have been run yet. Please run the briefings to generate content."
    elif missing_count > 0:
        # Some summaries missing
        status = "partial"
        html = _render_summaries_to_html(
            campaign_name=campaign.name,
            summaries=summaries_with_names,
            missing_briefings=missing_names
        )
        message = f"{missing_count} of {total_briefings} briefings haven't been run yet"
    else:
        # All summaries present
        status = "ready"
        html = _render_summaries_to_html(
            campaign_name=campaign.name,
            summaries=summaries_with_names
        )
        message = None
    
    # Build action URLs
    actions = {
        "run_missing_url": f"/api/campaigns/{campaign_id}/run-missing",
        "run_individual_urls": {
            bid: f"/api/briefings/{bid}/run" for bid in missing_briefing_ids
        }
    }
    
    return CampaignPreviewResponse(
        status=status,
        html=html,
        campaign={
            "id": campaign.id,
            "name": campaign.name,
            "subject": f"{campaign.name} - {datetime.now().strftime('%B %d, %Y')}"
        },
        briefings=briefing_statuses,
        message=message,
        missing_briefing_ids=missing_briefing_ids,
        actions=actions
    )


@router.post("/{campaign_id}/run-missing")
async def run_missing_briefings(
    campaign_id: str, 
    background_tasks: BackgroundTasks,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """
    Helper endpoint to run all briefings that don't have summaries yet.
    Useful for "Run All Missing" button in UI.
    """
    # Get campaign (filtered by user)
    campaign = campaigns_service.get_campaign_by_id(campaign_id, user_id=current_user["id"], conn=conn)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get summaries to find missing ones
    summaries_map = get_summaries_for_briefings(campaign.briefing_ids, conn=conn)
    missing_briefing_ids = [
        bid for bid in campaign.briefing_ids 
        if summaries_map.get(bid) is None
    ]
    
    if not missing_briefing_ids:
        return {
            "message": "All briefings already have summaries",
            "run_ids": [],
            "briefing_ids": []
        }
    
    # Trigger runs for missing briefings (in background to avoid timeout)
    from services import agent_service
    
    run_ids = []
    for briefing_id in missing_briefing_ids:
        briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
        if not briefing:
            continue
        
        # Create run record
        run_record = agent_service.create_agent_run(briefing_id, trigger_type="campaign_preview", conn=conn)
        run_ids.append(run_record.id)
        
        # Queue the actual agent run
        background_tasks.add_task(
            _run_agent_for_briefing_background,
            briefing_id=briefing_id,
            run_id=run_record.id
        )
    
    return {
        "message": f"Started {len(run_ids)} agent runs",
        "run_ids": run_ids,
        "briefing_ids": missing_briefing_ids,
        "estimated_completion_seconds": len(run_ids) * 60  # Rough estimate
    }


async def _run_agent_for_briefing_background(briefing_id: str, run_id: str):
    """Background task to run agent for a briefing."""
    try:
        briefing = briefings_service.get_briefing_by_id(briefing_id)
        if not briefing:
            logger.error(f"Briefing {briefing_id} not found")
            return
        
        # Run agent
        result = await run_agent(
            prompt=briefing.prompt,
            seed_links=[str(url) for url in briefing.primary_links],
            max_articles=10
        )
        
        if not result:
            logger.error(f"Agent run for briefing {briefing_id} returned no result")
            return
        
        # Save summary
        from services import agent_service
        agent_service.save_summary_and_finalize_run(
            run_id=run_id,
            briefing_id=briefing_id,
            summary_markdown=result.summary_markdown,
            bullet_points=result.bullet_points,
            citations=result.citations,
            model=result.model
        )
        
        logger.info(f"Successfully completed agent run for briefing {briefing_id}")
        
    except Exception as e:
        logger.exception(f"Error running agent for briefing {briefing_id}: {e}")


@router.post("/{campaign_id}/send")
async def send_campaign_email(
    campaign_id: str, 
    background_tasks: BackgroundTasks,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """
    Send campaign email to all recipients.
    Uses the latest summaries from all briefings in the campaign.
    """
    # Get campaign (filtered by user)
    campaign = campaigns_service.get_campaign_by_id(campaign_id, user_id=current_user["id"], conn=conn)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get all summaries
    summaries_map = get_summaries_for_briefings(campaign.briefing_ids, conn=conn)
    
    # Build summaries list with briefing names
    summaries_with_names = []
    missing_names = []
    
    for briefing_id in campaign.briefing_ids:
        briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
        if not briefing:
            continue
        
        summary = summaries_map.get(briefing_id)
        if summary:
            summaries_with_names.append((briefing.name, summary))
        else:
            missing_names.append(briefing.name)
    
    if not summaries_with_names:
        raise HTTPException(
            status_code=422, 
            detail="No summaries available. Please run the briefings first."
        )
    
    # Render email HTML
    html_content = _render_summaries_to_html(
        campaign_name=campaign.name,
        summaries=summaries_with_names,
        missing_briefings=missing_names if missing_names else None
    )
    
    # Prepare email
    subject = f"{campaign.name} - {datetime.now().strftime('%B %d, %Y')}"
    recipient_emails = campaign.recipient_emails
    
    if not recipient_emails:
        raise HTTPException(status_code=422, detail="Campaign has no recipient emails")
    
    # Send email in background
    background_tasks.add_task(
        email_service.send_email,
        recipient_emails=recipient_emails,
        subject=subject,
        html_content=html_content
    )
    
    return {
        "message": "Campaign email has been queued for sending",
        "recipients": recipient_emails,
        "subject": subject,
        "briefings_included": len(summaries_with_names),
        "briefings_missing": len(missing_names)
    }


class SendPreviewRequest(BaseModel):
    """Request body for sending preview email."""
    preview_email: str


@router.post("/{campaign_id}/send-preview")
async def send_preview_email(
    campaign_id: str, 
    payload: SendPreviewRequest, 
    background_tasks: BackgroundTasks,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """
    Send a preview email to a specific address.
    Uses the same email template as the actual campaign send.
    """
    # Get campaign (filtered by user)
    campaign = campaigns_service.get_campaign_by_id(campaign_id, user_id=current_user["id"], conn=conn)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get all summaries
    summaries_map = get_summaries_for_briefings(campaign.briefing_ids, conn=conn)
    
    # Build summaries list with briefing names
    summaries_with_names = []
    missing_names = []
    
    for briefing_id in campaign.briefing_ids:
        briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
        if not briefing:
            continue
        
        summary = summaries_map.get(briefing_id)
        if summary:
            summaries_with_names.append((briefing.name, summary))
        else:
            missing_names.append(briefing.name)
    
    if not summaries_with_names:
        raise HTTPException(
            status_code=422, 
            detail="No summaries available. Please run the briefings first."
        )
    
    # Render email HTML
    html_content = _render_summaries_to_html(
        campaign_name=f"{campaign.name} (PREVIEW)",
        summaries=summaries_with_names,
        missing_briefings=missing_names if missing_names else None
    )
    
    # Prepare email
    subject = f"[PREVIEW] {campaign.name} - {datetime.now().strftime('%B %d, %Y')}"
    
    # Send email in background
    background_tasks.add_task(
        email_service.send_email,
        recipient_emails=[payload.preview_email],
        subject=subject,
        html_content=html_content
    )
    
    return {
        "message": "Preview email has been queued for sending",
        "recipient": payload.preview_email,
        "subject": subject,
        "briefings_included": len(summaries_with_names),
        "briefings_missing": len(missing_names)
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> CampaignOut:
    """Gets a single campaign by ID."""
    campaign = campaigns_service.get_campaign_by_id(campaign_id, user_id=current_user["id"], conn=conn)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return CampaignOut(
        id=campaign.id,
        user_id=campaign.user_id,
        name=campaign.name,
        status=campaign.status,
        description=campaign.description,
        briefing_ids=campaign.briefing_ids,
        recipient_emails=campaign.recipient_emails,
        schedule_description=campaign.schedule_description,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


class CampaignUpdate(BaseModel):
    """Request body for updating a campaign."""
    name: Optional[str] = None
    description: Optional[str] = None
    briefing_ids: Optional[List[str]] = None
    recipient_emails: Optional[List[str]] = None
    schedule_description: Optional[str] = None
    status: Optional[str] = None


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> CampaignOut:
    """Updates a campaign."""
    campaign = campaigns_service.update_campaign(
        campaign_id=campaign_id,
        user_id=current_user["id"],
        name=payload.name,
        description=payload.description,
        briefing_ids=payload.briefing_ids,
        recipient_emails=payload.recipient_emails,
        schedule_description=payload.schedule_description,
        status=payload.status,
        conn=conn
    )
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Update scheduler: remove old jobs, add new ones if active
    from services.scheduler_service import schedule_campaign, unschedule_campaign
    
    unschedule_campaign(campaign_id)
    if campaign.status == "active" and campaign.schedule_description:
        schedule_campaign(campaign.id, campaign.schedule_description)
    
    return CampaignOut(
        id=campaign.id,
        user_id=campaign.user_id,
        name=campaign.name,
        status=campaign.status,
        description=campaign.description,
        briefing_ids=campaign.briefing_ids,
        recipient_emails=campaign.recipient_emails,
        schedule_description=campaign.schedule_description,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """Deletes a campaign."""
    deleted = campaigns_service.delete_campaign(campaign_id, user_id=current_user["id"], conn=conn)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Remove scheduled jobs
    from services.scheduler_service import unschedule_campaign
    unschedule_campaign(campaign_id)
    
    return {"message": "Campaign deleted successfully"}


