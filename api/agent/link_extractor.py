"""
AI-powered link extraction from HTML pages.

Uses GPT to intelligently identify and extract relevant article links
from web pages, eliminating the need for brittle heuristics.
"""

import json
import logging
import re
from typing import List, Optional
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from config import get_settings
from .llm_factory import get_fast_llm

logger = logging.getLogger(__name__)


def parse_listing_date(date_text: str) -> Optional[datetime]:
    """
    Parse date from listing page context.
    Handles formats like: "20 Oct 2025", "17 Oct 2025", "3 days ago", "yesterday"
    
    Returns:
        datetime if successfully parsed, None otherwise
    """
    if not date_text:
        return None
    
    text = date_text.strip().lower()
    now = datetime.now()
    
    # Handle relative dates
    if "today" in text or "hour" in text or "min" in text:
        return now
    
    if "yesterday" in text:
        return now - timedelta(days=1)
    
    # "X days ago" or "X day ago"
    days_match = re.search(r'(\d+)\s+days?\s+ago', text)
    if days_match:
        days = int(days_match.group(1))
        return now - timedelta(days=days)
    
    # "X weeks ago"
    weeks_match = re.search(r'(\d+)\s+weeks?\s+ago', text)
    if weeks_match:
        weeks = int(weeks_match.group(1))
        return now - timedelta(weeks=weeks)
    
    # Standard date formats: "20 Oct 2025", "Oct 20, 2025", "17 October 2025"
    date_patterns = [
        r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})',  # 20 Oct 2025
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})',  # Oct 20, 2025
        r'(\d{4})-(\d{2})-(\d{2})',  # 2025-10-20
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                # Handle different match group orders
                if pattern.startswith(r'(\d{1,2})'):  # Day first
                    day, month, year = match.groups()
                    month_num = datetime.strptime(month[:3].title(), '%b').month
                    return datetime(int(year), month_num, int(day))
                elif pattern.startswith(r'(jan|feb'):  # Month first
                    month, day, year = match.groups()
                    month_num = datetime.strptime(month[:3].title(), '%b').month
                    return datetime(int(year), month_num, int(day))
                elif pattern.startswith(r'(\d{4})'):  # ISO format
                    year, month, day = match.groups()
                    return datetime(int(year), int(month), int(day))
            except (ValueError, AttributeError):
                continue
    
    return None


