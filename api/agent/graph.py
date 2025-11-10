from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional

import logging
import json

logger = logging.getLogger(__name__)
from langchain_core.prompts import ChatPromptTemplate

from config import get_settings
from .llm_factory import get_smart_llm
from .types import ArticleContent, SeedLink, SummaryResult
from .utils import extract_main_text, extract_title
from .brightdata_fetcher import fetch_url
from .intent_extractor import extract_intent
from .deduplicator import deduplicate_articles
from .smart_navigator import run_smart_navigation
from .planner import create_navigation_plan, NavigationPlan
from .reflector import reflect_on_results, ReflectionResult


class AgentState(Dict[str, Any]):
    """State container used by LangGraph."""


def _emit(state: AgentState, event: Dict[str, Any]) -> None:
    state.setdefault("logs", []).append(event)
    try:
        logging.info("agent: %s", json.dumps(event))
    except Exception:
        logging.info("agent: %s", event)
    
    # Call event callback if provided (for SSE streaming)
    event_callback = state.get("_event_callback")
    if event_callback and callable(event_callback):
        try:
            event_callback(event)
        except Exception as e:
            logging.error(f"Event callback failed: {e}")


def _needs_js_rendering(html: str, url: str) -> bool:
    """
    Detect if a page needs JavaScript rendering to show all content.
    
    Looks for indicators like:
    - "Load More" buttons
    - Infinite scroll containers
    - Dynamic content loaders
    - Known lazy-loading sites
    
    Args:
        html: Page HTML content
        url: Page URL
        
    Returns:
        True if JS rendering is likely needed
    """
    html_lower = html.lower()
    
    # Check for common lazy-loading indicators
    lazy_load_indicators = [
        'load more',
        'show more',
        'view more',
        'load-more',
        'loadmore',
        'infinite-scroll',
        'lazy-load',
        'data-lazy',
        'data-src=',  # Lazy-loaded images
        'loading="lazy"',
        '__next_data__',  # Next.js with client-side rendering
        'react-root',  # React apps
        'ng-app',  # Angular apps
    ]
    
    if any(indicator in html_lower for indicator in lazy_load_indicators):
        logger.info("🚀 Detected lazy-loading indicators in HTML")
        return True
    
    # Known sites that heavily use lazy loading
    lazy_sites = [
        'reuters.com',
        'bloomberg.com',
        'wsj.com',
        'ft.com',
        'forbes.com',
        'medium.com',
        'substack.com',
    ]
    
    if any(site in url.lower() for site in lazy_sites):
        logger.info(f"🚀 Known lazy-loading site detected: {url}")
        return True
    
    return False


async def _node_init(state: AgentState) -> AgentState:
    state["started_at"] = datetime.utcnow().isoformat()
    state.setdefault("articles", [])
    state.setdefault("logs", [])
    # Merge input payload if provided (LangGraph often wraps inputs under 'input')
    if isinstance(state.get("input"), dict):
        state.update(state["input"])  # type: ignore[index]
    _emit(state, {"event": "init", "at": state["started_at"], "seed_links_count": len(state.get("seed_links", []) or [])})
    return state


async def _node_plan(state: AgentState) -> AgentState:
    """
    PLANNING NODE: Create strategic navigation plan before acting.
    
    This is where the agent THINKS before it ACTS.
    """
    if state.get("error"):
        return state
    
    _emit(state, {"event": "plan:init"})
    
    raw_links = state.get("seed_links", [])
    seed_url = raw_links[0].url if raw_links and len(raw_links) > 0 else None
    
    if not seed_url:
        logger.warning("⚠️ No seed URL for planning, skipping plan phase")
        return state
    
    intent = state.get("intent")
    max_articles = state.get("max_articles", 10)
    
    try:
        logger.info("📋 Creating strategic navigation plan...")
        plan = await create_navigation_plan(
            seed_url=seed_url,
            user_intent=intent.to_dict() if hasattr(intent, 'to_dict') else intent,
            max_articles=max_articles
        )
        
        state["plan"] = plan
        _emit(state, {
            "event": "plan:complete",
            "strategy": plan.strategy,
            "expected_type": plan.expected_page_type,
            "confidence": plan.confidence,
            "estimated_depth": plan.estimated_depth
        })
        
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        _emit(state, {"event": "plan:error", "message": str(e)})
        # Continue without plan (graceful degradation)
    
    return state


