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
from agent_v2.agent_v2 import AgentV2
from agent_v2.types import AgentV2Request, PageType

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
    - "Weekdays at 09:00" → ["0 9 * * 1-5"]
    - "Weekly on Monday at 09:00" → ["0 9 * * 1"]
    - "Weekly on Mon, Wed at 09:00" → ["0 9 * * 1,3"]
    - "Monthly on day 1 at 09:00" → ["0 9 1 * *"]
    - "Monthly on the first Monday at 09:00" (Complex, might need specialized handling or limitation) -> For MVP, sticking to specific days of month.
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
    
    # Split by " & " to handle multiple schedules combined
    schedule_parts = [s.strip() for s in schedule.split(" & ")]
    
    for part in schedule_parts:
        try:
            # Extract time part first (always at the end or after "at")
            if " at " in part.lower():
                time_part = part.lower().split(" at ")[-1].strip()
                schedule_base = part.lower().split(" at ")[0].strip()
            else:
                # Assume the last part is time if no "at" (e.g. "Daily 09:00")
                parts = part.split()
                time_part = parts[-1]
                schedule_base = " ".join(parts[:-1]).lower()

            # Handle multiple times "09:00, 17:00"
            times = [t.strip() for t in time_part.split(",")]
            
            for time_str in times:
            hour, minute = time_str.split(":")
            hour = int(hour)
            minute = int(minute)
                
                if "daily" in schedule_base:
                    cron_expressions.append(f"{minute} {hour} * * *")
                    
                elif "weekday" in schedule_base: # "Weekdays" or "Weekday"
                    cron_expressions.append(f"{minute} {hour} * * 1-5")
                    
                elif "weekly on" in schedule_base:
                    # "Weekly on Mon, Wed"
                    days_part = schedule_base.replace("weekly on", "").strip()
            
            day_map = {
                "monday": "0", "mon": "0",
                "tuesday": "1", "tue": "1",
                "wednesday": "2", "wed": "2",
                "thursday": "3", "thu": "3",
                "friday": "4", "fri": "4",
                "saturday": "5", "sat": "5",
                "sunday": "6", "sun": "6"
            }
            
                    selected_days = []
                    # Handle comma separated days
                    raw_days = [d.strip() for d in days_part.split(",")]
                    for d in raw_days:
                        for name, val in day_map.items():
                            if name == d or name in d: # Simple match
                                 if val not in selected_days:
                                    selected_days.append(val)
                                    break # Matched this raw day
                    
                    if selected_days:
                        # Map back to APScheduler/cron format (names: mon,tue,wed,thu,fri,sat,sun)
                        num_to_name = {
                    "0": "mon", "1": "tue", "2": "wed", "3": "thu", "4": "fri", "5": "sat", "6": "sun"
                }
                        cron_days = ",".join([num_to_name[d] for d in selected_days])
                        cron_expressions.append(f"{minute} {hour} * * {cron_days}")
            else:
                         logger.warning(f"Could not parse days from: {days_part}")

                elif "monthly on day" in schedule_base:
                     # "Monthly on day 1" or "Monthly on day 1, 15"
                     days_part = schedule_base.replace("monthly on day", "").strip()
                     doms = [d.strip() for d in days_part.split(",")]
                     dom_str = ",".join(doms)
                     cron_expressions.append(f"{minute} {hour} {dom_str} * *")

                elif any(day in schedule_base for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
                    # "Monday" (Single day fallback)
        day_map = {
                        "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
                        "friday": "fri", "saturday": "sat", "sunday": "sun"
        }
                    found = False
                    for name, code in day_map.items():
                        if name in schedule_base:
                             cron_expressions.append(f"{minute} {hour} * * {code}")
                             found = True
                break
                    if not found:
                         logger.warning(f"Could not parse specific day schedule: {schedule_base}")
                
                else:
                    logger.warning(f"Unknown schedule format: {schedule_base}")

        except Exception as e:
            logger.warning(f"Failed to parse schedule part '{part}': {e}")
    
    return cron_expressions


async def _run_briefing_and_wait(
    briefing_id: str,
    run_id: str,
    prompt: str,
    seed_links: List[str]
) -> tuple[str, bool, Optional[str]]:
    """
    Run a briefing using Agent V2 and wait for completion.
    
    Returns: (briefing_id, success, error_message)
    """
    from services.db import connect
    import asyncio
    
    logger.info(f"[run_id={run_id}] Starting briefing run for {briefing_id} (Agent V2)")
    
    try:
        # Initialize Agent V2
        agent = AgentV2()
        
        # Create request object
        request = AgentV2Request(
            url=seed_links[0] if seed_links else "",  # V2 expects a primary URL, fallback to empty if none (though validation usually catches this)
            prompt=prompt,
            page_type=PageType.BLOG_LISTING,  # Default to blog listing for now as per V2 capabilities
            max_items=10,
            time_range_days=None # Could be configurable in future
        )
        
        # Run agent (async)
        result = await agent.run(request)
        
        # Use connection for database operations
        with connect() as conn:
            if not result or not result.items:
                agent_service.mark_run_as_failed(run_id, "Agent returned no content", conn=conn)
                return (briefing_id, False, "Agent returned no content")
            
            # Convert V2 response to format expected by database storage
            # Summary markdown might be in result.summary or generated from items
            summary_text = result.summary or "No summary generated."
            
            # Extract bullet points (simulate if not present, V2 might return structured summary)
            # For now, we'll just use the item titles as bullet points if no explicit bullets
            bullet_points = [item.title for item in result.items if item.title]
            
            # Format citations
            citations = [{"url": item.url, "label": item.title} for item in result.items]
            
            # Save the summary
            agent_service.save_summary_and_finalize_run(
                run_id=run_id,
                briefing_id=briefing_id,
                summary_markdown=summary_text,
                bullet_points=bullet_points,
                citations=citations,
                model="agent-v2", # Identify as V2 run
                conn=conn
            )
            
            # Update briefing's last_run_at timestamp
            briefings_service.update_briefing_last_run(briefing_id, conn=conn)
            
            logger.info(f"[run_id={run_id}] ✅ Briefing {briefing_id} completed successfully with Agent V2")
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

