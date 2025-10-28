from typing import List

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from agent.graph import run_agent
from config import get_settings

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    prompt: str
    seed_links: List[HttpUrl]
    max_articles: int = 3


class AgentRunResponse(BaseModel):
    summary_markdown: str
    bullet_points: List[str]
    citations: List[dict]
    model: str


@router.post("/run", response_model=AgentRunResponse)
async def run_agent_endpoint(payload: AgentRunRequest):
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")
    logging.info("/agent/run request: max_articles=%s seed_links=%s", payload.max_articles, [str(u) for u in payload.seed_links])
    try:
        result = await run_agent(
            prompt=payload.prompt,
            seed_links=[str(url) for url in payload.seed_links],
            max_articles=payload.max_articles,
        )
    except Exception as exc:  # noqa: BLE001
        logging.exception("Agent run raised exception: %s", exc)
        raise HTTPException(status_code=500, detail="Agent run failed with exception")
    if not result:
        logging.error("Agent run returned no result (None or error state)")
        # If we had no articles extracted, return a 422 to the client with a helpful message
        raise HTTPException(status_code=422, detail="No usable content extracted from the provided URLs. Try a different link.")

    return AgentRunResponse(
        summary_markdown=result.summary_markdown,
        bullet_points=result.bullet_points,
        citations=result.citations,
        model=result.model,
    )
