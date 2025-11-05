from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional

import logging
import json

logger = logging.getLogger(__name__)
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph

from config import get_settings
from .types import ArticleContent, SeedLink, SummaryResult
from .utils import extract_main_text, extract_title
from .brightdata_fetcher import fetch_url
from .link_extractor import extract_article_links_with_ai
from .page_analyzer import analyze_page_for_content
from .context_extractor import extract_context_from_url_and_prompt, validate_page_relevance
from .context_extractor_llm import extract_context_with_llm
from .intent_extractor import extract_intent
from .date_parser import extract_article_date
from .content_validator import validate_content
from .deduplicator import deduplicate_articles


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


async def _node_navigate(state: AgentState) -> AgentState:
    """
    2-Step Intelligent Navigation Agent:
    Step 1: Analyze page to understand what it is and if navigation is needed
    Step 2: Extract relevant article links using AI based on user prompt
    """
    _emit(state, {"event": "nav:init"})
    raw_links = state.get("seed_links", [])
    links: List[SeedLink] = []
    for item in raw_links:
        if isinstance(item, SeedLink):
            links.append(item)
        elif isinstance(item, dict) and item.get("url"):
            links.append(SeedLink(url=str(item.get("url"))))
        elif isinstance(item, str):
            links.append(SeedLink(url=item))

    expanded_urls: List[str] = []
    max_articles: int = state.get("max_articles", 3)
    prompt = state.get("prompt", "")
    
    logger.info(f"🌐 Navigate node: Processing {len(links)} seed link(s), max_articles={max_articles}")

    for idx, link in enumerate(links, 1):
        current_url = link.url
        logger.info(f"🔗 Processing seed link {idx}/{len(links)}: {current_url}")
        _emit(state, {"event": "nav:fetching_seed", "url": current_url})
        
        # 🔍 STEP 0: Extract Context (What are we looking for?)
        # Use LLM-based universal extraction (works for ANY site)
        try:
            context = await extract_context_with_llm(current_url, prompt)
            logger.info(f"✅ LLM context extraction: {context}")
        except Exception as e:
            logger.warning(f"LLM context extraction failed, using fallback: {e}")
            # Fallback to rule-based extraction
            context = extract_context_from_url_and_prompt(current_url, prompt)
        
        _emit(state, {
            "event": "nav:context_extracted",
            "company": context.get("company"),
            "topic": context.get("topic"),
            "is_specific": context.get("is_specific"),
            "source_type": context.get("source_type", "unknown"),
            "confidence": context.get("confidence", "medium")
        })
        
        # Fetch the seed page
        html = await fetch_url(current_url, timeout=30)
        if not html:
            _emit(state, {"event": "nav:fetch_failed", "url": current_url})
            # Fallback: add seed URL itself
            expanded_urls.append(current_url)
            continue
        
        # 🧠 STEP 1: Intelligent Page Analysis (with context!)
        _emit(state, {"event": "nav:analyzing", "url": current_url})
        analysis = await analyze_page_for_content(
            html=html,
            page_url=current_url,
            user_prompt=prompt,
            context=context
        )
        
        _emit(state, {
            "event": "nav:analysis_complete",
            "url": current_url,
            "page_type": analysis.page_type,
            "needs_navigation": analysis.needs_navigation,
            "ready_to_extract": analysis.ready_to_extract_links,
            "summary": analysis.analysis_summary
        })
        
        # 🎯 If page IS an article itself, use it directly (skip link extraction)
        if analysis.page_type == "article" and not analysis.needs_navigation:
            _emit(state, {
                "event": "nav:direct_article",
                "url": current_url,
                "reason": "Page is a single article, using directly"
            })
            # Use this seed page directly as the article source
            expanded_urls.append(current_url)
            logger.info(f"✅ Using seed page as article directly: {current_url}")
            continue  # Skip link extraction for direct articles
        
        # If AI says we need to navigate to a better page, do it (one hop)
        if analysis.needs_navigation and analysis.navigation_link:
            _emit(state, {
                "event": "nav:navigating",
                "from": current_url,
                "to": analysis.navigation_link,
                "reason": analysis.navigation_reason
            })
            
            # Fetch the navigation target
            nav_html = await fetch_url(analysis.navigation_link, timeout=30)
            if nav_html:
                # ✅ VALIDATE: Did we land on the right page?
                validation = validate_page_relevance(nav_html, analysis.navigation_link, context)
                _emit(state, {
                    "event": "nav:validation",
                    "url": analysis.navigation_link,
                    "is_relevant": validation["is_relevant"],
                    "confidence": validation["confidence"],
                    "reason": validation["reason"]
                })
                
                if validation["is_relevant"]:
                    # ✅ Good navigation - use this page
                    current_url = analysis.navigation_link
                    html = nav_html
                    _emit(state, {"event": "nav:navigation_success", "url": current_url})
                else:
                    # ⚠️ Bad navigation - stay on original page
                    _emit(state, {
                        "event": "nav:navigation_rejected",
                        "url": analysis.navigation_link,
                        "reason": validation["reason"]
                    })
                    # Continue with original page (don't update html/current_url)
            else:
                _emit(state, {"event": "nav:navigation_failed", "url": analysis.navigation_link})
                # Continue with original page
        
        # 🔗 STEP 2: AI-Powered Link Extraction (fully prompt-aware)
        _emit(state, {"event": "nav:extracting_links", "url": current_url})
        
        # Get time range from intent for date-aware link filtering
        intent = state.get("intent")
        time_range_days = intent.time_range_days if intent else 7
        
        article_urls = await extract_article_links_with_ai(
            html=html,
            seed_url=current_url,
            user_prompt=prompt,
            max_links=max_articles,
            time_range_days=time_range_days
        )
        
        logger.info(f"🔗 Link extraction found {len(article_urls)} article links (max: {max_articles}, time window: {time_range_days} days)")
        if len(article_urls) > 0:
            logger.info(f"   📋 Extracted URLs: {article_urls[:5]}")  # Log first 5 URLs
        else:
            logger.error(f"❌ ZERO links extracted from news_listing page! This is wrong.")
        
        # 🚀 NEW: Smart JS rendering for lazy-loaded content
        # If we got very few links AND page has "load more" indicators, retry with JS
        if len(article_urls) < 5 and _needs_js_rendering(html, current_url):
            _emit(state, {
                "event": "nav:js_rendering_needed",
                "url": current_url,
                "reason": "Detected lazy-loaded content (Load More button)",
                "initial_links": len(article_urls)
            })
            logger.info(f"🚀 Retrying with JS rendering for lazy-loaded content: {current_url}")
            
            # Re-fetch with JS rendering enabled
            html_js = await fetch_url(current_url, timeout=60, render_js=True)
            if html_js and len(html_js) > len(html):
                logger.info(f"✅ JS rendering added {len(html_js) - len(html):,} bytes of content")
                _emit(state, {
                    "event": "nav:js_rendering_success",
                    "url": current_url,
                    "html_growth": len(html_js) - len(html)
                })
                
                # Re-extract links from JS-rendered HTML
                article_urls_js = await extract_article_links_with_ai(
                    html=html_js,
                    seed_url=current_url,
                    user_prompt=prompt,
                    max_links=max_articles,
                    time_range_days=time_range_days
                )
                
                if len(article_urls_js) > len(article_urls):
                    logger.info(f"✅ JS rendering found {len(article_urls_js) - len(article_urls)} more links!")
                    article_urls = article_urls_js
                    html = html_js  # Use JS-rendered HTML going forward
                    _emit(state, {
                        "event": "nav:js_rendering_improved",
                        "url": current_url,
                        "new_links": len(article_urls_js),
                        "improvement": len(article_urls_js) - len(article_urls)
                    })
        
        if article_urls:
            _emit(state, {"event": "nav:extraction_success", "url": current_url, "found": len(article_urls)})
            before_count = len(expanded_urls)
            for art_url in article_urls:
                if art_url not in expanded_urls:
                    expanded_urls.append(art_url)
                    _emit(state, {"event": "nav:article_link", "url": art_url})
            added_count = len(expanded_urls) - before_count
            logger.info(f"   ➕ Added {added_count} new URLs to expanded_urls (total now: {len(expanded_urls)}, {len(article_urls) - added_count} were duplicates)")
        else:
            _emit(state, {"event": "nav:no_links_found", "url": current_url})
            # Fallback: add current URL itself if AI found nothing
            if current_url not in expanded_urls:
                expanded_urls.append(current_url)
                logger.warning(f"   ⚠️ No article links found, using seed URL itself as fallback")

    logger.info(f"🏁 Navigate complete: {len(expanded_urls)} total URLs collected for fetching")
    state["expanded_urls"] = expanded_urls
    return state

