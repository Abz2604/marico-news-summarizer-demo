"""
Smart Recursive Navigation System

This is the CORE replacement for the old navigate + fetch logic.
Uses LLM decisions at each step to intelligently navigate and extract content.
"""

import logging
from typing import List, Set, Optional
from datetime import datetime

from .types import ArticleContent
from .brightdata_fetcher import fetch_url
from .page_decision import (
    analyze_and_decide,
    PageAction,
    normalize_url
)
from .content_extractor_llm import (
    extract_content_with_llm,
    validate_relevance
)
from .link_extractor_smart import extract_relevant_links_with_llm

logger = logging.getLogger(__name__)


async def smart_navigate(
    url: str,
    intent: dict,  # From UserIntent.to_dict()
    collected: List[ArticleContent],
    depth: int = 0,
    max_depth: int = 2,  # Reduced from 3: optimized for listing pages (depth 0) → articles (depth 1)
    visited: Optional[Set[str]] = None,
    emit_callback: Optional[callable] = None,
    plan: Optional[dict] = None
) -> List[ArticleContent]:
    """
    Intelligently navigate and extract content based on LLM decisions.
    
    OPTIMIZED FOR LISTING PAGES: When given a listing page at depth 0 (news, blog, forum),
    the system will prefer immediate link extraction (EXTRACT_LINKS) over navigation,
    resulting in efficient 2-level flow: Listing (depth 0) → Articles (depth 1).
    
    FALLBACK NAVIGATION: If seed URL is not a listing (e.g., homepage), NAVIGATE_TO
    is still available to find the right section before extraction begins.
    
    Args:
        url: Current URL to process
        intent: User intent dictionary
        collected: Articles collected so far
        depth: Current navigation depth (0=seed, 1=following links, 2=deep)
        max_depth: Maximum depth allowed (default: 2)
        visited: Set of visited URLs (for cycle detection)
        emit_callback: Callback for event emission
        plan: Optional navigation plan with expected_page_type for context
        
    Returns:
        Updated list of collected articles
    """
    # Initialize visited set
    if visited is None:
        visited = set()
    
    # Helper function for event emission
    def emit(event: dict):
        if emit_callback:
            try:
                emit_callback(event)
            except Exception as e:
                logger.error(f"Event callback failed: {e}")
    
    # SAFETY 1: Check exit conditions
    max_articles = intent.get('max_articles', 10)
    
    if depth >= max_depth:
        logger.info(f"⛔ Max depth ({max_depth}) reached at {url[:60]}")
        emit({"event": "nav:max_depth", "url": url, "depth": depth})
        return collected
    
    if len(collected) >= max_articles:
        logger.info(f"⛔ Collected enough articles ({len(collected)}/{max_articles})")
        emit({"event": "nav:max_articles", "collected": len(collected)})
        return collected
    
    # SAFETY 2: Cycle detection
    normalized = normalize_url(url)
    if normalized in visited:
        logger.info(f"⛔ Already visited: {url[:60]}")
        emit({"event": "nav:already_visited", "url": url})
        return collected
    
    visited.add(normalized)
    
    logger.info(f"🔍 [{depth}/{max_depth}] Navigating: {url[:80]}")
    emit({"event": "nav:visiting", "url": url, "depth": depth})
    
    # STEP 1: Fetch the page
    html = await fetch_url(url, timeout=30)
    if not html:
        logger.warning(f"❌ Failed to fetch: {url[:60]}")
        emit({"event": "nav:fetch_failed", "url": url})
        return collected
    
    # STEP 2: Analyze and decide what to do
    emit({"event": "nav:analyzing", "url": url})
    
    try:
        decision = await analyze_and_decide(
            html=html,
            url=url,
            intent=intent,
            depth=depth,
            max_depth=max_depth,
            plan=plan
        )
    except Exception as e:
        logger.error(f"Decision failed for {url[:60]}: {e}")
        emit({"event": "nav:decision_failed", "url": url, "error": str(e)})
        return collected
    
    emit({
        "event": "nav:decision",
        "url": url,
        "action": decision.action.value,
        "reasoning": decision.reasoning,
        "confidence": decision.confidence,
        "page_type": decision.page_type
    })
    
    # STEP 3: Execute decision
    
    if decision.action == PageAction.EXTRACT_CONTENT:
        # This page has content - extract with integrated date check
        logger.info(f"📄 Extracting content from: {url[:60]}")
        emit({"event": "nav:extracting_content", "url": url})
        
        try:
            # OPTIMIZED: Single LLM call extracts BOTH content AND date
            # Replaces: quick_date_check() + extract_content_with_llm()
            # Cost saving: ~25% reduction in LLM calls
            content = await extract_content_with_llm(
                html=html,
                url=url,
                page_type=decision.page_type,
                intent=intent
            )
            
            if content:
                # Validate relevance (including date check)
                emit({"event": "nav:validating_relevance", "url": url})
                is_relevant = await validate_relevance(content, intent, skip_date_check=False)
                
                if is_relevant:
                    # Convert to ArticleContent
                    article = ArticleContent(
                        url=url,
                        resolved_url=url,
                        title=content.title,
                        text=content.content,
                        fetched_at=datetime.utcnow(),
                        published_date=content.publish_date,
                        date_confidence=0.8 if content.publish_date else 0.0,
                        date_extraction_method="llm",
                        metadata=content.metadata
                    )
                    collected.append(article)
                    logger.info(f"✅ Content extracted and added ({len(collected)}/{max_articles})")
                    emit({
                        "event": "nav:content_added",
                        "url": url,
                        "title": content.title,
                        "collected_count": len(collected)
                    })
                else:
                    logger.info(f"❌ Content not relevant: {url[:60]}")
                    emit({"event": "nav:content_not_relevant", "url": url})
            else:
                logger.warning(f"❌ Content extraction returned None: {url[:60]}")
                emit({"event": "nav:extraction_failed", "url": url})
                
        except Exception as e:
            logger.error(f"Content extraction failed for {url[:60]}: {e}")
            emit({"event": "nav:extraction_error", "url": url, "error": str(e)})
    
    elif decision.action == PageAction.EXTRACT_LINKS:
        # This page lists content - extract links and recurse
        logger.info(f"🔗 Extracting links from: {url[:60]}")
        emit({"event": "nav:extracting_links", "url": url})
        
        try:
            links = await extract_relevant_links_with_llm(
                html=html,
                url=url,
                intent=intent,
                max_links=20  # Hard limit per page
            )
            
            logger.info(f"   Found {len(links)} relevant links")
            emit({"event": "nav:links_found", "url": url, "count": len(links)})
            
            # Track consecutive date filter failures for early stopping
            consecutive_date_failures = 0
            MAX_CONSECUTIVE_FAILURES = 3  # Stop if 3 articles in a row fail date filter
            
            # Recurse into each link
            for i, link in enumerate(links):
                # Safety limit: Don't exceed max_articles (this is a ceiling, not a target)
                if len(collected) >= max_articles:
                    logger.info(f"⚠️ Reached safety limit ({max_articles} articles), stopping")
                    emit({"event": "nav:max_articles_reached", "count": len(collected)})
                    break
                
                # Early stopping: If consecutive date failures, no point checking remaining old articles
                if consecutive_date_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.info(f"⏭️  Early stop: {consecutive_date_failures} consecutive date failures suggest remaining content is old")
                    emit({"event": "nav:early_stop", "reason": "consecutive_date_failures", "count": consecutive_date_failures, "collected": len(collected)})
                    break
                
                logger.info(f"   📎 [{i+1}/{len(links)}] Following: {link[:60]}")
                articles_before = len(collected)
                
                collected = await smart_navigate(
                    url=link,
                    intent=intent,
                    collected=collected,
                    depth=depth + 1,
                    max_depth=max_depth,
                    visited=visited,
                    emit_callback=emit_callback,
                    plan=plan
                )
                
                # Check if we successfully collected an article
                if len(collected) > articles_before:
                    # Success! Reset failure counter
                    consecutive_date_failures = 0
                else:
                    # No article collected (likely date filtered)
                    consecutive_date_failures += 1
        
        except Exception as e:
            logger.error(f"Link extraction failed for {url[:60]}: {e}")
            emit({"event": "nav:link_extraction_error", "url": url, "error": str(e)})
    
    elif decision.action == PageAction.NAVIGATE_TO:
        # Navigate to a specific section/link
        target = decision.target_url
        if target:
            logger.info(f"➡️  Navigating to: {target[:60]}")
            logger.info(f"   Reason: {decision.reasoning}")
            emit({
                "event": "nav:navigating_to",
                "from": url,
                "to": target,
                "reason": decision.reasoning
            })
            
            collected = await smart_navigate(
                url=target,
                intent=intent,
                collected=collected,
                depth=depth + 1,
                max_depth=max_depth,
                visited=visited,
                emit_callback=emit_callback,
                plan=plan
            )
        else:
            logger.warning(f"⚠️  NAVIGATE_TO without target_url")
            emit({"event": "nav:navigate_no_target", "url": url})
    
    else:  # PageAction.STOP
        logger.info(f"⛔ Stopping at: {url[:60]}")
        logger.info(f"   Reason: {decision.reasoning}")
        emit({"event": "nav:stopped", "url": url, "reason": decision.reasoning})
    
    return collected


