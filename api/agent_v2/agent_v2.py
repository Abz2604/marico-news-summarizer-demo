"""
AgentV2 - Main Orchestrator

LangGraph-based agent that loops until goal is reached or abort conditions are met.
Uses LLM intelligence for decision-making.
"""

import logging
from typing import List
from datetime import datetime

from .types import (
    AgentV2Request,
    AgentV2Response,
    PageType,
    ExtractedContent,
    AgentState
)
from .graph import get_agent_graph

logger = logging.getLogger(__name__)


class AgentV2:
    """
    Main AgentV2 orchestrator using LangGraph.
    
    Goal-oriented agent that extracts content based on user prompt.
    """
    
    def __init__(self, event_callback=None):
        """
        Initialize AgentV2.
        
        Args:
            event_callback: Optional callback function(event_dict) to emit events for streaming
        """
        self.event_callback = event_callback
    
    def _emit(self, event_type: str, data: dict = None):
        """Emit an event if callback is set"""
        if self.event_callback:
            try:
                event = {"event": event_type}
                if data:
                    event.update(data)
                self.event_callback(event)
            except Exception as e:
                logger.error(f"Failed to emit event {event_type}: {e}")
    
    async def run(self, request: AgentV2Request) -> AgentV2Response:
        """
        Run AgentV2 with the given request using LangGraph.
        
        Args:
            request: AgentV2Request with URL, prompt, page_type, etc.
            
        Returns:
            AgentV2Response with extracted content
        """
        # Force log output
        print("=" * 80)
        print("AGENTV2 RUN STARTED (PRINT)")
        print("=" * 80)
        import sys
        sys.stdout.flush()
        
        logger.info("=" * 80)
        logger.info("AGENTV2 RUN STARTED (LOGGER)")
        logger.info("=" * 80)
        
        # Force flush logger
        for handler in logger.handlers:
            handler.flush()
        logger.info(f"AgentV2: Processing {request.page_type.value} page")
        logger.info(f"  URL: {request.url}")
        logger.info(f"  Topic: {request.prompt}")
        logger.info(f"  Max items: {request.max_items}")
        logger.info(f"  Time range: {request.time_range_days} days" if request.time_range_days else "  Time range: None")
        
        # Emit init event
        self._emit("init", {
            "url": request.url,
            "prompt": request.prompt,
            "page_type": request.page_type.value,
            "max_items": request.max_items,
            "time_range_days": request.time_range_days
        })
        
        # Only support blog_listing for now (forum_thread can be added later)
        if request.page_type != PageType.BLOG_LISTING:
            raise ValueError(f"Page type {request.page_type} not yet supported. Use BLOG_LISTING.")
        
        # Initialize state
        initial_state: AgentState = {
            'goal': {
                'target_items': request.max_items,
                'topic': request.prompt,
                'time_range_days': request.time_range_days,
                'quality_threshold': 0.8
            },
            'seed_url': request.url,
            'prompt': request.prompt,
            'page_type': request.page_type.value,
            'extracted_items': [],
            'links_found': [],
            'listing_html': None,
            'current_link_index': 0,
            'iteration': 0,
            'quality_score': 0.0,
            'error': None,
            'should_abort': False,
            'consecutive_failures': 0,
            'no_progress_iterations': 0,
            'history': []
        }
        
        # Get graph and run
        logger.info("Getting agent graph...")
        try:
            graph = get_agent_graph()
            logger.info("Graph obtained successfully")
        except Exception as e:
            logger.exception("Failed to get agent graph!")
            raise
        
        logger.info("Invoking graph with initial state...")
        logger.info(f"Initial state keys: {list(initial_state.keys())}")
        logger.info(f"Initial state goal: {initial_state.get('goal')}")
        
        # Create config with thread_id for checkpoint tracking
        import uuid
        thread_id = str(uuid.uuid4())
        config = {
            "configurable": {
                "thread_id": thread_id
            },
            "recursion_limit": 25  # Set explicit recursion limit
        }
        
        try:
            # Invoke graph with checkpoint config
            final_state = await graph.ainvoke(initial_state, config=config)
            
            logger.info("=" * 80)
            logger.info("GRAPH EXECUTION COMPLETED")
            logger.info("=" * 80)
            logger.info(f"Final state keys: {list(final_state.keys())}")
            logger.info(f"Final state error: {final_state.get('error')}")
            logger.info(f"Final state history length: {len(final_state.get('history', []))}")
            logger.info(f"Final state iterations: {final_state.get('iteration', 0)}")
            logger.info(f"Final state extracted_items: {len(final_state.get('extracted_items', []))}")
            logger.info(f"Final state links_found: {len(final_state.get('links_found', []))}")
            
            # Emit completion event
            self._emit("graph:complete", {
                "iterations": final_state.get('iteration', 0),
                "extracted_items": len(final_state.get('extracted_items', [])),
                "links_found": len(final_state.get('links_found', [])),
                "error": final_state.get('error')
            })
        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__
            
            # Check if it's a recursion limit error
            # Try to import GraphRecursionError for proper type checking
            is_recursion_error = False
            try:
                from langgraph.errors import GraphRecursionError
                is_recursion_error = isinstance(e, GraphRecursionError)
            except ImportError:
                # Fallback to string matching if import fails
                is_recursion_error = "recursion limit" in error_str.lower() or "RecursionLimit" in error_type
            
            if is_recursion_error:
                logger.warning(f"Recursion limit reached: {error_str}")
                logger.info("Attempting to recover state from checkpoint...")
                
                # Get the checkpointer and retrieve last checkpoint
                recovered_state = None
                try:
                    from agent_v2.graph import get_agent_checkpointer
                    checkpointer = get_agent_checkpointer()
                    
                    if checkpointer:
                        # List checkpoints for this thread (most recent first)
                        checkpoint_list = list(checkpointer.list(config, limit=1))
                        
                        if checkpoint_list:
                            # Get the most recent checkpoint
                            checkpoint = checkpoint_list[0]
                            # Retrieve the state from checkpoint
                            checkpoint_data = checkpointer.get(config, checkpoint)
                            
                            if checkpoint_data:
                                # State is stored in 'channel_values' or directly as the checkpoint
                                if hasattr(checkpoint_data, 'channel_values'):
                                    recovered_state = checkpoint_data.channel_values
                                elif isinstance(checkpoint_data, dict) and 'channel_values' in checkpoint_data:
                                    recovered_state = checkpoint_data['channel_values']
                                elif isinstance(checkpoint_data, dict):
                                    # Checkpoint data might be the state itself
                                    recovered_state = checkpoint_data
                                
                                if recovered_state:
                                    logger.info(f"✅ Recovered state from checkpoint: {len(recovered_state.get('extracted_items', []))} items")
                                else:
                                    logger.warning("Checkpoint found but state structure unexpected")
                            else:
                                logger.warning("Checkpoint found but no data returned")
                        else:
                            logger.warning("No checkpoints found for this thread")
                    else:
                        logger.warning("Graph has no checkpointer configured")
                except Exception as checkpoint_error:
                    logger.exception(f"Failed to retrieve checkpoint: {checkpoint_error}")
                
                # If checkpoint recovery failed, try to get state from the exception
                if not recovered_state:
                    # Fallback: check if exception has state info
                    if hasattr(e, 'state') and e.state:
                        recovered_state = e.state
                        logger.info("Using state from exception")
                    else:
                        logger.warning("Could not recover state from checkpoint or exception")
                
                # If we have extracted items, summarize them
                if recovered_state and len(recovered_state.get('extracted_items', [])) > 0:
                    logger.info(f"Found {len(recovered_state['extracted_items'])} extracted items, generating summary...")
                    self._emit("recursion_limit_reached", {
                        "extracted_items": len(recovered_state['extracted_items']),
                        "iterations": recovered_state.get('iteration', 0),
                        "message": "Recursion limit reached, summarizing collected items"
                    })
                    
                    # Run summarize node on the recovered state
                    try:
                        from agent_v2.graph import summarize_node
                        recovered_state = await summarize_node(recovered_state)
                        final_state = recovered_state
                        logger.info("Successfully summarized recovered items")
                    except Exception as summarize_error:
                        logger.exception("Failed to summarize recovered items")
                        # Continue with recovered_state even if summarization fails
                        final_state = recovered_state
                        final_state['error'] = f"Recursion limit reached. Summarization failed: {str(summarize_error)}"
                else:
                    # No items extracted, return error
                    logger.warning("Recursion limit reached but no items were extracted")
                    self._emit("error", {
                        "error": "Recursion limit reached and no items were extracted",
                        "stage": "graph_execution"
                    })
                    raise
            else:
                # Other errors - raise as before
                logger.exception("Graph invocation failed!")
                self._emit("error", {"error": str(e), "stage": "graph_execution"})
                raise
        
        # Convert state to response
        items = []
        for item_dict in final_state.get('extracted_items', []):
            # Convert dict back to ExtractedContent
            publish_date = None
            if item_dict.get('publish_date'):
                try:
                    publish_date = datetime.fromisoformat(item_dict['publish_date'])
                except Exception:
                    pass
            
            items.append(ExtractedContent(
                url=item_dict['url'],
                title=item_dict['title'],
                content=item_dict['content'],
                publish_date=publish_date,
                content_type=item_dict.get('content_type', 'article'),
                summary=item_dict.get('summary'),  # Per-article summary
                metadata=item_dict.get('metadata', {})
            ))
        
        summary = final_state.get('_summary')
        
        return AgentV2Response(
            items=items,
            summary=summary,
            metadata={
                'total_links_found': len(final_state.get('links_found', [])),
                'articles_extracted': len(items),
                'iterations': final_state.get('iteration', 0),
                'quality_score': final_state.get('quality_score', 0.0),
                'page_type': 'blog_listing',
                'error': final_state.get('error')
            }
        )