async def _node_fetch(state: AgentState) -> AgentState:
    raw_links = state.get("seed_links", [])
    links: List[SeedLink] = []
    for item in raw_links:
        try:
            if isinstance(item, SeedLink):
                links.append(item)
            elif isinstance(item, dict) and item.get("url"):
                links.append(SeedLink(url=str(item.get("url")), depth_limit=int(item.get("depth_limit", 0) or 0)))
            elif isinstance(item, str):
                links.append(SeedLink(url=item))
        except Exception:  # noqa: BLE001
            continue
    try:
        logging.info("agent: %s", json.dumps({"event": "fetch:init", "seed_link_count": len(links)}))
    except Exception:
        logging.info("agent: fetch:init seed_link_count=%s", len(links))
    max_articles: int = state.get("max_articles", 3)
    time_cutoff = state.get("time_cutoff")
    collected: List[ArticleContent] = []
    skipped_by_date = 0
    skipped_by_quality = 0
    
    if time_cutoff:
        logger.info(f"⏰ Time filtering enabled: articles must be after {time_cutoff.strftime('%Y-%m-%d')}")

    expanded_urls: List[str] = state.get("expanded_urls") or []
    if not expanded_urls:
        # fallback to raw links
        for link in links:
            expanded_urls.append(link.url)
    
    # 🎯 SMART WORK: Don't try to fetch more URLs than we need
    # Limit to a reasonable buffer above max_articles
    # For time-focused queries, max_articles might be 20, but we still want to limit fetches
    # Use a smaller multiplier to avoid fetching too many
    buffer_size = min(5, max(3, max_articles // 4))  # Buffer: 25% of max_articles, min 3, max 5
    fetch_limit = min(len(expanded_urls), max_articles + buffer_size)
    
    if len(expanded_urls) > fetch_limit:
        logger.info(f"💡 Smart limiting: Will fetch {fetch_limit} of {len(expanded_urls)} extracted articles (max_articles={max_articles}, buffer={buffer_size})")
        expanded_urls = expanded_urls[:fetch_limit]
    else:
        logger.info(f"📊 Fetch plan: {len(expanded_urls)} articles to fetch (max_articles={max_articles}, all URLs within limit)")
    
    # Emit event at START of fetch phase so UI doesn't look stuck
    if expanded_urls:
        _emit(state, {"event": "fetch:phase_start", "total_urls": len(expanded_urls), "max_articles": max_articles})
        logger.info(f"📥 Starting fetch phase: {len(expanded_urls)} articles to fetch (need {max_articles}, will stop early if enough collected)")

    for idx, url in enumerate(expanded_urls):
        # 🎯 EARLY EXIT: Stop if we have enough articles
        if len(collected) >= max_articles:
            remaining = len(expanded_urls) - idx
            logger.info(f"✅ Collected enough articles ({len(collected)}/{max_articles}), stopping fetch early (skipped {remaining} URLs)")
            _emit(state, {"event": "fetch:early_exit", "collected": len(collected), "max": max_articles, "remaining": remaining})
            break
        
        # Skip obvious listing pages (generic check based on URL patterns)
        try:
            # Skip if URL looks like a listing/category page
            if any(pattern in url.lower() for pattern in ["/category/", "/categories/", "/tags/", "/tag/"]):
                if url.endswith("/") or url.endswith(".html"):
                    _emit(state, {"event": "fetch:skip", "url": url, "reason": "listing_page"})
                    continue
        except Exception:
            pass
        _emit(state, {"event": "fetch:start", "url": url})
        # Fetch using Bright Data Web Unlocker
        _emit(state, {"event": "fetch:brightdata_start", "url": url})
        html = await fetch_url(url, timeout=30)
        if not html:
            _emit(state, {"event": "fetch:error", "url": url, "reason": "fetch_failed"})
            continue
        text = extract_main_text(html)
        title = extract_title(html)
        _emit(state, {"event": "extract:length", "url": url, "length": len(text or "")})
        
        # Validate content quality (Phase 2: Content Quality)
        quality = await validate_content(text, url)
        
        if not quality.is_valid:
            skipped_by_quality += 1
            _emit(state, {
                "event": "fetch:skip",
                "url": url,
                "reason": "quality_issues",
                "issues": quality.issues,
                "is_paywall": quality.is_paywall
            })
            continue
        
        # Extract publish date (Phase 1: Date Intelligence)
        published_date, date_confidence, date_method = await extract_article_date(html, url)
        
        if published_date:
            _emit(state, {
                "event": "date:extracted",
                "url": url,
                "date": published_date.strftime("%Y-%m-%d"),
                "confidence": date_confidence,
                "method": date_method
            })
            
            # Validate against time cutoff (if present)
            time_cutoff = state.get("time_cutoff")
            if time_cutoff and published_date < time_cutoff:
                age_days = (datetime.now() - published_date).days
                skipped_by_date += 1
                logger.info(f"⏰ Article too old: {url[:60]}... ({age_days} days old, cutoff: {time_cutoff.strftime('%Y-%m-%d')})")
                _emit(state, {
                    "event": "fetch:skip",
                    "url": url,
                    "reason": "too_old",
                    "age_days": age_days,
                    "cutoff_date": time_cutoff.strftime("%Y-%m-%d")
                })
                continue
        else:
            logger.info(f"📅 No date found for {url[:60]}... - including anyway (will sort by fetch time)")
            _emit(state, {"event": "date:not_found", "url": url})
        
        collected.append(
            ArticleContent(
                url=url,
                resolved_url=url,
                title=title,
                text=text,
                fetched_at=datetime.utcnow(),
                published_date=published_date,
                date_confidence=date_confidence,
                date_extraction_method=date_method,
            )
        )
        _emit(state, {"event": "fetch:success", "url": url})
        if len(collected) >= max_articles:
            break

    # Deduplicate articles (Phase 2: Content Quality)
    before_dedup = len(collected)
    if len(collected) > 1:
        _emit(state, {"event": "dedup:start", "count": len(collected)})
        collected = await deduplicate_articles(collected)
        _emit(state, {"event": "dedup:complete", "unique_count": len(collected)})
    
    # Log filtering summary
    logger.info(f"📊 Fetch summary: {len(collected)} articles collected, {skipped_by_date} skipped (too old), {skipped_by_quality} skipped (quality), {before_dedup - len(collected)} duplicates removed")
    
    # Final check: if nothing collected, try seed page as fallback
    if not collected:
        _emit(state, {"event": "fetch:fallback_to_seed", "reason": "No articles found via navigation"})
        logger.warning("⚠️ No articles collected, attempting seed page fallback")
        
        # Try using original seed links as articles
        for seed_link in links:
            if len(collected) >= max_articles:
                break
            
            try:
                _emit(state, {"event": "fetch:fallback_attempt", "url": seed_link.url})
                html = await fetch_url(seed_link.url, timeout=30)
                if not html:
                    continue
                
                text = extract_main_text(html)
                title = extract_title(html)
                
                # Basic validation
                if len(text or "") < 300:
                    logger.info(f"Seed page too short: {seed_link.url}")
                    continue
                
                # Validate content quality
                quality = await validate_content(text, seed_link.url)
                if not quality.is_valid:
                    logger.info(f"Seed page failed quality check: {seed_link.url}")
                    continue
                
                # Extract date
                published_date, date_confidence, date_method = await extract_article_date(html, seed_link.url)
                
                # Check time cutoff if present
                time_cutoff = state.get("time_cutoff")
                if time_cutoff and published_date and published_date < time_cutoff:
                    logger.info(f"Seed page outside time window: {seed_link.url}")
                    continue
                
                # Use seed page as article
                collected.append(
                    ArticleContent(
                        url=seed_link.url,
                        resolved_url=seed_link.url,
                        title=title,
                        text=text,
                        fetched_at=datetime.utcnow(),
                        published_date=published_date,
                        date_confidence=date_confidence,
                        date_extraction_method=date_method,
                    )
                )
                _emit(state, {"event": "fetch:fallback_success", "url": seed_link.url})
                logger.info(f"✅ Successfully used seed page as fallback: {seed_link.url}")
                
            except Exception as e:
                logger.error(f"Seed page fallback failed for {seed_link.url}: {e}")
                continue
        
        # If still nothing, return error
        if not collected:
            state["error"] = {
                "code": "no_articles",
                "message": "Could not extract usable content from the provided URL. The page may not contain articles or may be behind a paywall."
            }
            _emit(state, {"event": "fetch:no_articles"})
            return state
        else:
            logger.info(f"✅ Seed page fallback succeeded: {len(collected)} articles")
            _emit(state, {"event": "fetch:fallback_complete", "count": len(collected)})
    
    state["articles"] = collected
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

    _emit(state, {"event": "summarize:start", "articles": len(articles), "model": settings.openai_model})
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)

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
        system_prompt = """You are an intelligent insights analyst creating structured, categorized summaries.

TASK: Create a comprehensive summary with these requirements:
1. Extract 3 KEY POINTS from EACH article (not 3 total - 3 per article!)
2. Organize points by CATEGORY such as Market Trends, Industry Dynamics, Financial Performance, Market Activity, Corporate Actions, Products/Innovation, Leadership Changes, Regulatory/Legal
3. Each point must include citation [n] where n is the article index
4. End with a 2-3 sentence executive summary

FORMAT:
## [Category Name]
- Point from article [1]
- Point from article [2]

## [Another Category]
- Point from article [1]
- Point from article [3]

**Executive Summary:** [2-3 sentences synthesizing key themes]

RULES:
✅ 3 points per article minimum
✅ Factual, no speculation
✅ Clear categories
✅ Every point cited
✅ Align categories to the subject (company OR industry/theme)"""

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


def build_agent_graph():
    # Retained for future use; not used in Phase 0 orchestration
    graph = StateGraph(AgentState)
    graph.add_node("init", _node_init)
    graph.add_node("fetch", _node_fetch)
    graph.add_node("summarize", _node_summarize)
    graph.add_node("finalize", _node_finalize)

    graph.set_entry_point("init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "summarize")
    graph.add_edge("summarize", "finalize")

    return graph.compile()


async def run_agent(
    prompt: str, 
    seed_links: List[str], 
    max_articles: int = 10,  # Increased from 3 to allow more articles within time window
    event_callback: Optional[callable] = None
) -> Optional[SummaryResult]:
    # 🎯 STEP 0: Extract User Intent (NEW in Phase 0)
    # Understand what the user wants: format, timeframe, focus areas
    intent = await extract_intent(prompt, max_articles)
    
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

    state = await _node_init(state)
    state = await _node_navigate(state)
    state = await _node_fetch(state)
    state = await _node_summarize(state)
    state = await _node_finalize(state)

    if state.get("error"):
        return None
    return state.get("summary")

