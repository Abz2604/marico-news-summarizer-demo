from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/campaigns", tags=["campaigns"])


_CAMPAIGNS: dict[str, dict] = {}


class CampaignOut(BaseModel):
    id: str
    name: str
    status: str
    description: Optional[str]
    briefing_ids: List[str]
    recipient_emails: List[str]
    schedule_description: Optional[str]


@router.get("")
async def list_campaigns() -> dict:
    return {"items": [CampaignOut(**c) for c in _CAMPAIGNS.values()]}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str) -> CampaignOut:
    c = _CAMPAIGNS.get(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignOut(**c)


