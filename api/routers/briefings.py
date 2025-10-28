from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, HttpUrl


router = APIRouter(prefix="/briefings", tags=["briefings"])


# In-memory store (Phase 0)
_BRIEFINGS: dict[str, dict] = {}


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
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None


class BriefingListResponse(BaseModel):
    items: List[BriefingOut]
    nextCursor: Optional[str] = None


@router.get("")
async def list_briefings(status: Optional[str] = Query(None), limit: int = Query(20)) -> BriefingListResponse:
    items = []
    for b in _BRIEFINGS.values():
        if status and b.get("status") != status:
            continue
        items.append(BriefingOut(**b))
    return BriefingListResponse(items=items[:limit], nextCursor=None)


@router.post("", status_code=201)
async def create_briefing(payload: BriefingCreate) -> BriefingOut:
    now = datetime.utcnow().isoformat()
    bid = f"b_{int(datetime.utcnow().timestamp()*1000)}"
    if any(b.get("name") == payload.name for b in _BRIEFINGS.values()):
        raise HTTPException(status_code=409, detail="Briefing name already exists")
    record = {
        "id": bid,
        "name": payload.name,
        "description": payload.description,
        "status": "draft",
        "prompt": payload.prompt,
        "seed_links": [str(u) for u in payload.seed_links],
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
    }
    _BRIEFINGS[bid] = record
    return BriefingOut(**record)


@router.get("/{briefing_id}")
async def get_briefing(briefing_id: str) -> dict:
    b = _BRIEFINGS.get(briefing_id)
    if not b:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"briefing": BriefingOut(**b), "latest_summary": None}


@router.patch("/{briefing_id}")
async def update_briefing(briefing_id: str, payload: BriefingUpdate) -> BriefingOut:
    b = _BRIEFINGS.get(briefing_id)
    if not b:
        raise HTTPException(status_code=404, detail="Briefing not found")
    data = b.copy()
    if payload.name is not None:
        data["name"] = payload.name
    if payload.description is not None:
        data["description"] = payload.description
    if payload.status is not None:
        data["status"] = payload.status
    if payload.prompt is not None:
        data["prompt"] = payload.prompt
    if payload.seed_links is not None:
        data["seed_links"] = [str(u) for u in payload.seed_links]
    data["updated_at"] = datetime.utcnow().isoformat()
    _BRIEFINGS[briefing_id] = data
    return BriefingOut(**data)


@router.get("/{briefing_id}/runs")
async def list_runs(briefing_id: str) -> dict:
    if briefing_id not in _BRIEFINGS:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"items": []}


@router.get("/{briefing_id}/summaries")
async def list_summaries(briefing_id: str) -> dict:
    if briefing_id not in _BRIEFINGS:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"items": []}


