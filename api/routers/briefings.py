from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, HttpUrl

from services import briefings_service, agent_service


router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: str
    seed_links: List[HttpUrl]


class BriefingUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    prompt: Optional[str] = None
    seed_links: Optional[List[HttpUrl]] = None


class BriefingOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    prompt: str
    seed_links: List[str]
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime] = None


class BriefingListResponse(BaseModel):
    items: List[BriefingOut]
    nextCursor: Optional[str] = None


@router.get("")
async def list_briefings(status: Optional[str] = Query(None), limit: int = Query(20)) -> BriefingListResponse:
    briefings_list = briefings_service.list_briefings(status=status, limit=limit)
    items = [
        BriefingOut(
            id=b.id,
            name=b.name,
            description=b.description,
            status=b.status,
            prompt=b.prompt,
            seed_links=[str(link) for link in b.primary_links],
            created_at=b.created_at,
            updated_at=b.updated_at,
            last_run_at=b.last_run_at,
        )
        for b in briefings_list
    ]
    return BriefingListResponse(items=items)


@router.post("", status_code=201)
async def create_briefing(payload: BriefingCreate) -> BriefingOut:
    try:
        new_briefing = briefings_service.create_briefing(
            name=payload.name,
            description=payload.description,
            prompt=payload.prompt,
            seed_links=[str(url) for url in payload.seed_links],
        )
        return BriefingOut(
            id=new_briefing.id,
            name=new_briefing.name,
            description=new_briefing.description,
            status=new_briefing.status,
            prompt=new_briefing.prompt,
            seed_links=[str(link) for link in new_briefing.primary_links],
            created_at=new_briefing.created_at,
            updated_at=new_briefing.updated_at,
            last_run_at=new_briefing.last_run_at,
        )
    except Exception as e:
        # A more specific exception would be better here
        raise HTTPException(status_code=409, detail=f"Briefing could not be created: {e}")


@router.get("/{briefing_id}")
async def get_briefing(briefing_id: str) -> dict:
    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    b_out = BriefingOut(
        id=briefing.id,
        name=briefing.name,
        description=briefing.description,
        status=briefing.status,
        prompt=briefing.prompt,
        seed_links=[str(link) for link in briefing.primary_links],
        created_at=briefing.created_at,
        updated_at=briefing.updated_at,
        last_run_at=briefing.last_run_at,
    )
    
    # Fetch latest summary if available
    summary = agent_service.get_latest_summary(briefing_id)
    summary_out = None
    if summary:
        summary_out = {
            "id": summary.id,
            "summary_markdown": summary.summary_markdown,
            "bullet_points": summary.bullet_points,
            "citations": summary.citations,
            "created_at": summary.created_at.isoformat(),
        }
    
    return {"briefing": b_out, "latest_summary": summary_out}


@router.patch("/{briefing_id}")
async def update_briefing(briefing_id: str, payload: BriefingUpdate) -> BriefingOut:
    # This is a placeholder implementation. A real implementation would
    # call a briefings_service.update_briefing function.
    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Update fields from payload
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(briefing, key, value)
    
    # In a real scenario, you would save the updated briefing object here.
    # For now, we just return it. The data is not actually persisted.
    # A call to an update service function would be needed.
    
    return BriefingOut(
        id=briefing.id,
        name=briefing.name,
        description=briefing.description,
        status=briefing.status,
        prompt=briefing.prompt,
        seed_links=[str(link) for link in briefing.primary_links],
        created_at=briefing.created_at,
        updated_at=datetime.utcnow(),  # Should be set by the database
        last_run_at=briefing.last_run_at,
    )


@router.get("/{briefing_id}/runs")
async def list_runs(briefing_id: str) -> dict:
    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"items": []}


@router.get("/{briefing_id}/summaries")
async def list_summaries(briefing_id: str) -> dict:
    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"items": []}


class AgentRunResponse(BaseModel):
    summary_markdown: str
    bullet_points: List[str]
    citations: List[dict]
    model: str


@router.post("/{briefing_id}/run")
async def run_briefing(briefing_id: str, background_tasks: BackgroundTasks) -> AgentRunResponse:
    """Triggers an agent run for a specific briefing and returns the summary."""
    
    # Verify briefing exists
    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    
    # Create an agent run record
    agent_run = agent_service.create_agent_run(
        briefing_id=briefing_id,
        trigger_type="manual"
    )
    
    try:
        # Import the agent execution logic
        from agent.graph import run_agent
        
        # Execute the agent
        result = await run_agent(
            prompt=briefing.prompt,
            seed_links=[str(link) for link in briefing.primary_links],
            max_articles=10
        )
        
        if not result:
            agent_service.mark_run_as_failed(agent_run.id, "Agent returned no result")
            raise HTTPException(status_code=422, detail="No usable content extracted from the provided URLs")
        
        # Save the summary
        summary = agent_service.save_summary_and_finalize_run(
            run_id=agent_run.id,
            briefing_id=briefing_id,
            summary_markdown=result.summary_markdown,
            bullet_points=result.bullet_points,
            citations=result.citations,
            model=result.model,
        )
        
        # Update briefing's last_run_at timestamp
        briefings_service.update_briefing_last_run(briefing_id)
        
        return AgentRunResponse(
            summary_markdown=summary.summary_markdown,
            bullet_points=summary.bullet_points,
            citations=summary.citations,
            model=result.model,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Mark the run as failed
        agent_service.mark_run_as_failed(agent_run.id, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run agent: {str(e)}")