async def extract_article_links_with_ai(
    html: str,
    seed_url: str,
    user_prompt: str,
    max_links: int = 10,
    time_range_days: int = 7
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
        
        # Filter out obvious non-articles (but be permissive!)
        if not text or len(text) < 5:  # Reduced from 10 to 5 for flexibility
            continue
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        
        # Skip obvious non-article patterns - be more aggressive to avoid branching
        href_lower = href.lower()
        skip_patterns = [
            "/tag/", "/tags/", "/category/", "/categories/", 
            "/author/", "/authors/", "/archive/", "/archives/",
            "/page/", "/pages/", "/about", "/contact",
            "javascript:", "mailto:", "tel:",
            "/login", "/signup", "/register",
            "?page=", "?category=", "?tag=",
        ]
        if any(pattern in href_lower for pattern in skip_patterns):
            continue
        
        # Skip if URL ends with just a slash or common non-article pages
        if href_lower.rstrip("/").endswith(("/news", "/blog", "/articles", "/press", "/media")):
            # These are usually listing pages, not individual articles
            continue
            
        # Make URL absolute if needed
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(seed_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        
        # Extract date context from nearby elements (crucial for temporal intelligence!)
        date_context = None
        
        # Strategy 1: Check parent and its children
        parent = a.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            # Check if parent itself contains date text
            if any(word in parent_text.lower() for word in ["ago", "hour", "day", "min", "today", "yesterday", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "2024", "2025"]):
                # Extract just the date-looking part
                for elem in parent.find_all(["time", "span", "small", "div", "p"], limit=10):
                    elem_text = elem.get_text(strip=True)
                    if elem_text and len(elem_text) < 50 and any(word in elem_text.lower() for word in ["ago", "hour", "day", "min", "today", "yesterday", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "2024", "2025"]):
                        date_context = elem_text
                        break
        
        # Strategy 2: Check siblings if not found in parent
        if not date_context:
            for sibling in a.find_next_siblings(limit=3):
                sibling_text = sibling.get_text(strip=True) if hasattr(sibling, 'get_text') else str(sibling).strip()
                if sibling_text and len(sibling_text) < 50 and any(word in sibling_text.lower() for word in ["ago", "hour", "day", "today", "yesterday", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "2024", "2025"]):
                    date_context = sibling_text
                    break
        
        links_data.append({
            "url": href,
            "text": text[:100],  # Truncate long text
            "date": date_context  # NEW: temporal context
        })
    
    if not links_data:
        logger.error(f"❌ CRITICAL: No links found in HTML from {seed_url}")
        logger.error(f"   HTML length: {len(html)} chars, <a> tags: {len(soup.find_all('a'))}")
        return []
    
    # Log how many links were found vs filtered
    total_links_found = len(soup.find_all("a", href=True))
    links_after_filter = len(links_data)
    filtered_out = total_links_found - links_after_filter
    
    if filtered_out > 0:
        logger.info(f"🔍 Filtered {filtered_out} non-article links (kept {links_after_filter} of {total_links_found} total links)")
    
    # Limit to first 100 links to avoid token overload (increased from 50)
    links_data = links_data[:100]
    
    # 🎯 SMART WORK: Pre-filter by dates from listing page BEFORE AI filtering
    # This avoids fetching articles that are clearly outside the time window
    cutoff_date = datetime.now() - timedelta(days=time_range_days)
    filtered_links = []
    no_date_links = []
    skipped_by_date = 0
    
    for link in links_data:
        if link.get("date"):
            # Try to parse the date from listing page
            parsed_date = parse_listing_date(link["date"])
            if parsed_date:
                if parsed_date >= cutoff_date:
                    filtered_links.append(link)
                else:
                    skipped_by_date += 1
                    logger.debug(f"⏰ Pre-filtered old article: {link['url'][:60]} (date: {link['date']})")
            else:
                # Date text exists but couldn't parse - include it
                no_date_links.append(link)
        else:
            # No date info - include it (will check when fetching)
            no_date_links.append(link)
    
    # Combine filtered (recent) articles + articles without dates
    links_data = filtered_links + no_date_links
    
    # Log sample date contexts for debugging
    date_samples = [link.get('date') for link in (filtered_links + no_date_links)[:5] if link.get('date')]
    if date_samples:
        logger.info(f"   📅 Sample dates found: {date_samples[:3]}")
    else:
        logger.warning(f"   ⚠️ No dates found in any links! Date extraction may not be working properly.")
    
    logger.info(f"🔍 Extracted {len(links_data)} candidate links (✅ {len(filtered_links)} recent + 📅 {len(no_date_links)} no-date, ⏰ skipped {skipped_by_date} old)")
    if skipped_by_date > 0:
        logger.info(f"   💡 Smart filtering: Avoided fetching {skipped_by_date} articles that were clearly outside time window!")
    if len(links_data) < 5:
        logger.error(f"❌ Very few candidate links found ({len(links_data)})! Page structure might be unusual or filtering too strict")
        logger.error(f"   Sample link text from page: {[a.get_text(strip=True)[:50] for a in soup.find_all('a', href=True)[:10]]}")
    
    # Dynamic recency guidance based on user's time intent
    if time_range_days <= 1:
        recency_guidance = "only from today"
    elif time_range_days <= 3:
        recency_guidance = "within last 2-3 days"
    elif time_range_days <= 7:
        recency_guidance = "within last week"
    elif time_range_days <= 14:
        recency_guidance = "within last 2 weeks"
    elif time_range_days <= 30:
        recency_guidance = "within last month"
    elif time_range_days <= 60:
        recency_guidance = "within last 2 months"
    elif time_range_days <= 90:
        recency_guidance = "within last 3 months"
    else:
        recency_guidance = "from any recent period"
    
    # Prepare prompt for GPT - SIMPLIFIED for better results
    prompt = f"""Extract article URLs from this page.

USER REQUEST: {user_prompt}
PAGE: {seed_url}

LINKS FOUND (already pre-filtered by date - only showing recent/relevant articles):
{json.dumps(links_data, indent=2)}

TASK: Return URLs that best match the user's subject (which may be a company, industry/sector, or thematic topic).

SIMPLE RULES:
1. ✅ Include articles clearly related to the user's subject (company OR industry/sector/theme). Prefer subject-aligned links over generic ones.
2. ✅ Prefer article/story pages over listing/category pages unless the link text is an article title.
3. ❌ Exclude: navigation-only pages, pure tag hubs without article content, video/podcast pages.

Be GENEROUS but relevant — links are already date-filtered. Focus on topical alignment.
Return up to {max_links} URLs.

Respond with ONLY a JSON array:
["url1", "url2", "url3"]
"""
    
    try:
        # Use Azure OpenAI pipeline via llm_factory
        llm = get_fast_llm(temperature=0)
        
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
        
        result = valid_urls[:max_links]
        logger.info(f"✅ AI filtered {len(links_data)} candidates → {len(valid_urls)} article URLs (returning {len(result)})")
        
        # Log sample URLs for debugging
        if len(result) > 0:
            sample_urls = [url.split('/')[-1] or url.split('/')[-2] for url in result[:3]]
            logger.debug(f"   Sample article URLs: {sample_urls}")
        
        if len(result) == 0:
            logger.error(f"❌ CRITICAL: AI returned 0 article links!")
            logger.error(f"   User prompt: {user_prompt[:100]}")
            logger.error(f"   Time range: {time_range_days} days ({recency_guidance})")
            logger.error(f"   AI raw response: {response_text[:500]}")
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return []
    except Exception as e:
        logger.error(f"AI link extraction failed: {e}")
        return []