async def run_smart_navigation(
    seed_urls: List[str],
    intent: dict,
    max_articles: int = 10,
    emit_callback: Optional[callable] = None,
    plan: Optional[dict] = None
) -> List[ArticleContent]:
    """
    Entry point for smart content extraction.
    
    OPTIMIZED WORKFLOW:
    - Listing pages (news, blog, forum) → Extract links immediately (depth 0 → 1)
    - Non-listing pages (homepage) → Navigate to section, then extract (depth 0 → 1 → 2)
    
    Returns whatever content matches user criteria - max_articles is just a safety ceiling.
    
    Args:
        seed_urls: List of starting URLs (ideally listing pages for optimal performance)
        intent: User intent dictionary (includes time_range, target_section, etc.)
        max_articles: Safety limit (ceiling) - won't collect more than this
        emit_callback: Optional callback for event emission
        plan: Optional navigation plan with expected_page_type for context
        
    Returns:
        List of collected ArticleContent objects that match user criteria
    """
    logger.info(f"🚀 Starting smart extraction with {len(seed_urls)} seed URL(s)")
    
    # Ensure intent has max_articles
    intent = {**intent, 'max_articles': max_articles}
    
    collected: List[ArticleContent] = []
    visited: Set[str] = set()
    
    for i, url in enumerate(seed_urls):
        logger.info(f"🌱 Processing seed URL {i+1}/{len(seed_urls)}: {url[:80]}")
        
        if emit_callback:
            emit_callback({
                "event": "nav:seed_start",
                "url": url,
                "index": i + 1,
                "total": len(seed_urls)
            })
        
        collected = await smart_navigate(
            url=url,
            intent=intent,
            collected=collected,
            depth=0,
            max_depth=2,  # Optimized: listing (0) → articles (1), or hub (0) → listing (1) → articles (2)
            visited=visited,
            emit_callback=emit_callback,
            plan=plan
        )
        
        # Check if we've hit the safety limit
        if len(collected) >= max_articles:
            logger.info(f"⚠️ Reached safety limit ({len(collected)}/{max_articles}), stopping seed processing")
            break
    
    logger.info(f"🏁 Smart extraction complete: Found {len(collected)} article(s) matching criteria")
    
    if emit_callback:
        emit_callback({
            "event": "extraction:complete",
            "collected": len(collected),
            "max_limit": max_articles
        })
    
    return collected

