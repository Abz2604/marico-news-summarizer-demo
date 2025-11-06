from typing import List
import asyncio
import json

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from agent.graph import run_agent
from config import get_settings
from services import agent_service, briefings_service


router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    prompt: str
    seed_links: List[HttpUrl]
    max_articles: int = 10  # Increased to allow more articles within time window


class AgentRunResponse(BaseModel):
    summary_markdown: str
    bullet_points: List[str]
    citations: List[dict]
    model: str


@router.post(
    "/run",
    response_model=AgentRunResponse,
    deprecated=True,
    summary="[DEPRECATED] Use POST /briefings/{briefing_id}/run instead",
)
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

    # Note: This deprecated endpoint does not save the run to the database.
    return AgentRunResponse(
        summary_markdown=result.summary_markdown,
        bullet_points=result.bullet_points,
        citations=result.citations,
        model=result.model,
    )


@router.post("/briefings/{briefing_id}/run", response_model=AgentRunResponse)
async def run_agent_for_briefing(briefing_id: str):
    """
    Runs the agent for a specific briefing, using its stored prompt and seed links.
    The run and its resulting summary are saved to the database.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")

    briefing = briefings_service.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    logging.info(f"Starting agent run for briefing_id={briefing_id}")
    run_record = agent_service.create_agent_run(briefing_id=briefing_id)

    try:
        result = await run_agent(
            prompt=briefing.prompt,
            seed_links=[str(url) for url in briefing.primary_links],
            max_articles=10,  # This could be a parameter in the future
        )
    except Exception as exc:
        logging.exception("Agent run raised exception: %s", exc)
        # TODO: Update run record to failed status
        raise HTTPException(status_code=500, detail="Agent run failed with exception")

    if not result:
        logging.error("Agent run returned no result")
        # TODO: Update run record to failed status
        raise HTTPException(status_code=422, detail="No usable content extracted from the provided URLs.")

    # Save summary and finalize run
    agent_service.save_summary_and_finalize_run(
        run_id=run_record.id,
        briefing_id=briefing_id,
        summary_markdown=result.summary_markdown,
        bullet_points=result.bullet_points,
        citations=result.citations,
        model=result.model,
    )

    return AgentRunResponse(
        summary_markdown=result.summary_markdown,
        bullet_points=result.bullet_points,
        citations=result.citations,
        model=result.model,
    )


@router.get("/run/stream")
async def run_agent_stream(
    prompt: str,
    seed_links: str,  # JSON array as string
    max_articles: int = 10,  # Increased to allow more articles within time window
    target_section: str = ""  # NEW: Target section (forum, news, etc.)
):
    """
    Stream agent progress in real-time using Server-Sent Events (SSE).
    
    Events emitted:
    - init: Agent starting
    - nav:*: Navigation events
    - fetch:*: Article fetching events
    - date:*: Date extraction events
    - quality:*: Content validation events
    - dedup:*: Deduplication events
    - summarize:*: Summary generation events
    - complete: Final result ready
    - error: Error occurred
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=422, detail="OPENAI_API_KEY is not configured")
    
    # Parse seed_links from JSON string
    try:
        seed_links_list = json.loads(seed_links)
        if not isinstance(seed_links_list, list):
            raise ValueError("seed_links must be a JSON array")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid seed_links format: {str(e)}")
    
    logging.info("/agent/run/stream request: max_articles=%s seed_links=%s", 
                 max_articles, seed_links_list)
    
    async def event_generator():
        # Create event queue
        event_queue = asyncio.Queue()
        
        # Event callback to push events to queue
        def event_callback(event):
            try:
                # Put event in queue (non-blocking)
                event_queue.put_nowait(event)
            except Exception as e:
                logging.error(f"Failed to queue event: {e}")
        
        # Run agent in background task
        async def run_in_background():
            try:
                result = await run_agent(
                    prompt=prompt,
                    seed_links=seed_links_list,
                    max_articles=max_articles,
                    event_callback=event_callback,
                    target_section=target_section,  # NEW: Pass explicit section
                )
                
                if result:
                    # Send complete event with final result
                    await event_queue.put({
                        "event": "complete",
                        "data": {
                            "summary_markdown": result.summary_markdown,
                            "bullet_points": result.bullet_points,
                            "citations": result.citations,
                            "model": result.model,
                        }
                    })
                else:
                    # Agent returned None (error)
                    await event_queue.put({
                        "event": "error",
                        "error": "No usable content extracted from the provided URLs."
                    })
                    
            except Exception as e:
                logging.exception(f"Agent run failed: {e}")
                await event_queue.put({
                    "event": "error",
                    "error": str(e)
                })
            finally:
                # Send sentinel to signal completion
                await event_queue.put(None)
        
        # Start background task
        task = asyncio.create_task(run_in_background())
        
        try:
            # Stream events as they come
            while True:
                # Wait for next event (with timeout for keep-alive)
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    yield f": keep-alive\n\n"
                    continue
                
                if event is None:
                    # Sentinel received, we're done
                    break
                
                # Format as SSE message
                event_json = json.dumps(event)
                yield f"data: {event_json}\n\n"
            
            # Ensure task completes
            await task
            
        except asyncio.CancelledError:
            # Client disconnected, cancel background task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logging.info("SSE connection cancelled by client")
        except Exception as e:
            logging.error(f"SSE streaming error: {e}")
            error_event = {"event": "error", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
