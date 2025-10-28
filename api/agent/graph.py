from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional

import logging
import json
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
from .newsapi_fallback import get_company_news, extract_company_from_url


class AgentState(Dict[str, Any]):
    """State container used by LangGraph."""


def _emit(state: AgentState, event: Dict[str, Any]) -> None:
    state.setdefault("logs", []).append(event)
    try:
        logging.info("agent: %s", json.dumps(event))
    except Exception:
        logging.info("agent: %s", event)


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

    for link in links:
        current_url = link.url
        _emit(state, {"event": "nav:fetching_seed", "url": current_url})
        
        # 🔍 STEP 0: Extract Context (What are we looking for?)
        context = extract_context_from_url_and_prompt(current_url, prompt)
        _emit(state, {
            "event": "nav:context_extracted",
            "company": context.get("company"),
            "topic": context.get("topic"),
            "is_specific": context.get("is_specific")
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
        article_urls = await extract_article_links_with_ai(
            html=html,
            seed_url=current_url,
            user_prompt=prompt,
            max_links=max_articles
        )
        
        if article_urls:
            _emit(state, {"event": "nav:extraction_success", "url": current_url, "found": len(article_urls)})
            for art_url in article_urls:
                if art_url not in expanded_urls:
                    expanded_urls.append(art_url)
                    _emit(state, {"event": "nav:article_link", "url": art_url})
        else:
            _emit(state, {"event": "nav:no_links_found", "url": current_url})
            # Fallback: add current URL itself if AI found nothing
            if current_url not in expanded_urls:
                expanded_urls.append(current_url)

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
    collected: List[ArticleContent] = []

    expanded_urls: List[str] = state.get("expanded_urls") or []
    if not expanded_urls:
        # fallback to raw links
        for link in links:
            expanded_urls.append(link.url)

    for url in expanded_urls:
        # Skip obvious listing pages to avoid summarizing restricted/index pages
        try:
            if "moneycontrol.com" in url and "/company-article/" in url and "/news" in url:
                _emit(state, {"event": "fetch:skip", "url": url, "reason": "listing_url"})
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
        if len(text or "") < 300:
            _emit(state, {"event": "fetch:skip", "url": url, "reason": "short_content"})
            continue
        collected.append(
            ArticleContent(
                url=url,
                resolved_url=url,
                title=title,
                text=text,
                fetched_at=datetime.utcnow(),
            )
        )
        _emit(state, {"event": "fetch:success", "url": url})
        if len(collected) >= max_articles:
            break

    state["articles"] = collected
    if not collected:
        # Try NewsAPI FIRST before falling back to seed page
        # (seed pages are often listing pages with low-quality content)
        _emit(state, {"event": "fetch:trying_newsapi_fallback"})
        seeds: List[str] = [l.url for l in links if isinstance(l, SeedLink)]
        
        for seed_url in seeds:
            try:
                company = await extract_company_from_url(seed_url)
                if company:
                    _emit(state, {"event": "fetch:newsapi_company", "company": company})
                    newsapi_articles = await get_company_news(
                        company_name=company,
                        max_articles=max_articles,
                        days_back=7,
                    )
                    if newsapi_articles:
                        collected.extend(newsapi_articles)
                        _emit(state, {
                            "event": "fetch:newsapi_success",
                            "company": company,
                            "articles": len(newsapi_articles)
                        })
                        break
            except Exception as exc:  # noqa: BLE001
                _emit(state, {"event": "fetch:newsapi_error", "reason": str(exc)})
        
        # If NewsAPI also fails, return empty (no more fallbacks)
        # Bright Data should have worked - if not, user needs to check API key

    # Final check: if nothing collected, set error state
    if not collected:
        state["error"] = {
            "code": "no_articles",
            "message": "Could not extract articles from the provided URL. Please check the URL or try a different source."
        }
        _emit(state, {"event": "fetch:no_articles"})
        return state
    
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

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", """You are an intelligent executive analyst creating structured, categorized summaries.

TASK: Create a comprehensive summary with these requirements:
1. Extract 3 KEY POINTS from EACH article (not 3 total - 3 per article!)
2. Organize points by CATEGORY (Financial Performance, Market Activity, Corporate Actions, Strategic Initiatives, etc.)
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
✅ Every point cited"""),
            (
                "human",
                "User Request: {prompt}\n\nArticles to analyze:\n{articles}\n\nCreate the categorized summary:",
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

    # Extract bullets defensively (some models return markdown without strict dashes)
    lines = [line.strip() for line in response.content.split("\n")]
    bullet_points = [l if l.startswith("-") else f"- {l}" for l in lines if l and (l.startswith("-") or l.startswith("*") or l.startswith("•"))]

    summary = SummaryResult(
        summary_markdown=response.content,
        bullet_points=bullet_points,
        citations=[{"url": article.url, "label": f"[{idx}]"} for idx, article in enumerate(articles, start=1)],
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


async def run_agent(prompt: str, seed_links: List[str], max_articles: int = 3) -> Optional[SummaryResult]:
    # Direct orchestration to avoid runtime input/state plumbing issues
    state: AgentState = {
        "prompt": prompt,
        "seed_links": [SeedLink(url=link) for link in seed_links],
        "max_articles": max_articles,
    }

    state = await _node_init(state)
    state = await _node_navigate(state)
    state = await _node_fetch(state)
    state = await _node_summarize(state)
    state = await _node_finalize(state)

    if state.get("error"):
        return None
    return state.get("summary")

