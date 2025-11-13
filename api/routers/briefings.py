from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Depends, status
from pydantic import BaseModel
import snowflake.connector

from services import briefings_service, agent_service
from services.db import get_db_connection
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingOut(BaseModel):
    id: str
    name: str
    prompt: str
    status: str
    description: Optional[str]
    seed_links: List[str]
    user_id: str
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime]


class BriefingListResponse(BaseModel):
    items: List[BriefingOut]
    next_cursor: Optional[str] = None


class BriefingCreate(BaseModel):
    name: str
    prompt: str
    description: Optional[str] = None
    seed_links: List[str]


class BriefingUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    seed_links: Optional[List[str]] = None
    status: Optional[str] = None


class AgentRunResponse(BaseModel):
    run_id: str
    status: str
    summary_markdown: Optional[str] = None
    bullet_points: Optional[List[str]] = None
    citations: Optional[List[dict]] = None
    model: Optional[str] = None


@router.get("")
async def list_briefings(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> BriefingListResponse:
    """Lists briefings for the current user."""
    briefings = briefings_service.list_briefings(
        user_id=current_user["id"],
        limit=limit,
        conn=conn
    )
    
    items = [
        BriefingOut(
            id=b.id,
            name=b.name,
            prompt=b.prompt,
            status=b.status,
            description=b.description,
            seed_links=[str(link) for link in b.primary_links],  # Convert HttpUrl to string
            user_id=b.user_id,
            created_at=b.created_at,
            updated_at=b.updated_at,
            last_run_at=b.last_run_at,
        )
        for b in briefings
    ]
    
    return BriefingListResponse(items=items, next_cursor=None)


@router.post("", status_code=201)
async def create_briefing(
    payload: BriefingCreate,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> BriefingOut:
    """Creates a new briefing."""
    briefing = briefings_service.create_briefing(
        user_id=current_user["id"],
        name=payload.name,
        prompt=payload.prompt,
        description=payload.description,
        seed_links=payload.seed_links,
        conn=conn
    )
    
    return BriefingOut(
        id=briefing.id,
        name=briefing.name,
        prompt=briefing.prompt,
        status=briefing.status,
        description=briefing.description,
        seed_links=[str(link) for link in briefing.primary_links],  # Convert HttpUrl to string
        user_id=briefing.user_id,
        created_at=briefing.created_at,
        updated_at=briefing.updated_at,
        last_run_at=briefing.last_run_at,
    )


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: str,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Gets a single briefing with its latest summary."""
    briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if briefing.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get latest summary
    latest_summary = agent_service.get_latest_summary(briefing_id, conn=conn)
    
    return {
        "briefing": BriefingOut(
            id=briefing.id,
            name=briefing.name,
            prompt=briefing.prompt,
            status=briefing.status,
            description=briefing.description,
            seed_links=[str(link) for link in briefing.primary_links],  # Convert HttpUrl to string
            user_id=briefing.user_id,
            created_at=briefing.created_at,
            updated_at=briefing.updated_at,
            last_run_at=briefing.last_run_at,
        ),
        "latest_summary": latest_summary.dict() if latest_summary else None
    }


@router.patch("/{briefing_id}")
async def update_briefing(
    briefing_id: str, 
    payload: BriefingUpdate,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> BriefingOut:
    briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if briefing.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    updated = briefings_service.update_briefing(
        briefing_id=briefing_id,
        name=payload.name,
        description=payload.description,
        prompt=payload.prompt,
        seed_links=payload.seed_links,
        status=payload.status,
        conn=conn
    )
    
    return BriefingOut(
        id=updated.id,
        name=updated.name,
        prompt=updated.prompt,
        status=updated.status,
        description=updated.description,
        seed_links=[str(link) for link in updated.primary_links],  # Convert HttpUrl to string
        user_id=updated.user_id,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        last_run_at=updated.last_run_at,
    )


@router.delete("/{briefing_id}")
async def delete_briefing(
    briefing_id: str,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
):
    """Deletes a briefing."""
    briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if briefing.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    briefings_service.delete_briefing(briefing_id, conn=conn)
    return {"message": "Briefing deleted successfully"}


async def _run_agent_background(
    briefing_id: str,
    run_id: str,
    prompt: str,
    seed_links: List[str]
):
    """
    Background task to run agent and save results.
    
    All logs from this function and the agent execution will include [run_id={run_id}]
    for easy correlation in server logs.
    """
    from services.db import connect
    from agent.graph import run_agent
    
    # Create a logger adapter with run_id context for all logs
    import logging
    run_logger = logging.LoggerAdapter(
        logger,
        extra={"run_id": run_id, "briefing_id": briefing_id}
    )
    
    run_logger.info(f"[run_id={run_id}] Starting background agent run for briefing {briefing_id}")
    run_logger.debug(f"[run_id={run_id}] Prompt: {prompt[:100]}...")
    run_logger.debug(f"[run_id={run_id}] Seed links: {len(seed_links)} URLs")
    
    conn = None
    try:
        # Create a connection for this background task
        with connect() as conn:
            run_logger.info(f"[run_id={run_id}] Executing agent...")
            
            # Execute the agent
            result = await run_agent(
                prompt=prompt,
                seed_links=seed_links,
                max_articles=10
            )
            
            if not result:
                agent_service.mark_run_as_failed(run_id, "Agent returned no result", conn=conn)
                run_logger.error(f"[run_id={run_id}] Agent returned no result")
                return
            
            run_logger.info(f"[run_id={run_id}] Agent completed successfully, saving summary...")
            
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
            
            run_logger.info(
                f"[run_id={run_id}] ✅ Successfully completed agent run for briefing {briefing_id}. "
                f"Summary saved with {len(result.bullet_points)} bullet points."
            )
            
    except Exception as e:
        run_logger.exception(f"[run_id={run_id}] ❌ Error in background agent run: {e}")
        # Mark as failed - need connection for this
        try:
            with connect() as conn:
                agent_service.mark_run_as_failed(run_id, str(e), conn=conn)
                run_logger.error(f"[run_id={run_id}] Marked run as failed in database")
        except Exception as db_error:
            run_logger.error(f"[run_id={run_id}] Failed to mark run as failed: {db_error}")


@router.post("/{briefing_id}/run")
async def run_briefing(
    briefing_id: str, 
    background_tasks: BackgroundTasks,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection),
    current_user: dict = Depends(get_current_user)
) -> AgentRunResponse:
    """Triggers an agent run for a specific briefing. Returns immediately with run_id."""
    
    # Verify briefing exists
    briefing = briefings_service.get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if briefing.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to run this briefing")
    
    # Create an agent run record
    agent_run = agent_service.create_agent_run(
        briefing_id=briefing_id,
        trigger_type="manual",
        conn=conn
    )
    
    # Add background task to run agent
    background_tasks.add_task(
        _run_agent_background,
        briefing_id=briefing_id,
        run_id=agent_run.id,
        prompt=briefing.prompt,
        seed_links=[str(link) for link in briefing.primary_links]
    )
    
    # Return immediately with run_id
    return AgentRunResponse(
        run_id=agent_run.id,
        status="queued",
        summary_markdown=None,
        bullet_points=None,
        citations=None,
        model=None,
    )