async def _node_smart_navigate_and_fetch(state: AgentState) -> AgentState:
    """
    Smart extraction using LLM-driven decisions.
    
    OPTIMIZED FOR LISTING PAGES:
    - If seed URL is a listing (news, blog, forum) → Extract links immediately (most efficient)
    - If seed URL is not a listing (homepage) → Navigate to section, then extract (fallback)
    
    Replaced old _node_navigate + _node_fetch with intelligent extraction logic.
    """
    _emit(state, {"event": "smart_nav:init"})
    
    # Get seed links
    raw_links = state.get("seed_links", [])
    seed_urls: List[str] = []
    for item in raw_links:
        if isinstance(item, SeedLink):
            seed_urls.append(item.url)
        elif isinstance(item, dict) and item.get("url"):
            seed_urls.append(str(item.get("url")))
        elif isinstance(item, str):
            seed_urls.append(item)
    
    if not seed_urls:
        state["error"] = {"code": "no_seeds", "message": "No seed URLs provided"}
        _emit(state, {"event": "smart_nav:no_seeds"})
        return state
    
    # Get intent and max_articles
    intent = state.get("intent")
    if not intent:
        state["error"] = {"code": "no_intent", "message": "Intent not extracted"}
        _emit(state, {"event": "smart_nav:no_intent"})
        return state
    
    max_articles = state.get("max_articles", 10)
    intent_dict = intent.to_dict() if hasattr(intent, 'to_dict') else intent
    
    logger.info(f"🚀 Starting smart extraction: {len(seed_urls)} seed(s), target: {max_articles} articles")
    logger.info(f"   Optimization: Prefer direct extraction from listing pages (depth 0 → 1)")
    _emit(state, {
        "event": "smart_extraction:start",
        "seed_count": len(seed_urls),
        "max_articles": max_articles,
        "target_section": intent_dict.get('target_section', '')
    })
    
    # Run smart extraction (optimized for listing pages)
    try:
        # Create callback for event emission
        def emit_callback(event: dict):
            _emit(state, event)
        
        # Get plan if available (provides expected page type context)
        plan = state.get("plan")
        plan_dict = None
        if plan:
            if hasattr(plan, '__dict__'):
                plan_dict = {
                    'expected_page_type': getattr(plan, 'expected_page_type', None),
                    'strategy': getattr(plan, 'strategy', None)
                }
            elif isinstance(plan, dict):
                plan_dict = plan
        
        collected = await run_smart_navigation(
            seed_urls=seed_urls,
            intent=intent_dict,
            max_articles=max_articles,
            emit_callback=emit_callback,
            plan=plan_dict
        )
        
        logger.info(f"✅ Smart navigation collected {len(collected)} articles")
        
        # Deduplicate
        if len(collected) > 1:
            _emit(state, {"event": "dedup:start", "count": len(collected)})
            collected = await deduplicate_articles(collected)
            _emit(state, {"event": "dedup:complete", "unique_count": len(collected)})
        
        # Check if we got any content
        if not collected:
            intent = state.get("intent")
            time_range_days = 7  # Default
            time_range = "last_7_days"  # Default
            
            # Extract from UserIntent object (dataclass)
            if intent:
                time_range_days = getattr(intent, "time_range_days", 7)
                time_range = getattr(intent, "time_range", "last_7_days")
            
            # Create user-friendly time range message
            if time_range_days == 0:
                time_msg = "in the last 24 hours"
            elif time_range_days == 1:
                time_msg = "in the last day"
            elif time_range_days == 7:
                time_msg = "in the last 7 days"
            elif time_range_days == 30:
                time_msg = "in the last 30 days"
            else:
                time_msg = f"in the last {time_range_days} days"
            
            state["error"] = {
                "code": "no_articles",
                "message": f"No articles found {time_msg} matching your criteria. Try expanding the time range or using different search terms.",
                "time_range_days": time_range_days,
                "time_range": time_range
            }
            _emit(state, {"event": "smart_nav:no_articles"})
            return state
        
        state["articles"] = collected
        _emit(state, {"event": "smart_nav:success", "articles": len(collected)})
        
    except Exception as e:
        logger.error(f"Smart navigation failed: {e}", exc_info=True)
        state["error"] = {
            "code": "smart_nav_error",
            "message": f"Smart navigation failed: {str(e)}"
        }
        _emit(state, {"event": "smart_nav:error", "message": str(e)})
    
    return state


