"""
AgentV2 API Router

New endpoint for AgentV2 with agent toggle support.
"""

import logging
import json
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl, Field

from agent_v2 import AgentV2, AgentV2Request, AgentV2Response, PageType
from agent_v2.graph import set_event_callback
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-v2", tags=["agent-v2"])

# Test endpoint to verify router is loaded
@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify router is working"""
    logger.info("TEST ENDPOINT CALLED - Router is working!")
    return {"status": "ok", "message": "AgentV2 router is loaded and working"}


class AgentV2RunRequest(BaseModel):
    """Request for AgentV2 run"""
    url: HttpUrl
    prompt: str
    page_type: str = Field(..., description="Page type: blog_listing, forum_thread")
    max_items: int = Field(default=10, ge=1, le=50)
    time_range_days: Optional[int] = Field(default=None, ge=0, description="Time range in days (None = no filter)")


class AgentV2RunResponse(BaseModel):
    """Response from AgentV2 run"""
    items: List[dict]
    summary: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/run", response_model=AgentV2RunResponse)
async def run_agent_v2(payload: AgentV2RunRequest):
    """
    Run AgentV2 to extract content from a page.
    
    Args:
        payload: AgentV2RunRequest with URL, prompt, page_type, etc.
        
    Returns:
        AgentV2RunResponse with extracted content
    """
    # Force log output - use print as well to ensure we see something
    print("=" * 80)
    print("AGENTV2 API ENDPOINT CALLED (PRINT)")
    print("=" * 80)
    
    import sys
    sys.stdout.flush()
    
    logger.info("=" * 80)
    logger.info("AGENTV2 API ENDPOINT CALLED (LOGGER)")
    logger.info("=" * 80)
    
    # Force flush logger
    for handler in logger.handlers:
        handler.flush()
    
    settings = get_settings()
    
    # Validate AI configuration
    if not settings.azure_openai_key and not settings.openai_api_key:
        raise HTTPException(
            status_code=422,
            detail="AI API key not configured. Please set AZURE_OPENAI_KEY or OPENAI_API_KEY."
        )
    
    # Validate page type
    try:
        page_type = PageType(payload.page_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid page_type: {payload.page_type}. Must be one of: {[pt.value for pt in PageType]}"
        )
    
    logger.info(f"AgentV2 request: {payload.page_type} - {payload.url}")
    logger.info(f"  Prompt: {payload.prompt}")
    logger.info(f"  Max items: {payload.max_items}")
    logger.info(f"  Time range: {payload.time_range_days}")
    
    try:
        # Create request
        request = AgentV2Request(
            url=str(payload.url),
            prompt=payload.prompt,
            page_type=page_type,
            max_items=payload.max_items,
            time_range_days=payload.time_range_days
        )
        
        # Run agent
        agent = AgentV2()
        response = await agent.run(request)
        
        # Convert to API response format
        items = [
            {
                "url": item.url,
                "title": item.title,
                "content": item.content,
                "publish_date": item.publish_date.isoformat() if item.publish_date else None,
                "content_type": item.content_type,
                "metadata": item.metadata or {}
            }
            for item in response.items
        ]
        
        return AgentV2RunResponse(
            items=items,
            summary=response.summary,
            metadata=response.metadata
        )
        
    except Exception as e:
        logger.exception("AgentV2 run failed")
        raise HTTPException(
            status_code=500,
            detail=f"AgentV2 run failed: {str(e)}"
        )


@router.get("/page-types")
async def get_page_types():
    """
    Get list of supported page types.
    
    Returns:
        List of available page types
    """
    return {
        "page_types": [
            {
                "value": pt.value,
                "description": _get_page_type_description(pt)
            }
            for pt in PageType
        ]
    }


def _get_page_type_description(page_type: PageType) -> str:
    """Get human-readable description for page type"""
    descriptions = {
        PageType.BLOG_LISTING: "Blog or news listing page with article links",
        PageType.FORUM_THREAD: "Forum thread page with posts/comments",
    }
    return descriptions.get(page_type, "Unknown page type")


@router.get("/run/stream")
async def run_agent_v2_stream(
    url: str,
    prompt: str,
    page_type: str = "blog_listing",
    max_items: int = 10,
    time_range_days: Optional[int] = None
):
    """
    Stream AgentV2 progress in real-time using Server-Sent Events (SSE).
    
    Events emitted:
    - init: Agent starting
    - fetch_listing:*: Listing page fetch events
    - extract_links:*: Link extraction events (stage1, stage2, batches)
    - fetch_article:*: Article fetching events
    - check_goal:*: Goal evaluation events
    - summarize:*: Summary generation events
    - complete: Final result ready
    - error: Error occurred
    """
    settings = get_settings()
    
    # Validate AI configuration
    if not settings.azure_openai_key and not settings.openai_api_key:
        raise HTTPException(
            status_code=422,
            detail="AI API key not configured. Please set AZURE_OPENAI_KEY or OPENAI_API_KEY."
        )
    
    # Validate page type
    try:
        page_type_enum = PageType(page_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid page_type: {page_type}. Must be one of: {[pt.value for pt in PageType]}"
        )
    
    logger.info(f"AgentV2 stream request: {page_type} - {url}")
    logger.info(f"  Prompt: {prompt}")
    logger.info(f"  Max items: {max_items}")
    logger.info(f"  Time range: {time_range_days}")
    
    async def event_generator():
        # Create event queue
        event_queue = asyncio.Queue()
        
        # Event callback to push events to queue
        def event_callback(event):
            try:
                event_queue.put_nowait(event)
            except Exception as e:
                logger.error(f"Failed to queue event: {e}")
        
        # Set global event callback for graph nodes
        set_event_callback(event_callback)
        
        # Run agent in background task
        async def run_in_background():
            try:
                # Create request
                request = AgentV2Request(
                    url=url,
                    prompt=prompt,
                    page_type=page_type_enum,
                    max_items=max_items,
                    time_range_days=time_range_days
                )
                
                # Run agent with event callback
                agent = AgentV2(event_callback=event_callback)
                response = await agent.run(request)
                
                # Convert to API response format
                items = [
                    {
                        "url": item.url,
                        "title": item.title,
                        "content": item.content,
                        "publish_date": item.publish_date.isoformat() if item.publish_date else None,
                        "content_type": item.content_type,
                        "metadata": item.metadata or {}
                    }
                    for item in response.items
                ]
                
                # Send complete event with final result
                await event_queue.put({
                    "event": "complete",
                    "data": {
                        "items": items,
                        "summary": response.summary,
                        "metadata": response.metadata
                    }
                })
                    
            except Exception as e:
                logger.exception(f"AgentV2 run failed: {e}")
                await event_queue.put({
                    "event": "error",
                    "error": str(e)
                })
            finally:
                # Clear event callback
                set_event_callback(None)
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
            set_event_callback(None)
            logger.info("SSE connection cancelled by client")
        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            set_event_callback(None)
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

