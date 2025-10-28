"""
AI-powered link extraction from HTML pages.

Uses GPT to intelligently identify and extract relevant article links
from web pages, eliminating the need for brittle heuristics.
"""

import json
import logging
from typing import List, Optional

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI

from config import get_settings

logger = logging.getLogger(__name__)


async def extract_article_links_with_ai(
    html: str,
    seed_url: str,
    user_prompt: str,
    max_links: int = 10
) -> List[str]:
    """
    Use AI to extract relevant article links from HTML based on user's prompt.
    
    Args:
        html: The HTML content of the page
        seed_url: The URL of the page (for context)
        user_prompt: The user's request (e.g., "Summarize recent Marico news")
        max_links: Maximum number of links to return
        
    Returns:
        List of article URLs
    """
    settings = get_settings()
    
    # Clean and simplify HTML for better token efficiency
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove scripts, styles, and other noise
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer"]):
        tag.decompose()
    
    # Extract all links with their text AND nearby date context for AI to analyze
    links_data = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        
        # Filter out obvious non-articles
        if not text or len(text) < 10:
            continue
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
            
        # Make URL absolute if needed
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(seed_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        
        # Extract date context from nearby elements (crucial for temporal intelligence!)
        date_context = None
        parent = a.parent
        if parent:
            # Look for time/date elements near the link
            for elem in parent.find_all(["time", "span", "small", "div"], limit=5):
                elem_text = elem.get_text(strip=True)
                # Check if it looks like a date
                if any(word in elem_text.lower() for word in ["ago", "hour", "day", "min", "today", "yesterday", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "2024", "2025"]):
                    date_context = elem_text
                    break
        
        links_data.append({
            "url": href,
            "text": text[:100],  # Truncate long text
            "date": date_context  # NEW: temporal context
        })
    
    if not links_data:
        logger.warning(f"No links found in HTML from {seed_url}")
        return []
    
    # Limit to first 50 links to avoid token overload
    links_data = links_data[:50]
    
    logger.info(f"Extracted {len(links_data)} candidate links, asking AI to filter...")
    
    # Prepare prompt for GPT with temporal awareness
    prompt = f"""You are an intelligent article link extractor analyzing a web page.

USER REQUEST: {user_prompt}
PAGE URL: {seed_url}
TODAY'S DATE: {__import__('datetime').datetime.now().strftime('%B %d, %Y')}

LINKS FOUND (with text and date context):
{json.dumps(links_data, indent=2)}

TASK: Extract ONLY the URLs of actual ARTICLES that match the user's request.

INTELLIGENCE RULES:
1. RELEVANCE: Article must relate to the user's topic/company/subject
2. RECENCY: Prioritize recent articles (within last 5-7 days if possible)
   - Use the "date" field to assess recency
   - "X hours ago", "today", "yesterday" = very recent (prioritize these!)
   - Specific dates should be recent (within a week)
   - If no date info, include if highly relevant
3. TYPE: Must be actual articles, NOT category/tag/navigation pages
4. QUALITY: Full articles with substantial content

INCLUDE:
✅ News articles about the topic
✅ Recent updates (look at date field!)
✅ Blog posts or detailed stories
✅ Articles with clear, informative titles

EXCLUDE:
❌ Category/tag pages
❌ Navigation links
❌ Podcast/video pages
❌ Old articles (unless nothing recent exists)
❌ Generic pages

LIMIT: Return UP TO {max_links} MOST RELEVANT and RECENT URLs.

Respond with ONLY a valid JSON array of URLs (no markdown, no explanation):
["url1", "url2", "url3"]
"""
    
    try:
        # Use gpt-4o-mini for cost efficiency (this is a simple task)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.openai_api_key
        )
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Parse JSON response
        # Handle markdown code blocks if present
        if response_text.startswith("```"):
            # Extract JSON from code block
            lines = response_text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or (not line.startswith("```")):
                    json_lines.append(line)
            response_text = "\n".join(json_lines)
        
        urls = json.loads(response_text)
        
        if not isinstance(urls, list):
            logger.error(f"AI response is not a list: {response_text}")
            return []
        
        # Filter out invalid URLs
        valid_urls = []
        for url in urls:
            if isinstance(url, str) and url.startswith("http"):
                valid_urls.append(url)
        
        logger.info(f"✅ AI extracted {len(valid_urls)} article URLs")
        return valid_urls[:max_links]
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return []
    except Exception as e:
        logger.error(f"AI link extraction failed: {e}")
        return []