async def _node_reflect(state: AgentState) -> AgentState:
    """
    REFLECTION NODE: Agent evaluates its own results.
    
    This is METACOGNITION - thinking about thinking.
    Did we accomplish what user wanted?
    """
    if state.get("error"):
        return state
    
    articles = state.get("articles", [])
    if not articles:
        # Skip reflection if no articles (will be handled by summarize node)
        return state
    
    _emit(state, {"event": "reflect:init"})
    
    intent = state.get("intent")
    plan = state.get("plan")
    max_articles = state.get("max_articles", 10)
    
    try:
        logger.info("🤔 Reflecting on collected results...")
        
        # Convert plan to dict if it's an object
        plan_dict = None
        if plan:
            if hasattr(plan, '__dict__'):
                plan_dict = {
                    'strategy': getattr(plan, 'strategy', None),
                    'success_criteria': getattr(plan, 'success_criteria', {}),
                    'estimated_depth': getattr(plan, 'estimated_depth', None)
                }
            elif isinstance(plan, dict):
                plan_dict = plan
        
        reflection = await reflect_on_results(
            articles=articles,
            intent=intent.to_dict() if hasattr(intent, 'to_dict') else intent,
            plan=plan_dict,
            max_articles=max_articles
        )
        
        state["reflection"] = reflection
        _emit(state, {
            "event": "reflect:complete",
            "success": reflection.success,
            "quality_score": reflection.quality_score,
            "should_continue": reflection.should_continue,
            "gaps": len(reflection.gaps),
            "reasoning": reflection.reasoning
        })
        
        # Note: We don't auto-continue even if should_continue=true
        # That would require recursive navigation, which we skip for now
        # But the reflection is still valuable for debugging and future improvements
        
    except Exception as e:
        logger.error(f"Reflection failed: {e}")
        _emit(state, {"event": "reflect:error", "message": str(e)})
        # Continue without reflection (graceful degradation)
    
    return state


