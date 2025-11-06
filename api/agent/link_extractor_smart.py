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
from langchain_openai import ChatOpenAI
from config import get_settings

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
    
    logger.info(f"Found {len(all_links)} total links, analyzing with LLM...")
    
    # Build link list for LLM (truncate if too many to avoid overwhelming the LLM)
    # Limit to 100 links for better LLM performance
    links_to_analyze = all_links[:100]
    if len(all_links) > 100:
        logger.info(f"⚠️ Truncating from {len(all_links)} to 100 links for LLM analysis")
    
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
- Time range preference: Last {time_range_days} days (but include relevant links even if date is unclear)

LINKS ON PAGE:
{link_list}

TASK: Identify which links lead to relevant content.

IMPORTANT: Focus primarily on RELEVANCE to the user's intent and target section. 
Include links that seem relevant even if you cannot determine their publication date.

RULES:
1. Return links to INDIVIDUAL CONTENT items (not listing pages)
   - Forums → individual threads/discussions
   - Blogs → individual posts
   - News → individual articles
   - Research → individual reports
   - Any section → individual items, not category/listing pages
2. Look for dates in link text or context (e.g., "Oct 17, 2025", "2 days ago")
   - If dates are visible, include them
   - If dates are NOT visible, still include the link if it's relevant (we'll filter later)
3. Score relevance 0.0 to 1.0 based on how well link matches user intent and target section
4. Return max {max_links} links, ranked by relevance
5. Skip obvious navigation links, login links, social media links, category/listing pages
6. IMPORTANT: Prefer to include links even if you're unsure about dates - be generous, not strict

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
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0
        )
        
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

