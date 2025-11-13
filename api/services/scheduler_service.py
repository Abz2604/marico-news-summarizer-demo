"""
Scheduler service for campaign email automation.

Uses APScheduler to schedule campaign emails based on schedule_description.
Converts human-readable schedules to cron expressions.
"""

import logging
import asyncio
from typing import List, Optional
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import snowflake.connector

from services import campaigns_service, briefings_service, agent_service, email_service
from services.db import connect
from services.agent_service import get_summaries_for_briefings
from agent.graph import run_agent

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
        logger.info("Scheduler started")
    return _scheduler


def parse_schedule_to_cron(schedule_description: str) -> List[str]:
    """
    Parse human-readable schedule description to cron expressions.
    
    Supported formats:
    - "Daily at 09:00, 17:00" → ["0 9 * * *", "0 17 * * *"]
    - "Weekdays 09:00" → ["0 9 * * 1-5"]
    - "0 9 * * *" → ["0 9 * * *"] (already cron format)
    
    Returns list of cron expressions (one per time).
    """
    if not schedule_description or schedule_description.lower() == "not scheduled":
        return []
    
    schedule = schedule_description.strip()
    
    # If already in cron format, return as-is
    if len(schedule.split()) == 5:
        return [schedule]
    
    cron_expressions = []
    
    # Parse "Daily at 09:00, 17:00" format
    if "daily" in schedule.lower() or "at" in schedule.lower():
        # Extract times
        times = []
        if "at" in schedule.lower():
            # "Daily at 09:00, 17:00"
            time_part = schedule.lower().split("at")[-1].strip()
            times = [t.strip() for t in time_part.split(",")]
        else:
            # "Daily 09:00"
            parts = schedule.lower().replace("daily", "").strip().split(",")
            times = [t.strip() for t in parts]
        
        for time_str in times:
            try:
                hour, minute = time_str.split(":")
                hour = int(hour)
                minute = int(minute)
                cron_expressions.append(f"{minute} {hour} * * *")
            except ValueError:
                logger.warning(f"Could not parse time: {time_str}")
    
    # Parse "Weekdays 09:00" format
    elif "weekday" in schedule.lower():
        time_part = schedule.lower().replace("weekdays", "").replace("weekday", "").strip()
        try:
            hour, minute = time_part.split(":")
            hour = int(hour)
            minute = int(minute)
            cron_expressions.append(f"{minute} {hour} * * 1-5")  # Mon-Fri
        except ValueError:
            logger.warning(f"Could not parse weekday time: {time_part}")
    
    # Parse "Monday 09:00" format (single day)
    elif any(day in schedule.lower() for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
        day_map = {
            "monday": "1", "tuesday": "2", "wednesday": "3", "thursday": "4",
            "friday": "5", "saturday": "6", "sunday": "0"
        }
        day_name = None
        for d, num in day_map.items():
            if d in schedule.lower():
                day_name = num
                break
        
        time_part = schedule.lower()
        for d in day_map.keys():
            time_part = time_part.replace(d, "").strip()
        
        try:
            hour, minute = time_part.split(":")
            hour = int(hour)
            minute = int(minute)
            cron_expressions.append(f"{minute} {hour} * * {day_name}")
        except ValueError:
            logger.warning(f"Could not parse day-specific time: {time_part}")
    
    return cron_expressions


async def _run_briefing_and_wait(
    briefing_id: str,
    run_id: str,
    prompt: str,
    seed_links: List[str]
) -> tuple[str, bool, Optional[str]]:
    """
    Run a briefing and wait for completion.
    
    Returns: (briefing_id, success, error_message)
    """
    from services.db import connect
    import asyncio
    
    logger.info(f"[run_id={run_id}] Starting briefing run for {briefing_id}")
    
    try:
        # Run agent (async)
        result = await run_agent(
            prompt=prompt,
            seed_links=seed_links,
            max_articles=10
        )
        
        # Use connection for database operations
        with connect() as conn:
            if not result:
                agent_service.mark_run_as_failed(run_id, "Agent returned no result", conn=conn)
                return (briefing_id, False, "Agent returned no result")
            
            # Save the summary
            agent_service.save_summary_and_finalize_run(
                run_id=run_id,
                briefing_id=briefing_id,
                summary_markdown=result.summary_markdown,
                bullet_points=result.bullet_points,
                citations=result.citations,
                model=result.model,
                conn=conn
            )
            
            # Update briefing's last_run_at timestamp
            briefings_service.update_briefing_last_run(briefing_id, conn=conn)
            
            logger.info(f"[run_id={run_id}] ✅ Briefing {briefing_id} completed successfully")
            return (briefing_id, True, None)
            
    except Exception as e:
        logger.exception(f"[run_id={run_id}] ❌ Error running briefing {briefing_id}: {e}")
        try:
            with connect() as conn:
                agent_service.mark_run_as_failed(run_id, str(e), conn=conn)
        except Exception as db_error:
            logger.error(f"[run_id={run_id}] Failed to mark run as failed: {db_error}")
        return (briefing_id, False, str(e))


async def _execute_scheduled_campaign(campaign_id: str):
    """
    Execute a scheduled campaign:
    1. Run all briefings in parallel
    2. Wait for all to complete
    3. Collect summaries
    4. Send email with results
    """
    logger.info(f"[campaign_id={campaign_id}] Starting scheduled campaign execution")
    
    try:
        # Get campaign
        with connect() as conn:
            campaign = campaigns_service.get_campaign_by_id(campaign_id, conn=conn)
            if not campaign:
                logger.error(f"[campaign_id={campaign_id}] Campaign not found")
                return
            
            # Check if campaign is still active
            if campaign.status != "active":
                logger.info(f"[campaign_id={campaign_id}] Campaign is {campaign.status}, skipping")
                return
            
            logger.info(f"[campaign_id={campaign_id}] Running {len(campaign.briefing_ids)} briefings...")
            
            # Prepare briefing tasks (create run records first)
            briefing_tasks = []
            for briefing_id in campaign.briefing_ids:
                briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
                if not briefing:
                    logger.warning(f"[campaign_id={campaign_id}] Briefing {briefing_id} not found")
                    continue
                
                # Create run record
                run_record = agent_service.create_agent_run(
                    briefing_id=briefing_id,
                    trigger_type="scheduled",
                    conn=conn
                )
                
                # Create task to run briefing
                task = _run_briefing_and_wait(
                    briefing_id=briefing_id,
                    run_id=run_record.id,
                    prompt=briefing.prompt,
                    seed_links=[str(link) for link in briefing.primary_links]
                )
                briefing_tasks.append(task)
        
        # Wait for all briefings to complete (outside connection context)
        if briefing_tasks:
            results = await asyncio.gather(*briefing_tasks, return_exceptions=True)
        else:
            results = []
        
        # Process results
        successful_briefing_ids = []
        failed_briefings = []
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[campaign_id={campaign_id}] Briefing task raised exception: {result}")
                continue
            
            briefing_id, success, error_msg = result
            if success:
                successful_briefing_ids.append(briefing_id)
            else:
                # Get briefing name for error message
                with connect() as conn:
                    briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
                    if briefing:
                        failed_briefings.append((briefing.name, error_msg))
        
        logger.info(
            f"[campaign_id={campaign_id}] Briefings completed: "
            f"{len(successful_briefing_ids)} successful, {len(failed_briefings)} failed"
        )
        
        # Get summaries for successful briefings
        with connect() as conn:
            summaries_map = get_summaries_for_briefings(successful_briefing_ids, conn=conn)
            
            # Build summaries list with briefing names
            summaries_with_names = []
            for briefing_id in successful_briefing_ids:
                briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
                if not briefing:
                    continue
                
                summary = summaries_map.get(briefing_id)
                if summary:
                    summaries_with_names.append((briefing.name, summary))
        
        # Render and send email (outside connection context)
        from routers.campaigns import _render_summaries_to_html
        
        html_content = _render_summaries_to_html(
            campaign_name=campaign.name,
            summaries=summaries_with_names,
            missing_briefings=[name for name, _ in failed_briefings] if failed_briefings else None,
            failed_briefings=failed_briefings  # Pass failed briefings with error messages
        )
        
        subject = f"{campaign.name} - {datetime.now().strftime('%B %d, %Y')}"
        recipient_emails = campaign.recipient_emails
        
        if recipient_emails:
            email_service.send_email(
                recipient_emails=recipient_emails,
                subject=subject,
                html_content=html_content
            )
            logger.info(
                f"[campaign_id={campaign_id}] ✅ Email sent to {len(recipient_emails)} recipients. "
                f"Included {len(summaries_with_names)} summaries, {len(failed_briefings)} failed."
            )
        else:
            logger.warning(f"[campaign_id={campaign_id}] No recipient emails configured")
                
    except Exception as e:
        logger.exception(f"[campaign_id={campaign_id}] ❌ Error executing scheduled campaign: {e}")


def schedule_campaign(campaign_id: str, schedule_description: str):
    """
    Schedule a campaign based on its schedule_description.
    Creates one job per time in the schedule.
    """
    scheduler = get_scheduler()
    
    # Remove existing jobs for this campaign
    unschedule_campaign(campaign_id)
    
    # Parse schedule to cron expressions
    cron_expressions = parse_schedule_to_cron(schedule_description)
    
    if not cron_expressions:
        logger.info(f"[campaign_id={campaign_id}] No schedule to parse, skipping")
        return
    
    # Create one job per cron expression
    for idx, cron_expr in enumerate(cron_expressions):
        job_id = f"campaign_{campaign_id}_{idx}"
        try:
            scheduler.add_job(
                _execute_scheduled_campaign,
                trigger=CronTrigger.from_crontab(cron_expr),
                args=[campaign_id],
                id=job_id,
                replace_existing=True,
                max_instances=1,  # Prevent duplicate executions
            )
            logger.info(f"[campaign_id={campaign_id}] Scheduled job {job_id} with cron: {cron_expr}")
        except Exception as e:
            logger.error(f"[campaign_id={campaign_id}] Failed to schedule job: {e}")


def unschedule_campaign(campaign_id: str):
    """Remove all scheduled jobs for a campaign."""
    scheduler = get_scheduler()
    
    # Find and remove all jobs for this campaign
    jobs_to_remove = [
        job.id for job in scheduler.get_jobs()
        if job.id.startswith(f"campaign_{campaign_id}_")
    ]
    
    for job_id in jobs_to_remove:
        try:
            scheduler.remove_job(job_id)
            logger.info(f"[campaign_id={campaign_id}] Removed scheduled job {job_id}")
        except Exception as e:
            logger.warning(f"[campaign_id={campaign_id}] Failed to remove job {job_id}: {e}")


def reload_all_campaigns():
    """Reload all active campaigns from database and schedule them."""
    logger.info("Reloading all campaigns from database...")
    
    try:
        with connect() as conn:
            campaigns = campaigns_service.list_campaigns(limit=100, conn=conn)
            
            active_count = 0
            for campaign in campaigns:
                if campaign.status == "active" and campaign.schedule_description:
                    schedule_campaign(campaign.id, campaign.schedule_description)
                    active_count += 1
            
            logger.info(f"Reloaded {active_count} active campaigns with schedules")
    except Exception as e:
        logger.exception(f"Failed to reload campaigns: {e}")