async def _node_summarize(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    settings = get_settings()
    articles = state.get("articles", [])
    if not articles:
        state["error"] = {"code": "no_content", "message": "No articles available for summarization"}
        _emit(state, {"event": "summarize:skip", "reason": "no_content"})
        return state

    # Enforce minimum articles where possible; if fewer than requested and we still have seed links,
    # attempt to gather more via search fallback before summarizing.
    min_required = min(5, state.get("max_articles", 3))
    if len(articles) < min_required:
        _emit(state, {"event": "summarize:warn", "reason": "few_articles", "count": len(articles)})

    _emit(state, {"event": "summarize:start", "articles": len(articles), "model": "gpt-4o"})
    llm = get_smart_llm(temperature=0.2)

    # Get intent for dynamic formatting
    intent = state.get("intent")
    
    # Build dynamic system prompt based on intent
    if intent:
        # Use intent to generate custom guidance
        format_guidance = intent.get_summarization_prompt_guidance()
        focus_filter = intent.get_focus_area_filter()
        
        system_prompt = f"""You are an intelligent insights analyst creating customized summaries.

USER'S OUTPUT PREFERENCE:
{format_guidance}

{focus_filter if focus_filter else 'SCOPE: Cover relevant topics such as Market Trends, Industry Dynamics, Financial Performance, Corporate Actions, Product/Innovation, Leadership, and Regulatory/Legal.'}

FORMATTING RULES:
- Use markdown headers (##) for categories (e.g., ## Market Trends, ## Industry Dynamics, ## Financial Performance)
- Each point must include citation [n] where n is the article index
- Be factual, avoid speculation; synthesize across sources when appropriate
- Clear, concise language; avoid repeating headlines

IMPORTANT: Follow the user’s output preference exactly and align to the subject (company OR industry/theme)."""
    else:
        # Fallback to default (backward compatibility)
        system_prompt = """You are an intelligent insights analyst creating article-specific summaries.

TASK: Create a summary with UNIQUE points for EACH article:
1. For each article, extract 3 KEY POINTS that are SPECIFIC to that article only
2. Each bullet must describe what's UNIQUE in that specific article (not shared themes)
3. Every point must include ONLY its own citation [n] (e.g., [1], not [1][3][5])
4. End with a 2-3 sentence executive summary synthesizing across all articles

CRITICAL RULES:
❌ FORBIDDEN: Shared bullets across multiple articles (e.g., "Trend X is popular [1][3][5]")
✅ REQUIRED: Each article gets its OWN unique bullets describing its specific content
✅ Each bullet should have ONLY ONE citation number (the article it came from)
✅ Focus on what makes each article DIFFERENT, not what they have in common

FORMAT:
## Article [1]: [Article Title]
- Unique point 1 from article [1]
- Unique point 2 from article [1]
- Unique point 3 from article [1]

## Article [2]: [Article Title]
- Unique point 1 from article [2]
- Unique point 2 from article [2]
- Unique point 3 from article [2]

**Executive Summary:** [2-3 sentences synthesizing key themes across ALL articles]

EXAMPLE (CORRECT):
## Article [1]: 32 Gel Manicure Ideas
- Features gothic window designs with burgundy and black color schemes [1]
- Includes celestial cat eye effects using magnetic gel polish [1]
- Showcases 3D embellishments with chrome accents [1]

## Article [2]: Almond Nail Ideas  
- Highlights mismatched dot patterns on almond-shaped nails [2]
- Features chocolate shimmer finishes for fall season [2]
- Demonstrates French tip variations with edgy twists [2]

EXAMPLE (WRONG - DO NOT DO THIS):
## Seasonal Trends
- November embraces autumnal colors like chocolate and plum [1][3][5] ❌ WRONG!
- Almond shapes are popular this month [2][4] ❌ WRONG!"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "human",
                "User Request: {prompt}\n\nArticles to analyze:\n{articles}\n\nCreate the summary:",
            ),
        ]
    )

    article_chunks = []
    for idx, article in enumerate(articles, start=1):
        title_part = f"Title: {article.title}\n" if article.title else ""
        # Give more content per article so AI can extract 3 meaningful points
        article_chunks.append(f"[{idx}] {title_part}URL: {article.url}\n{article.text[:3500]}")

    messages = prompt.format_messages(prompt=state.get("prompt", ""), articles="\n\n".join(article_chunks))
    try:
        response = await llm.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001
        state["error"] = {"code": "llm_error", "message": str(exc)}
        _emit(state, {"event": "summarize:error", "message": str(exc)})
        logging.exception("LLM invocation failed: %s", exc)
        return state

    # Extract bullets defensively (handle '-', '*', '•', '–', '—', and numbered lists like '1.')
    import re
    lines = [line.strip() for line in response.content.split("\n")]
    bullet_like = []
    for l in lines:
        if not l or l.startswith("##") or l.startswith("# "):
            continue
        if re.match(r"^(-|\*|•|–|—)\s+", l):
            bullet_like.append(l)
        elif re.match(r"^\d+\.[\)\.]?\s+", l):
            # convert numbered list to dash bullet
            bullet_like.append(re.sub(r"^\d+\.[\)\.]?\s+", "- ", l))
    # Fallback: collect lines containing citation markers [n] that look like points
    if not bullet_like:
        for l in lines:
            if not l or l.startswith("#"):
                continue
            if re.search(r"\[[0-9]+\]", l):
                bullet_like.append(f"- {l}" if not l.startswith("-") else l)
    bullet_points = bullet_like

    # Build citations with dates (Phase 1: Date Intelligence)
    citations = []
    for idx, article in enumerate(articles, start=1):
        citation = {
            "url": article.url,
            "label": f"[{idx}]",
            "title": article.title,
        }
        
        # Add date info if available
        if article.published_date:
            citation["date"] = article.published_date.strftime("%Y-%m-%d")
            citation["age_days"] = article.age_days
            citation["date_confidence"] = article.date_confidence
        
        citations.append(citation)
    
    summary = SummaryResult(
        summary_markdown=response.content,
        bullet_points=bullet_points,
        citations=citations,
        model=settings.openai_model,
        token_usage=getattr(response, "response_metadata", {}).get("token_usage"),
    )

    state["summary"] = summary
    _emit(state, {"event": "summarize:success", "bullets": len(bullet_points)})
    return state


async def _node_finalize(state: AgentState) -> AgentState:
    state["completed_at"] = datetime.utcnow().isoformat()
    logging.info("Agent run finalized; error=%s articles=%s", bool(state.get("error")), len(state.get("articles", [])))
    _emit(state, {"event": "finalize", "at": state["completed_at"], "error": bool(state.get("error"))})
    return state



async def run_agent(
    prompt: str, 
    seed_links: List[str], 
    max_articles: int = 10,
    event_callback: Optional[callable] = None,
    target_section: str = ""  # Explicit section override (forum, news, etc.)
) -> Optional[SummaryResult]:
    # 🎯 STEP 0: Extract User Intent (NEW in Phase 0)
    # Understand what the user wants: format, timeframe, focus areas
    intent = await extract_intent(prompt, max_articles)
    
    # Override target_section if explicitly provided
    if target_section:
        intent.target_section = target_section
        logger.info(f"🎯 Target section explicitly set to: {target_section}")
    
    logger.info(f"📋 Extracted Intent: {intent.to_dict()}")
    
    if intent.ambiguities:
        logger.warning(f"⚠️ Intent ambiguities: {intent.ambiguities}")
    
    # Use intent.max_articles if user specified, otherwise use parameter
    effective_max_articles = intent.max_articles
    
    # Direct orchestration to avoid runtime input/state plumbing issues
    state: AgentState = {
        "prompt": prompt,
        "intent": intent,  # NEW: Store intent in state
        "seed_links": [SeedLink(url=link) for link in seed_links],
        "max_articles": effective_max_articles,
        "time_cutoff": intent.get_cutoff_date(),  # NEW: For date filtering
        "_event_callback": event_callback,  # For SSE streaming
    }

    # ═══════════════════════════════════════════════════════════════════════════════
    # OPTIMIZED INTELLIGENT EXTRACTION WORKFLOW
    # ═══════════════════════════════════════════════════════════════════════════════
    # 1. INIT: Initialize state
    # 2. PLAN: Strategic extraction planning (identify listing vs non-listing)
    # 3. EXTRACT: Smart content extraction (prefer direct link extraction)
    # 4. REFLECT: Evaluate results quality (metacognition)
    # 5. SUMMARIZE: Create final output
    # 6. FINALIZE: Cleanup and logging
    #
    # OPTIMIZATION: When given listing pages (news, blog, forum), system extracts
    # links immediately (depth 0→1) instead of navigating deeper. NAVIGATE_TO remains
    # available as fallback for non-listing pages (e.g., homepage).
    # ═══════════════════════════════════════════════════════════════════════════════
    
    state = await _node_init(state)
    
    # PLANNING PHASE: Strategic extraction planning
    logger.info("📋 INTELLIGENT AGENT: Planning → Extract → Reflect → Summarize")
    state = await _node_plan(state)
    
    # EXTRACTION PHASE: Smart extraction with listing optimization
    logger.info("🧠 Executing smart extraction (LLM-driven, optimized for listings)")
    state = await _node_smart_navigate_and_fetch(state)
    
    # REFLECTION PHASE: Evaluate our own results (metacognition)
    logger.info("🤔 Reflecting on collected results...")
    state = await _node_reflect(state)
    
    # SUMMARIZATION PHASE: Create final summary
    state = await _node_summarize(state)
    
    # FINALIZATION PHASE: Cleanup
    state = await _node_finalize(state)

    if state.get("error"):
        # Return error state so router can access error details
        return state
    return state.get("summary")

