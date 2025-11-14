"""
LangGraph Agent Implementation

Goal-oriented agent that loops until goal is reached or abort conditions are met.
Uses LLM intelligence for decision-making.
"""

import logging
import json
import asyncio
from typing import Literal, Optional, Callable
from datetime import datetime, timedelta

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .types import AgentState, ExtractedContent, ExtractedLink
from .tools import fetch_page, extract_links, extract_content
from .ai_factory import get_ai_factory

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def summarize_article(
    title: str,
    content: str,
    url: str,
    user_prompt: str,
    topic: str
) -> str:
    """
    Generate a concise summary for a single article.
    
    Args:
        title: Article title
        content: Full article content
        url: Article URL
        user_prompt: User's original request/prompt
        topic: Topic being searched
        
    Returns:
        Summary string (100-150 words)
    """
    try:
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        # Limit content size for summarization (keep it focused)
        content_preview = content[:2000] if len(content) > 2000 else content
        
        # Determine if user has a specific request
        has_specific_request = len(user_prompt) > 20 and not user_prompt.lower().startswith("find")
        
        if has_specific_request:
            prompt = f"""Create a concise summary of this article that addresses the user's specific request.

USER REQUEST: {user_prompt}
TOPIC: {topic}

ARTICLE:
Title: {title}
URL: {url}
Content: {content_preview}

TASK: Create a focused summary (100-150 words) that:
1. Directly addresses how this article relates to the user's request: "{user_prompt}"
2. Highlights the most relevant information from the article
3. Is concise and well-structured
4. Uses clear, readable language

Return ONLY the summary text (no markdown, no JSON, no extra formatting)."""
        else:
            prompt = f"""Create a concise summary of this article.

TOPIC: {topic}

ARTICLE:
Title: {title}
URL: {url}
Content: {content_preview}

TASK: Create a medium-sized summary (100-150 words) that:
1. Captures the main points and key information
2. Is well-structured and readable
3. Focuses on the most important details
4. Uses clear, concise language

Return ONLY the summary text (no markdown, no JSON, no extra formatting)."""
        
        response = await llm.ainvoke(prompt)
        summary = response.content.strip()
        
        # Clean up any markdown formatting that might have been added
        if summary.startswith("```"):
            lines = summary.split("\n")
            summary = "\n".join([l for l in lines if not l.startswith("```")])
        
        logger.info(f"Generated summary for article: {title[:50]} ({len(summary)} chars)")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to summarize article {title[:50]}: {e}")
        # Fallback: return a simple excerpt
        return content[:200] + "..." if len(content) > 200 else content

# Global event callback (set by streaming endpoint)
_event_callback: Optional[Callable[[dict], None]] = None

def set_event_callback(callback: Optional[Callable[[dict], None]]):
    """Set global event callback for streaming"""
    global _event_callback
    _event_callback = callback

