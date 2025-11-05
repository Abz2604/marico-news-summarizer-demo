"""
Intelligent Page Analyzer Agent

Analyzes web pages to understand their content and determine
the best course of action for extracting relevant information.
"""

import json
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import get_settings

logger = logging.getLogger(__name__)


class PageAnalysis(BaseModel):
    """Result of page analysis"""
    page_type: str  # e.g., "news_listing", "company_profile", "homepage", "article"
    has_relevant_content: bool
    needs_navigation: bool
    navigation_link: Optional[str] = None
    navigation_reason: Optional[str] = None
    ready_to_extract_links: bool
    analysis_summary: str
    confidence: str  # "high", "medium", "low"


async def analyze_page_for_content(
    html: str,
    page_url: str,
    user_prompt: str,
    context: dict = None
) -> PageAnalysis:
    """
    Intelligent page analysis to determine what action to take.
    
    Args:
        html: The HTML content of the page
        page_url: The URL of the page being analyzed
        user_prompt: What the user is looking for (e.g., "Marico news summaries")
        
    Returns:
        PageAnalysis object with recommendations
    """
    settings = get_settings()
    
    # Extract links for potential navigation
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove noise
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    
    # Get page title
    title = soup.find("title")
    page_title = title.get_text(strip=True) if title else "No title"
    
    # Extract potential navigation links (limited for token efficiency)
    nav_links = []
    for a in soup.find_all("a", href=True)[:60]:  # First 60 links (improve recall)
        href = a.get("href", "")
        text = a.get_text(strip=True)
        
        if not text or len(text) < 3:
            continue
        if href.startswith("#") or href.startswith("javascript:"):
            continue
            
        # Make absolute
        if href.startswith("/"):
            parsed = urlparse(page_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        
        # Only include if looks like navigation
        lower_text = text.lower()
        lower_href = href.lower()
        if any(keyword in lower_text for keyword in ["news", "press", "media", "blog", "article", "stories", "updates"]) or any(
            kw in lower_href for kw in ["news", "press", "newsroom", "company-article", "/media/"]
        ):
            nav_links.append({"text": text[:50] if text else href[:50], "url": href})
    
    # Get a sample of page text for context
    body_text = soup.get_text(separator=" ", strip=True)
    # Take first 1500 chars for analysis
    body_sample = body_text[:1500] if body_text else "No text content"
    
    # Build context-aware prompt
    context_info = ""
    if context and context.get("is_specific") and context.get("company"):
        company = context["company"]
        context_info = f"""
⚠️ CRITICAL CONTEXT:
- User is looking for news about: **{company}**
- Current page type: {context.get('context_type', 'unknown')}
- This is a SPECIFIC company search, not general news!

NAVIGATION PRIORITY (most important to least):
1. Links containing "{company}" (e.g., "News on {company}", "{company} Updates")
2. Company-specific news sections (avoid generic "News" or "World News")
3. Tags/categories specifically for {company}
4. AVOID: General news sections, world news, breaking news (unless they mention {company})
"""
    
    # Build prompt for AI
    prompt = f"""You are an intelligent web page analyzer helping to extract relevant, recent content.

USER REQUEST: {user_prompt}
TODAY'S DATE: {__import__('datetime').datetime.now().strftime('%B %d, %Y')}
{context_info}

PAGE INFORMATION:
URL: {page_url}
Title: {page_title}

NAVIGATION LINKS FOUND:
{json.dumps(nav_links, indent=2)}

PAGE CONTENT SAMPLE (first 1500 chars):
{body_sample}

TASK: Analyze this page and determine the best action.
FOCUS: The user wants RECENT content (last 5-7 days ideally). Consider temporal relevance and SUBJECT alignment.
SUBJECT ALIGNMENT:
- If the subject is a specific company, prefer company-specific news/press/media sections that mention the company explicitly.
- If the subject is an industry/sector/theme, prefer pages or sections aligned to that topic (e.g., "industry", "sector", "market", "insights", "analysis", "theme"), not generic homepages.

Respond with ONLY a valid JSON object (no markdown, no explanation, double quotes only):
{{
  "page_type": "<one of: homepage, company_profile, news_listing, article, category_page, search_results, other>",
  "has_relevant_content": <true if this page contains or links to content matching user request>,
  "needs_navigation": <true if we should click a link to get to better content>,
  "navigation_link": "<full URL to navigate to, or null>",
  "navigation_reason": "<why we should navigate there, or null>",
  "ready_to_extract_links": <true if this page has article links we can extract NOW>,
  "analysis_summary": "<brief explanation of what this page is and why you made this decision>",
  "confidence": "<high, medium, or low>"
}}

CRITICAL DECISION RULES (follow in order):

1. **Company profile / stock quote pages**: If page_type is "company_profile" or "homepage" and ANY link contains "news", "press", "media", "newsroom", or "company-article", you MUST set needs_navigation=true and navigation_link to that URL. Do NOT extract from these pages directly.

2. **News listing pages**: If page_type is "news_listing" or "category_page" with many article links visible, set ready_to_extract_links=true and needs_navigation=false.

3. **Single articles**: If page_type is "article", set ready_to_extract_links=false and needs_navigation=false (will be handled separately).

4. **Fallback**: If unsure and navigation links exist with "news/press/media", prefer navigation over extraction.

5. navigation_link must be a COMPLETE URL from the NAVIGATION LINKS list above
"""
    
    try:
        model_name = settings.page_analyzer_model or settings.openai_model or "gpt-4o-mini"
        llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=settings.openai_api_key
        )
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            response_text = "\n".join(json_lines)
        
        # Parse JSON
        analysis_dict = json.loads(response_text)
        analysis = PageAnalysis(**analysis_dict)
        
        logger.info(f"✅ Page analysis complete: {analysis.page_type}, ready_to_extract={analysis.ready_to_extract_links}, needs_nav={analysis.needs_navigation}")
        return analysis
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        # Return a safe fallback
        return PageAnalysis(
            page_type="unknown",
            has_relevant_content=False,
            needs_navigation=False,
            ready_to_extract_links=True,  # Try to extract anyway
            analysis_summary="Failed to analyze page, will attempt extraction",
            confidence="low"
        )
    except Exception as e:
        logger.error(f"Page analysis failed: {e}")
        return PageAnalysis(
            page_type="unknown",
            has_relevant_content=False,
            needs_navigation=False,
            ready_to_extract_links=True,
            analysis_summary=f"Analysis error: {str(e)}",
            confidence="low"
        )

