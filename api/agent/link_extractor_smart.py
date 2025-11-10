"""
Smart LLM-Based Link Extraction

Extracts relevant links from listing pages with:
- Relevance scoring
- Date detection
- Prioritization
"""

import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from bs4 import BeautifulSoup
from config import get_settings
from .llm_factory import get_smart_llm

logger = logging.getLogger(__name__)


@dataclass
class RankedLink:
    """Link with relevance metadata"""
    url: str
    anchor_text: str
    relevance_score: float  # 0.0 to 1.0
    detected_date: Optional[datetime] = None
    content_type: str = "unknown"  # thread, article, discussion


async def extract_relevant_links_with_llm(
    html: str,
    url: str,
    intent: Dict,
    max_links: int = 20
) -> List[str]:
    """
    Extract relevant links from a listing page using LLM.
    
    Returns ranked and filtered links based on:
    - Relevance to user intent
    - Time range (if dates visible)
    - Content type
    
    Args:
        html: Page HTML
        url: Page URL
        intent: User intent dict
        max_links: Maximum links to return
        
    Returns:
        List of URLs, ranked by relevance
    """
    settings = get_settings()
    
    # Extract all links first
    soup = BeautifulSoup(html, 'html.parser')
    all_links = []
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        text = a_tag.get_text(strip=True)
        
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        
        # Make absolute
        from urllib.parse import urljoin
        absolute_url = urljoin(url, href)
        
        # Get surrounding context for date detection
        parent_text = ""
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(strip=True)
        
        all_links.append({
            'url': absolute_url,
            'text': text[:150] if text else '',
            'context': parent_text[:200] if parent_text else ''
        })
    
    if not all_links:
        logger.warning("No links found on page")
        return []
    
    logger.info(f"Found {len(all_links)} total links, applying smart pre-filtering...")
    
    # SMART PRE-FILTERING: Remove obvious non-article links BEFORE sending to LLM
    def is_likely_article_link(link: dict) -> tuple[bool, int]:
        """Returns (is_likely_article, priority_score)"""
        url = link['url'].lower()
        text = (link['text'] or '').lower()
        
        # EXCLUDE obvious non-article patterns
        exclude_patterns = [
            '/login', '/signup', '/register', '/auth',
            'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
            'youtube.com', 'whatsapp', 'telegram',
            '/search', '/sitemap', '/contact', '/about', '/privacy', '/terms',
            '/subscribe', '/newsletter', '/rss', '/feed',
            'javascript:', 'mailto:', '#',
        ]
        
        # Exclude very short URLs (likely navigation)
        url_parts = url.split('/')
        if len(url_parts) <= 4 and not any(char.isdigit() for char in url):
            return False, 0  # Too short, likely navigation
        
        for pattern in exclude_patterns:
            if pattern in url or pattern in text:
                return False, 0
        
        # PRIORITIZE article-like patterns
        priority = 0
        
        # High priority: URLs with article IDs, dates, or long slugs
        if any(char.isdigit() for char in url):
            priority += 30  # Has numbers (article IDs, dates)
        
        # URL length (longer = more likely article)
        if len(url) > 100:
            priority += 25  # Very long URL
        elif len(url) > 60:
            priority += 15  # Long URL
        
        # Has meaningful link text (not just "Read more")
        if text and len(text) > 20:
            priority += 20  # Good link text
        
        # Topic relevance (if topic mentions Marico, prioritize links mentioning it)
        topic_lower = intent.get('topic', '').lower()
        if 'marico' in topic_lower:
            if 'marico' in url or 'marico' in text:
                priority += 40  # Highly relevant
        
        # Article-like URL patterns
        article_patterns = ['-', '_', 'article', 'post', 'news', 'story', 'report', 'analysis']
        for pattern in article_patterns:
            if pattern in url:
                priority += 5
        
        return True, priority  # Score not used for sorting, just for filtering threshold
    
    # Filter links (but PRESERVE ORIGINAL ORDER - listing pages are usually chronological!)
    filtered_links = []
    for link in all_links:
        is_likely, score = is_likely_article_link(link)
        if is_likely:
            filtered_links.append(link)  # Keep original order from page
    
    logger.info(f"📊 Pre-filtering: {len(all_links)} total → {len(filtered_links)} likely articles (order preserved)")
    
    # Take top candidates for LLM analysis (maintaining page order)
    links_to_analyze = filtered_links[:100]
    
    if len(links_to_analyze) == 0:
        logger.warning("⚠️ No article-like links found after filtering!")
        return []
    
    if len(filtered_links) > 100:
        logger.info(f"✂️ Sending top 100 article candidates (out of {len(filtered_links)} filtered, order preserved)")
    
    link_list = "\n".join([
        f"  {i+1}. [{link['text'][:80] or 'No text'}] → {link['url']}\n     Context: {link['context'][:100] if link['context'] else 'N/A'}"
        for i, link in enumerate(links_to_analyze)
    ])
    
    topic = intent.get('topic', '')
    target_section = intent.get('target_section', '')
    time_range_days = intent.get('time_range_days', 7)
    
    prompt = f"""Extract and rank links relevant to user intent.

USER INTENT:
- Looking for: {topic}
- Target section: {target_section or '(any)'}
- ⏰ Time range: Last {time_range_days} days {"(PRIORITIZE RECENT!)" if time_range_days <= 7 else ""}

LINKS ON PAGE:
{link_list}

TASK: Identify which links lead to INDIVIDUAL ARTICLES/CONTENT (not listing/category pages).

⏰ **DATE PRIORITIZATION (CRITICAL FOR TIME-SENSITIVE REQUESTS):**
If user wants content from last {time_range_days} days, YOU MUST:
1. Look for date indicators in Context field: "1 DAY AGO", "2 DAYS AGO", "hours ago", "Published: [date]"
2. **PRIORITIZE links with visible recent dates** - put them FIRST in your ranking
3. Rank by: RECENCY first, then relevance
4. Skip links with old dates like "1 MONTH AGO", "2 WEEKS AGO" if recent content is available

Examples in Context:
- "1 DAY AGO" → HIGH PRIORITY ✅
- "3 hours ago" → HIGH PRIORITY ✅  
- "Oct 15, 2025" → Check if within {time_range_days} days
- "2 weeks ago" → LOWER PRIORITY if recent content available

🎯 **CRITICAL: WHAT TO LOOK FOR**
✅ INCLUDE article/content links that have:
   - LONG URLs with article titles, slugs, or IDs (e.g., /news/.../marico-q2-pat-seen-up-12765223.html)
   - Specific article headlines in link text (e.g., "Marico Q2 PAT seen up 6.3%...")
   - Dates, timestamps, or article IDs in URL or context
   - Unique content identifiers (numbers, article codes)

❌ EXCLUDE navigation/section links like:
   - Short generic URLs: /news/, /business/, /companies/, /category/tech/
   - Pure section/category names without specific content
   - Homepage or directory links
   - Links ending in just category names (/)

**EXAMPLE GOOD LINKS:**
- /news/business/marico-reports-strong-q2-earnings-2024-12345.html ✅
- /articles/trade-spotlight-marico-bharat-forge-analysis ✅  
- /post/2024/10/marico-launches-new-product ✅

**EXAMPLE BAD LINKS:**
- /news/ ❌
- /news/business/ ❌
- /category/companies/ ❌
- /section/business-news/ ❌

RULES:
1. **ONLY** return links to INDIVIDUAL CONTENT (articles, posts, threads)
2. **SKIP** all navigation, category, section, or listing page links
3. Article links are typically LONGER and contain specific titles/IDs
4. **RANKING PRIORITY:** For time-sensitive requests (≤7 days), rank by RECENCY FIRST, then relevance
5. Score relevance 0.0 to 1.0 based on topic match AND recency
6. Return max {max_links} links, ranked by recency + relevance
7. Extract detected_date from context if visible (e.g., "1 DAY AGO" → calculate actual date)

OUTPUT FORMAT (JSON only, no markdown):
{{
  "links": [
    {{
      "url": "full URL from list above",
      "anchor_text": "link text",
      "relevance_score": 0.85,
      "detected_date": "YYYY-MM-DD if visible, otherwise null",
      "content_type": "thread" | "article" | "blog_post" | "press_release" | "research_report" | "event" | "discussion" | "unknown"
    }}
  ]
}}"""
    
    try:
        # Use GPT-4o for link analysis (needs reasoning)
        llm = get_smart_llm(temperature=0)  # Smart model for link selection
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown
        if response_text.startswith("```"):
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
        
        result = json.loads(response_text)
        links_data = result.get('links', [])
        
        # Log what LLM returned
        logger.info(f"🔍 LLM returned {len(links_data)} candidate links")
        if len(links_data) == 0:
            logger.warning(f"⚠️ LLM returned 0 links. Response preview: {response_text[:500]}")
        
        # Parse and filter links
        ranked_links = []
        cutoff_date = datetime.now() - timedelta(days=time_range_days)
        
        # IMPORTANT: If time_range_days is 0 (today), be lenient - dates are often not visible in links
        # Only filter if we have a detected date AND it's clearly old
        strict_time_filter = time_range_days > 1  # Only strict if looking for >1 day back
        
        for link_data in links_data:
            try:
                # Parse date if provided
                detected_date = None
                if link_data.get('detected_date'):
                    try:
                        detected_date = datetime.strptime(link_data['detected_date'], '%Y-%m-%d')
                    except Exception:
                        pass
                
                # Filter by date if detected AND we're being strict
                # For "today" queries (time_range_days=0), we can't reliably filter by date
                # since most links don't show publish dates, so we rely on LLM relevance instead
                if strict_time_filter and detected_date and detected_date < cutoff_date:
                    logger.debug(f"Skipping old link: {link_data['url'][:60]} ({detected_date.strftime('%Y-%m-%d')})")
                    continue
                
                ranked_links.append(RankedLink(
                    url=link_data['url'],
                    anchor_text=link_data.get('anchor_text', ''),
                    relevance_score=float(link_data.get('relevance_score', 0.5)),
                    detected_date=detected_date,
                    content_type=link_data.get('content_type', 'unknown')
                ))
            except Exception as e:
                logger.warning(f"Failed to parse link: {e}")
                continue
        
        # Sort by relevance
        ranked_links.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Return top N URLs
        result_urls = [link.url for link in ranked_links[:max_links]]
        
        logger.info(f"✅ Extracted {len(result_urls)} relevant links (from {len(links_data)} candidates)")
        if result_urls:
            logger.info(f"   Top link: {result_urls[0][:80]}")
        
        return result_urls
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ LLM returned invalid JSON for link extraction: {e}")
        logger.error(f"Response preview: {response_text[:500]}")
        return []
    
    except Exception as e:
        logger.error(f"❌ Link extraction failed with exception: {e}", exc_info=True)
        return []