def _emit_event(event_type: str, data: dict = None):
    """Emit an event if callback is set"""
    if _event_callback:
        try:
            event = {"event": event_type}
            if data:
                event.update(data)
            _event_callback(event)
        except Exception as e:
            logger.error(f"Failed to emit event {event_type}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# NODE IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_listing_node(state: AgentState) -> AgentState:
    """Fetch the seed URL listing page"""
    logger.info("=" * 80)
    logger.info("FETCH_LISTING_NODE CALLED")
    logger.info(f"State keys: {list(state.keys())}")
    logger.info(f"Seed URL: {state.get('seed_url')}")
    logger.info("=" * 80)
    logger.info(f"[Node: fetch_listing] Fetching: {state['seed_url']}")
    
    _emit_event("fetch_listing:start", {"url": state['seed_url']})
    
    try:
        # Don't clean HTML - we need raw HTML for link extraction!
        html = await fetch_page(state['seed_url'], render_js=False, clean=False)
        
        if html:
            state['listing_html'] = html
            state['history'].append({
                'action': 'fetch_listing',
                'success': True,
                'html_length': len(html)
            })
            logger.info(f"[Node: fetch_listing] Success: {len(html)} chars")
            _emit_event("fetch_listing:complete", {
                "url": state['seed_url'],
                "html_length": len(html),
                "html_size_kb": round(len(html) / 1024, 1)
            })
        else:
            state['error'] = "Failed to fetch listing page"
            state['consecutive_failures'] += 1
            state['history'].append({
                'action': 'fetch_listing',
                'success': False,
                'error': 'Failed to fetch'
            })
            logger.error("[Node: fetch_listing] Failed to fetch")
            _emit_event("fetch_listing:error", {"url": state['seed_url'], "error": "Failed to fetch"})
    
    except Exception as e:
        state['error'] = f"Fetch error: {str(e)}"
        state['consecutive_failures'] += 1
        state['history'].append({
            'action': 'fetch_listing',
            'success': False,
            'error': str(e)
        })
        logger.exception("[Node: fetch_listing] Exception")
        _emit_event("fetch_listing:error", {"url": state['seed_url'], "error": str(e)})
    
    return state


async def extract_links_node(state: AgentState) -> AgentState:
    """Extract article links from listing page"""
    logger.info("=" * 80)
    logger.info("EXTRACT_LINKS_NODE CALLED")
    logger.info(f"Has listing_html: {bool(state.get('listing_html'))}")
    listing_html = state.get('listing_html', '')
    logger.info(f"Listing HTML length: {len(listing_html)}")
    logger.info(f"Listing HTML preview (first 500 chars): {listing_html[:500]}")
    logger.info("=" * 80)
    logger.info("[Node: extract_links] Extracting links...")
    
    _emit_event("extract_links:start", {
        "html_length": len(listing_html),
        "topic": state['goal']['topic']
    })
    
    if not listing_html:
        state['error'] = "No listing HTML to extract links from"
        state['consecutive_failures'] += 1
        _emit_event("extract_links:error", {"error": "No listing HTML"})
        return state
    
    # Check if HTML has links (debug)
    from bs4 import BeautifulSoup
    soup_test = BeautifulSoup(listing_html, 'html.parser')
    all_a_tags = soup_test.find_all('a', href=True)
    logger.info(f"[DEBUG] Found {len(all_a_tags)} <a> tags in raw HTML")
    if len(all_a_tags) > 0:
        logger.info(f"[DEBUG] Sample links: {[a.get('href', '')[:50] for a in all_a_tags[:5]]}")
    
    _emit_event("extract_links:analyzing", {
        "total_links_found": len(all_a_tags)
    })
    
    try:
        links = await extract_links(
            html=listing_html,  # Use raw HTML, not cleaned
            base_url=state['seed_url'],
            topic=state['goal']['topic'],
            time_range_days=state['goal'].get('time_range_days'),
            max_links=state['goal']['target_items'] * 2
        )
        
        # Convert ExtractedLink objects to dicts for state
        links_dicts = [
            {
                'url': link.url,
                'title': link.title,
                'snippet': link.snippet,
                'detected_date': link.detected_date.isoformat() if link.detected_date else None,
                'relevance_score': link.relevance_score
            }
            for link in links
        ]
        
        state['links_found'] = links_dicts
        state['current_link_index'] = 0
        
        state['history'].append({
            'action': 'extract_links',
            'success': True,
            'links_count': len(links_dicts)
        })
        
        logger.info(f"[Node: extract_links] Found {len(links_dicts)} links")
        
        _emit_event("extract_links:complete", {
            "links_found": len(links_dicts),
            "links": [{"url": link.url, "title": link.title[:80]} for link in links[:5]]  # First 5 for preview
        })
        
        if len(links_dicts) == 0:
            state['consecutive_failures'] += 1
            state['error'] = "No links found"
    
    except Exception as e:
        state['error'] = f"Link extraction error: {str(e)}"
        state['consecutive_failures'] += 1
        state['history'].append({
            'action': 'extract_links',
            'success': False,
            'error': str(e)
        })
        logger.exception("[Node: extract_links] Exception")
    
    return state


async def fetch_article_node(state: AgentState) -> AgentState:
    """Fetch and extract content from next article"""
    article_num = state['current_link_index'] + 1
    total_links = len(state['links_found'])
    logger.info(f"[Node: fetch_article] Processing article {article_num}")
    
    if state['current_link_index'] >= len(state['links_found']):
        state['error'] = "No more links to process"
        state['should_abort'] = True
        return state
    
    link = state['links_found'][state['current_link_index']]
    link_url = link['url']
    
    _emit_event("fetch_article:start", {
        "article_num": article_num,
        "total_links": total_links,
        "url": link_url,
        "title": link.get('title', '')[:80]
    })
    
    try:
        # Fetch article
        html = await fetch_page(link_url, render_js=False, clean=True)
        
        if not html:
            logger.warning(f"[Node: fetch_article] Failed to fetch: {link_url}")
            state['current_link_index'] += 1
            state['consecutive_failures'] += 1
            state['history'].append({
                'action': 'fetch_article',
                'url': link_url,
                'success': False,
                'error': 'Failed to fetch'
            })
            _emit_event("fetch_article:error", {
                "article_num": article_num,
                "url": link_url,
                "error": "Failed to fetch"
            })
            return state
        
        _emit_event("fetch_article:extracting", {
            "article_num": article_num,
            "url": link_url,
            "html_length": len(html)
        })
        
        # Extract content
        content = await extract_content(
            html=html,
            url=link_url,
            page_type="article",
            topic=state['goal']['topic']
        )
        
        if content:
            # Date filtering: Prefer link's detected_date (from listing page) over content.publish_date (from article page)
            # The listing page date is more reliable for "recent" articles (e.g., "2 days ago")
            # The article page might have an old publication date that doesn't reflect recent updates
            link_date = None
            if link.get('detected_date'):
                # Link date might be stored as ISO string or datetime
                if isinstance(link['detected_date'], str):
                    try:
                        link_date = datetime.fromisoformat(link['detected_date'])
                    except Exception:
                        pass
                elif isinstance(link['detected_date'], datetime):
                    link_date = link['detected_date']
            
            # Use link date if available, otherwise fall back to content date
            article_date = link_date if link_date else content.publish_date
            
            if state['goal'].get('time_range_days'):
                cutoff = datetime.now() - timedelta(days=state['goal']['time_range_days'])
                if article_date and article_date < cutoff:
                    logger.warning(f"[Node: fetch_article] ❌ SKIPPING article (too old): {article_date} < {cutoff}")
                    logger.warning(f"  URL: {link_url}")
                    logger.warning(f"  Title: {content.title[:80]}")
                    logger.warning(f"  Date source: {'link (listing page)' if link_date else 'content (article page)'}")
                    _emit_event("fetch_article:skipped", {
                        "article_num": article_num,
                        "url": link_url,
                        "title": content.title[:80],
                        "reason": "Date too old",
                        "publish_date": article_date.isoformat() if article_date else None
                    })
                    state['current_link_index'] += 1
                    return state
                elif article_date:
                    logger.info(f"[Node: fetch_article] ✅ Date OK: {article_date} >= {cutoff} (source: {'link' if link_date else 'content'})")
            
            # Generate per-article summary
            _emit_event("fetch_article:summarizing", {
                "article_num": article_num,
                "url": link_url,
                "title": content.title[:80]
            })
            
            article_summary = await summarize_article(
                title=content.title,
                content=content.content,
                url=content.url,
                user_prompt=state['prompt'],
                topic=state['goal']['topic']
            )
            
            # Convert to dict for state (include summary)
            # Use link date if available (more reliable), otherwise use content date
            final_publish_date = link_date if link_date else content.publish_date
            content_dict = {
                'url': content.url,
                'title': content.title,
                'content': content.content,
                'publish_date': final_publish_date.isoformat() if final_publish_date else None,
                'content_type': content.content_type,
                'summary': article_summary,  # Per-article summary
                'metadata': content.metadata or {}
            }
            
            state['extracted_items'].append(content_dict)
            state['consecutive_failures'] = 0  # Reset on success
            state['no_progress_iterations'] = 0  # Reset on progress
            
            state['history'].append({
                'action': 'fetch_article',
                'url': link_url,
                'success': True,
                'title': content.title
            })
            
            logger.info(f"[Node: fetch_article] Extracted: {content.title[:50]}")
            
            _emit_event("fetch_article:complete", {
                "article_num": article_num,
                "total_extracted": len(state['extracted_items']),
                "url": link_url,
                "title": content.title[:80],
                "content_length": len(content.content),
                "publish_date": content.publish_date.isoformat() if content.publish_date else None
            })
        else:
            state['consecutive_failures'] += 1
            state['history'].append({
                'action': 'fetch_article',
                'url': link_url,
                'success': False,
                'error': 'Failed to extract content'
            })
            _emit_event("fetch_article:error", {
                "article_num": article_num,
                "url": link_url,
                "error": "Failed to extract content"
            })
        
        state['current_link_index'] += 1
    
    except Exception as e:
        state['error'] = f"Article extraction error: {str(e)}"
        state['consecutive_failures'] += 1
        state['current_link_index'] += 1
        state['history'].append({
            'action': 'fetch_article',
            'url': link_url,
            'success': False,
            'error': str(e)
        })
        logger.exception("[Node: fetch_article] Exception")
    
    return state


async def check_goal_node(state: AgentState) -> AgentState:
    """Evaluate if goal is reached using LLM intelligence"""
    logger.info("=" * 80)
    logger.info("CHECK_GOAL_NODE CALLED")
    logger.info(f"Iteration: {state.get('iteration', 0)}")
    logger.info(f"Extracted items: {len(state.get('extracted_items', []))}")
    logger.info(f"Links found: {len(state.get('links_found', []))}")
    logger.info("=" * 80)
    logger.info("[Node: check_goal] Evaluating goal...")
    
    state['iteration'] += 1
    
    _emit_event("check_goal:start", {
        "iteration": state['iteration'],
        "extracted_items": len(state.get('extracted_items', [])),
        "target_items": state['goal']['target_items'],
        "links_found": len(state.get('links_found', [])),
        "links_processed": state['current_link_index']
    })
    
    # Check abort conditions first
    if state['consecutive_failures'] >= 5:
        state['should_abort'] = True
        state['error'] = "Too many consecutive failures"
        logger.warning("[Node: check_goal] Abort: Too many failures")
        return state
    
    # Check recursion limit before it's hit (25 is the limit, abort at 23 to be safe)
    # This prevents hitting GraphRecursionError and allows graceful exit
    if state['iteration'] >= 23:
        state['should_abort'] = True
        state['error'] = "Approaching recursion limit, summarizing collected items"
        logger.warning(f"[Node: check_goal] Abort: Approaching recursion limit (iteration {state['iteration']}/25)")
        return state
    
    if state['no_progress_iterations'] >= 10:
        state['should_abort'] = True
        state['error'] = "No progress for too long"
        logger.warning("[Node: check_goal] Abort: No progress")
        return state
    
    # Use LLM to evaluate goal
    try:
        logger.info(f"[Node: check_goal] Calling LLM to evaluate goal (iteration {state['iteration']})...")
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        prompt = f"""You are an intelligent agent evaluating if you've reached your goal.

GOAL:
- Target items: {state['goal']['target_items']}
- Topic: {state['goal']['topic']}
- Time range: {state['goal'].get('time_range_days', 'None')} days
- Quality threshold: {state['goal'].get('quality_threshold', 0.8)}

CURRENT STATE:
- Items extracted: {len(state['extracted_items'])}/{state['goal']['target_items']}
- Links found: {len(state['links_found'])}
- Links processed: {state['current_link_index']}/{len(state['links_found'])}
- Iteration: {state['iteration']}
- Consecutive failures: {state['consecutive_failures']}

EXTRACTED ITEMS (titles):
{chr(10).join([f"- {item.get('title', 'Untitled')[:60]}" for item in state['extracted_items'][:5]])}

HISTORY (last 3 actions):
{json.dumps(state['history'][-3:], indent=2)}

Evaluate if the goal is reached. Consider:
1. Do we have enough items? (target: {state['goal']['target_items']})
2. Are items relevant to the topic?
3. Are items within time range?
4. Is quality acceptable?

Return ONLY JSON (no markdown):
{{
  "decision": "continue" | "done" | "abort",
  "reasoning": "Brief explanation",
  "quality_score": 0.0-1.0,
  "items_needed": number of additional items needed (if continue)
}}"""
        
        logger.info(f"[Node: check_goal] LLM prompt length: {len(prompt)} chars, invoking LLM...")
        # Add timeout to prevent hanging (30 seconds should be enough)
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
        logger.info(f"[Node: check_goal] LLM response received: {len(response.content) if response.content else 0} chars")
        response_text = response.content.strip()
        
        # Handle markdown
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            response_text = "\n".join(json_lines)
        
        logger.info(f"[Node: check_goal] Parsing LLM response...")
        result = json.loads(response_text)
        logger.info(f"[Node: check_goal] LLM decision: {result.get('decision')}, quality: {result.get('quality_score')}")
        
        decision = result.get('decision', 'continue')
        state['quality_score'] = float(result.get('quality_score', 0.5))
        
        state['history'].append({
            'action': 'check_goal',
            'decision': decision,
            'reasoning': result.get('reasoning', ''),
            'quality_score': state['quality_score']
        })
        
        _emit_event("check_goal:decision", {
            "iteration": state['iteration'],
            "decision": decision,
            "reasoning": result.get('reasoning', ''),
            "quality_score": state['quality_score'],
            "extracted_items": len(state.get('extracted_items', [])),
            "target_items": state['goal']['target_items'],
            "items_needed": result.get('items_needed', 0)
        })
        
        if decision == 'done':
            logger.info(f"[Node: check_goal] Goal reached! Quality: {state['quality_score']:.2f}")
            _emit_event("check_goal:done", {
                "iteration": state['iteration'],
                "quality_score": state['quality_score'],
                "extracted_items": len(state.get('extracted_items', []))
            })
        elif decision == 'abort':
            state['should_abort'] = True
            logger.warning(f"[Node: check_goal] Abort: {result.get('reasoning', '')}")
            _emit_event("check_goal:abort", {
                "reason": result.get('reasoning', ''),
                "quality_score": state['quality_score']
            })
        else:
            # Check if we made progress
            if len(state['extracted_items']) == state.get('_last_item_count', 0):
                state['no_progress_iterations'] += 1
            else:
                state['no_progress_iterations'] = 0
            state['_last_item_count'] = len(state['extracted_items'])
            
            logger.info(f"[Node: check_goal] Continue: {result.get('reasoning', '')}")
    
    except asyncio.TimeoutError:
        logger.error(f"[Node: check_goal] LLM call timed out after 30 seconds (iteration {state['iteration']})")
        # Fallback to simple rule-based check
        if len(state['extracted_items']) >= state['goal']['target_items']:
            decision = 'done'
        elif state['current_link_index'] >= len(state['links_found']):
            decision = 'abort'
        else:
            decision = 'continue'
        
        state['quality_score'] = 0.5
        state['history'].append({
            'action': 'check_goal',
            'decision': decision,
            'reasoning': 'LLM timeout - using fallback',
            'quality_score': state['quality_score']
        })
        logger.info(f"[Node: check_goal] Fallback decision: {decision}")
    except Exception as e:
        logger.exception(f"[Node: check_goal] LLM evaluation failed (iteration {state['iteration']}): {e}")
        logger.error(f"[Node: check_goal] Error type: {type(e).__name__}, Error message: {str(e)}")
        # Fallback to simple rule-based check
        if len(state['extracted_items']) >= state['goal']['target_items']:
            decision = 'done'
        elif state['current_link_index'] >= len(state['links_found']):
            decision = 'abort'
        else:
            decision = 'continue'
        
        state['quality_score'] = 0.5
        state['history'].append({
            'action': 'check_goal',
            'decision': decision,
            'reasoning': f'LLM error: {str(e)[:100]}',
            'quality_score': state['quality_score']
        })
        logger.info(f"[Node: check_goal] Fallback decision: {decision}")
    
    return state


async def summarize_node(state: AgentState) -> AgentState:
    """Create final summary from extracted items"""
    logger.info("[Node: summarize] Creating summary...")
    
    _emit_event("summarize:start", {
        "items_count": len(state['extracted_items']),
        "prompt": state['prompt']
    })
    
    if not state['extracted_items']:
        state['error'] = "No items to summarize"
        _emit_event("summarize:error", {"error": "No items to summarize"})
        return state
    
    try:
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        # Prepare items for summarization (reduce input size)
        items_text = "\n\n".join([
            f"Title: {item['title']}\nURL: {item['url']}\nContent: {item['content'][:500]}..."
            for item in state['extracted_items']
        ])
        
        user_request = state['prompt']
        has_specific_request = len(user_request) > 20 and not user_request.lower().startswith("find")
        
        if has_specific_request:
            prompt = f"""Create a concise summary that directly answers the user's specific request.

USER REQUEST: {user_request}
TOPIC: {state['goal']['topic']}
TIME RANGE: {state['goal'].get('time_range_days', 'None')} days

EXTRACTED ARTICLES ({len(state['extracted_items'])} items):
{items_text}

TASK: Create a focused summary that:
1. Directly addresses the user's request: "{user_request}"
2. Synthesizes key information from the articles
3. Provides a clear, concise answer
4. Keeps the summary to 200-300 words

IMPORTANT: 
- Focus on answering the user's specific question/request
- Be concise and direct
- Organize information logically
- Use markdown formatting (headings, bullets if helpful)

Return the summary as markdown text (no JSON wrapper)."""
        else:
            prompt = f"""Create a concise medium-sized summary of the articles.

TOPIC: {state['goal']['topic']}
TIME RANGE: {state['goal'].get('time_range_days', 'None')} days

EXTRACTED ARTICLES ({len(state['extracted_items'])} items):
{items_text}

TASK: Create a well-structured summary that:
1. Highlights the main themes and key points from the articles
2. Organizes information logically
3. Provides a clear overview
4. Keeps the summary to 200-300 words

IMPORTANT:
- Be concise and focused
- Synthesize information across articles
- Use markdown formatting (headings, bullets if helpful)

Return the summary as markdown text (no JSON wrapper)."""
        
        response = await llm.ainvoke(prompt)
        summary = response.content.strip()
        
        state['_summary'] = summary  # Store in state (will be extracted in response)
        
        state['history'].append({
            'action': 'summarize',
            'success': True,
            'summary_length': len(summary)
        })
        
        logger.info(f"[Node: summarize] Summary created: {len(summary)} chars")
        
        _emit_event("summarize:complete", {
            "summary_length": len(summary),
            "items_count": len(state['extracted_items'])
        })
    
    except Exception as e:
        state['error'] = f"Summarization error: {str(e)}"
        state['history'].append({
            'action': 'summarize',
            'success': False,
            'error': str(e)
        })
        logger.exception("[Node: summarize] Exception")
        _emit_event("summarize:error", {"error": str(e)})
    
    return state


# ═══════════════════════════════════════════════════════════════════════════
# DECISION FUNCTIONS (for conditional edges)
# ═══════════════════════════════════════════════════════════════════════════

def has_links(state: AgentState) -> Literal["yes", "no"]:
    """Check if links were found"""
    links_count = len(state.get('links_found', []))
    logger.info(f"[Decision: has_links] Links found: {links_count}")
    if links_count > 0:
        logger.info("[Decision: has_links] Returning 'yes'")
        return "yes"
    logger.info("[Decision: has_links] Returning 'no'")
    return "no"


def evaluate_goal(state: AgentState) -> Literal["continue", "done", "abort"]:
    """Evaluate goal and return routing decision"""
    logger.info("[Decision: evaluate_goal] Evaluating...")
    logger.info(f"  should_abort: {state.get('should_abort')}")
    logger.info(f"  history length: {len(state.get('history', []))}")
    
    if state.get('should_abort'):
        logger.info("[Decision: evaluate_goal] Returning 'abort' (should_abort=True)")
        return "abort"
    
    # Check last decision from check_goal_node
    last_action = state.get('history', [])[-1] if state.get('history') else {}
    decision = last_action.get('decision', 'continue')
    
    logger.info(f"[Decision: evaluate_goal] Last action decision: {decision}")
    
    if decision == 'done':
        logger.info("[Decision: evaluate_goal] Returning 'done'")
        return "done"
    elif decision == 'abort':
        logger.info("[Decision: evaluate_goal] Returning 'abort'")
        return "abort"
    else:
        logger.info("[Decision: evaluate_goal] Returning 'continue'")
        return "continue"


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════

def create_agent_graph():
    """Create and compile the LangGraph agent"""
    logger.info("Creating LangGraph workflow...")
    
    # Create graph
    try:
        workflow = StateGraph(AgentState)
        logger.info("StateGraph created successfully")
    except Exception as e:
        logger.exception("Failed to create StateGraph!")
        raise
    
    # Add nodes
    workflow.add_node("fetch_listing", fetch_listing_node)
    workflow.add_node("extract_links", extract_links_node)
    workflow.add_node("fetch_article", fetch_article_node)
    workflow.add_node("check_goal", check_goal_node)
    workflow.add_node("summarize", summarize_node)
    
    # Set entry point
    workflow.set_entry_point("fetch_listing")
    
    # Add edges
    workflow.add_edge("fetch_listing", "extract_links")
    
    # Conditional: Do we have links?
    workflow.add_conditional_edges(
        "extract_links",
        has_links,
        {
            "yes": "check_goal",
            "no": END  # No links, abort
        }
    )
    
    # Conditional: Goal reached?
    workflow.add_conditional_edges(
        "check_goal",
        evaluate_goal,
        {
            "continue": "fetch_article",  # Loop back to fetch more
            "done": "summarize",          # Goal reached, summarize
            "abort": END                  # Give up
        }
    )
    
    # After fetching article, check goal again (loop)
    workflow.add_edge("fetch_article", "check_goal")
    
    # Final step
    workflow.add_edge("summarize", END)
    
    # Compile graph with checkpoint memory for state recovery
    logger.info("Compiling graph with checkpoint memory...")
    try:
        # Use MemorySaver to store state checkpoints
        # This allows us to recover state if recursion limit is hit
        memory = MemorySaver()
        app = workflow.compile(checkpointer=memory)
        logger.info("Graph compiled successfully with checkpoint memory")
    except Exception as e:
        logger.exception("Failed to compile graph!")
        raise
    
    return app


# Global graph instance and checkpointer
_agent_graph = None
_agent_checkpointer = None


def get_agent_graph():
    """Get or create the agent graph instance"""
    global _agent_graph, _agent_checkpointer
    if _agent_graph is None:
        logger.info("Creating agent graph for the first time...")
        try:
            _agent_graph = create_agent_graph()
            # Store checkpointer reference for state recovery
            _agent_checkpointer = _agent_graph.checkpointer
            logger.info("Agent graph created successfully")
        except Exception as e:
            logger.exception("Failed to create agent graph!")
            raise
    else:
        logger.debug("Using existing agent graph instance")
    return _agent_graph


def get_agent_checkpointer():
    """Get the checkpointer instance for state recovery"""
    global _agent_checkpointer
    if _agent_checkpointer is None:
        # Ensure graph is created first
        get_agent_graph()
    return _agent_checkpointer

