"""
Link Extractor Tool - Extract links from listing pages

Uses LLM to intelligently extract relevant article/thread links.
"""

import json
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from agent_v2.ai_factory import get_ai_factory
from agent_v2.types import ExtractedLink

logger = logging.getLogger(__name__)


async def extract_links(
    html: str,
    base_url: str,
    topic: str,
    time_range_days: Optional[int] = None,
    max_links: int = 20
) -> List[ExtractedLink]:
    """
    Extract relevant links from a listing page.
    
    Uses LLM to intelligently identify article/thread links and filter by:
    - Relevance to topic
    - Date (if visible and time_range_days specified)
    
    Args:
        html: Page HTML (should be cleaned)
        base_url: Base URL for resolving relative links
        topic: Topic to match against
        time_range_days: Optional time range filter
        max_links: Maximum links to return
        
    Returns:
        List of extracted links with metadata
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract all links with context
    all_links = []
    seen_urls = set()
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        text = a_tag.get_text(strip=True)
        
        # Skip empty, javascript, or fragment-only links
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        
        # Make absolute URL
        try:
            absolute_url = urljoin(base_url, href)
            parsed = urlparse(absolute_url)
            
            # Skip if not http/https
            if parsed.scheme not in ['http', 'https']:
                continue
            
            # Deduplicate
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            
            # Get surrounding context for date detection
            parent = a_tag.parent
            context = parent.get_text(strip=True)[:200] if parent else ""
            
            all_links.append({
                'url': absolute_url,
                'text': text[:150] if text else '',
                'context': context
            })
        except Exception as e:
            logger.debug(f"Failed to process link: {href} - {e}")
            continue
    
    if not all_links:
        logger.warning("No links found on page")
        return []
    
    logger.info(f"Found {len(all_links)} links, filtering with LLM...")
    
    # Pre-filter obvious non-article links
    filtered_links = _pre_filter_links(all_links, topic)
    
    if not filtered_links:
        logger.warning("No links passed pre-filtering")
        return []
    
    # Use LLM to extract and rank relevant links
    extracted_links = await _llm_extract_links(
        filtered_links,
        topic,
        time_range_days,
        max_links
    )
    
    logger.info(f"Extracted {len(extracted_links)} relevant links")
    
    return extracted_links


def _pre_filter_links(links: List[dict], topic: str) -> List[dict]:
    """
    Pre-filter links to remove obvious non-article links.
    
    This reduces tokens sent to LLM.
    """
    filtered = []
    
    exclude_patterns = [
        '/login', '/signup', '/register', '/auth',
        'facebook.com', 'twitter.com', 'linkedin.com',
        '/search', '/sitemap', '/contact', '/about',
        '/privacy', '/terms', '/subscribe', '/newsletter',
        'javascript:', 'mailto:', '#'
    ]
    
    # Category/listing page patterns (these are NOT articles)
    category_patterns = [
        '/category/', '/categories/', '/tag/', '/tags/',
        '/author/', '/authors/', '/archive/', '/archives/',
        '/section/', '/sections/', '/page/', '/pages/',
    ]
    
    for link in links:
        url = link['url'].lower()
        text = (link['text'] or '').lower()
        
        # Skip obvious non-article links
        if any(pattern in url or pattern in text for pattern in exclude_patterns):
            continue
        
        # CRITICAL: Skip category/listing pages
        # These typically:
        # 1. End with just a slash (e.g., /news/business/companies/)
        # 2. Have category patterns in URL
        # 3. Are very short generic paths
        url_clean = url.rstrip('/')
        url_parts = [p for p in url_clean.split('/') if p]
        
        # Skip if URL ends with a slash and has few path segments (likely category page)
        if url.endswith('/') and len(url_parts) <= 4:
            continue
        
        # Skip if contains category patterns
        if any(pattern in url for pattern in category_patterns):
            continue
        
        # CRITICAL: Article links typically have LONG, DESCRIPTIVE text (sentences)
        # Navigation/category links have SHORT text (single words or short phrases)
        text_length = len(text)
        text_word_count = len(text.split())
        
        # Skip links with very short text (likely navigation/category)
        # Articles usually have at least 5-10 words describing the headline
        if text_word_count < 5:
            # Allow only if URL has strong article indicators
            article_indicators = ['.html', '/article/', '/news/', '/story/', '/post/']
            if not any(indicator in url for indicator in article_indicators):
                # Also allow if URL has article IDs (numbers) or is very long
                if not any(char.isdigit() for char in url) and len(url) < 80:
                    continue
        
        # Skip very short URLs without article indicators (likely navigation)
        if len(url_parts) <= 3:
            # Allow if it has article-like indicators OR long descriptive text
            article_indicators = ['.html', '.php', '.aspx', '/article/', '/news/', '/story/']
            if not any(indicator in url for indicator in article_indicators):
                # Also allow if URL has numbers (article IDs) or long descriptive text
                if not any(char.isdigit() for char in url) and text_word_count < 8:
                    continue
        
        filtered.append(link)
    
    logger.debug(f"Pre-filtered: {len(links)} → {len(filtered)} links")
    
    return filtered


async def _llm_extract_links(
    links: List[dict],
    topic: str,
    time_range_days: Optional[int],
    max_links: int
) -> List[ExtractedLink]:
    """
    Two-stage approach:
    1. Find ALL article links (with dates) - classification only
    2. Filter and rank by topic relevance and date
    """
    
    # Stage 1: Find ALL article links (batched + concurrent)
    all_article_links = await _stage1_find_all_articles(links)
    
    if not all_article_links:
        logger.warning("Stage 1 found 0 article links, trying fallback")
        return _fallback_extract_links(links, topic, time_range_days, max_links)
    
    logger.info(f"Stage 1 found {len(all_article_links)} article links")
    
    # Stage 2: Filter by topic relevance and date, then rank
    filtered_links = await _stage2_filter_and_rank(all_article_links, topic, time_range_days, max_links)
    
    return filtered_links


async def _stage1_find_all_articles(links: List[dict]) -> List[dict]:
    """
    Stage 1: Find ALL article links (not navigation/category).
    Extract dates if visible.
    No topic filtering - just classification.
    """
    if not links:
        return []
    
    # Batch links (50 per batch for better LLM performance)
    batch_size = 50
    batches = [links[i:i + batch_size] for i in range(0, len(links), batch_size)]
    logger.info(f"Splitting {len(links)} links into {len(batches)} batches of ~{batch_size}")
    
    # Emit event for batching
    from agent_v2.graph import _emit_event
    _emit_event("extract_links:stage1:start", {
        "total_links": len(links),
        "batch_count": len(batches),
        "batch_size": batch_size
    })
    
    # Prepare prompts for each batch
    batch_tasks = []
    for batch_idx, batch in enumerate(batches):
        link_list = "\n".join([
            f"{i+1}. [{link['text'][:80] or 'No text'}]\n   URL: {link['url']}\n   Context: {link['context'][:200] if link['context'] else 'N/A'}"
            for i, link in enumerate(batch)
        ])
        
        prompt = f"""Identify ALL links that lead to INDIVIDUAL ARTICLES/CONTENT (not listing/category pages).

TASK: Classify each link as ARTICLE or NOT-ARTICLE.

LINKS:
{link_list}

🎯 **CRITICAL: WHAT TO LOOK FOR**
✅ INCLUDE article/content links that have:
   - **LONG, DESCRIPTIVE LINK TEXT** (articles have full headlines like "Marico Q2 PAT seen up 6.3% on strong volume growth")
   - **SENTENCE-LIKE TEXT** (5+ words describing the article, not just "Companies" or "News")
   - LONG URLs with article titles, slugs, or IDs
   - Specific article headlines in link text
   - Dates, timestamps, or article IDs in URL or context

❌ EXCLUDE navigation/section links like:
   - **SHORT LINK TEXT** (single words like "Companies", "News", "Markets" - these are navigation, not articles)
   - **SHORT PHRASES** (2-3 words like "Business News", "Stock Quote" - these are categories, not articles)
   - URLs ending with just a slash: /news/business/companies/ ❌ (category page)
   - Stock quote pages, sector info pages, company profile pages
   - Links with text like "Companies", "Markets", "Stocks" are NAVIGATION, not articles!

**CRITICAL RULE**: URLs that end with a slash (/) and have 3-4 path segments are ALWAYS category/listing pages, NOT articles.

**IMPORTANT**: Be PERMISSIVE - if it looks like an article (long descriptive text, specific headline), include it even if you're not 100% sure.

DATE EXTRACTION:
- Look for dates in Context field: "1 DAY AGO", "2 DAYS AGO", "hours ago", "Published: [date]", "Oct 15, 2024"
- Extract the date if visible, otherwise set to null
- Convert relative dates (e.g., "2 days ago") to YYYY-MM-DD format

Return ONLY valid JSON (no markdown):
{{
  "articles": [
    {{
      "url": "full URL from list above",
      "title": "link text or extracted title",
      "detected_date": "YYYY-MM-DD if visible, otherwise null"
    }}
  ]
}}"""
        
        batch_tasks.append((batch_idx, prompt, batch))
    
    # Execute all batches concurrently
    import asyncio
    results = await asyncio.gather(*[
        _process_batch(batch_idx, prompt, batch) 
        for batch_idx, prompt, batch in batch_tasks
    ], return_exceptions=True)
    
    # Merge all results
    all_articles = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Batch processing failed: {result}")
            continue
        if result:
            # Filter out None values and ensure all items are dicts
            valid_articles = [item for item in result if item and isinstance(item, dict) and 'url' in item]
            all_articles.extend(valid_articles)
    
    logger.info(f"Stage 1 complete: Found {len(all_articles)} total article links across all batches")
    
    # Emit stage 1 complete event
    from agent_v2.graph import _emit_event
    _emit_event("extract_links:stage1:complete", {
        "total_articles_found": len(all_articles),
        "total_links_processed": len(links)
    })
    
    return all_articles


async def _process_batch(batch_idx: int, prompt: str, batch: List[dict]) -> List[dict]:
    """Process a single batch of links"""
    try:
        logger.info(f"Processing batch {batch_idx + 1} with {len(batch)} links")
        
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            response_text = "\n".join(json_lines)
        
        result = json.loads(response_text)
        articles = result.get('articles', [])
        
        # Validate and filter articles
        valid_articles = []
        for article in articles:
            if not article or not isinstance(article, dict):
                logger.warning(f"Batch {batch_idx + 1}: Skipping invalid article entry: {article}")
                continue
            if 'url' not in article or not article.get('url'):
                logger.warning(f"Batch {batch_idx + 1}: Skipping article without URL: {article}")
                continue
            valid_articles.append(article)
        
        logger.info(f"Batch {batch_idx + 1} found {len(valid_articles)} valid article links (from {len(articles)} total)")
        
        # Emit batch progress event
        try:
            from agent_v2.graph import _emit_event
            _emit_event("extract_links:stage1:batch", {
                "batch_num": batch_idx + 1,
                "articles_found": len(valid_articles),
                "batch_size": len(batch)
            })
        except Exception:
            pass  # Don't fail if event system not available
        
        return valid_articles
        
    except Exception as e:
        logger.error(f"Batch {batch_idx + 1} failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []


async def _stage2_filter_and_rank(
    article_links: List[dict],
    topic: str,
    time_range_days: Optional[int],
    max_links: int
) -> List[ExtractedLink]:
    """
    Stage 2: Filter by topic relevance and date, then rank.
    """
    if not article_links:
        return []
    
    logger.info(f"Stage 2: Filtering and ranking {len(article_links)} article links")
    
    # Emit stage 2 start event
    from agent_v2.graph import _emit_event
    _emit_event("extract_links:stage2:start", {
        "article_links_count": len(article_links),
        "topic": topic,
        "time_range_days": time_range_days
    })
    
    # Prepare link list for ranking (filter out invalid entries with strict validation)
    valid_links = []
    for link in article_links:
        if not link:
            logger.warning("Stage 2: Skipping None link")
            continue
        if not isinstance(link, dict):
            logger.warning(f"Stage 2: Skipping non-dict link: {type(link)}")
            continue
        if 'url' not in link or not link.get('url'):
            logger.warning(f"Stage 2: Skipping link without URL: {link}")
            continue
        valid_links.append(link)
    
    if not valid_links:
        logger.warning("Stage 2: No valid article links to filter")
        return []
    
    logger.info(f"Stage 2: Processing {len(valid_links)} valid links (from {len(article_links)} total)")
    
    # Build link list with defensive error handling
    link_list_parts = []
    for i, link in enumerate(valid_links):
        try:
            title = link.get('title', 'No title')[:80] if link.get('title') else 'No title'
            url = link.get('url', 'NO URL')
            date = link.get('detected_date', 'Not specified')
            link_list_parts.append(f"{i+1}. [{title}]\n   URL: {url}\n   Date: {date}")
        except Exception as e:
            logger.error(f"Stage 2: Error formatting link {i+1}: {e}, link: {link}")
            continue
    
    if not link_list_parts:
        logger.error("Stage 2: No valid links could be formatted")
        return []
    
    link_list = "\n".join(link_list_parts)
    
    time_filter_text = f"Last {time_range_days} days" if time_range_days else "No time filter"
    
    prompt = f"""Filter and rank article links by relevance to the user's request.

USER WANTS: {topic}
TIME RANGE: {time_filter_text}

ARTICLE LINKS (already identified as articles):
{link_list}

TASK: 
1. Filter links by topic relevance (must be related to: {topic})
2. If time_range specified, prioritize links with dates within the range
3. Rank by: relevance to topic first, then recency (if dates available)

RANKING PRIORITY:
- Highly relevant to topic + within time range = highest priority
- Relevant to topic + no date (can't verify age) = medium priority  
- Relevant to topic + outside time range = lower priority
- Not relevant to topic = exclude

Return ONLY valid JSON (no markdown):
{{
  "links": [
    {{
      "url": "full URL from list above",
      "title": "title from list above",
      "detected_date": "date from list above (or null)",
      "relevance_score": 0.85
    }}
  ]
}}"""
    
    try:
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            response_text = "\n".join(json_lines)
        
        result = json.loads(response_text)
        links_data = result.get('links', [])
        
        logger.info(f"Stage 2 returned {len(links_data)} relevant links")
        
        # Emit stage 2 progress
        from agent_v2.graph import _emit_event
        _emit_event("extract_links:stage2:filtered", {
            "relevant_links": len(links_data),
            "total_articles": len(article_links)
        })
        
        # Convert to ExtractedLink objects and apply date filtering
        extracted = []
        cutoff_date = None
        if time_range_days:
            cutoff_date = datetime.now() - timedelta(days=time_range_days)
            logger.info(f"Date filter: cutoff_date = {cutoff_date}")
        
        for i, link_data in enumerate(links_data):
            url = link_data.get('url', 'NO URL')
            title = link_data.get('title', '')
            detected_date_str = link_data.get('detected_date')
            
            logger.info(f"Processing link {i+1}/{len(links_data)}: {url[:80]}")
            logger.info(f"  Title: {title[:100]}")
            logger.info(f"  Detected date (raw): {detected_date_str}")
            
            # Parse date if provided
            detected_date = None
            if detected_date_str and detected_date_str.lower() != 'null':
                try:
                    detected_date = datetime.strptime(detected_date_str, '%Y-%m-%d')
                    logger.info(f"  Parsed date: {detected_date}")
                except Exception as e:
                    logger.warning(f"  Failed to parse date '{detected_date_str}': {e}")
                    detected_date = None
            
            # Filter by date if specified
            if time_range_days:
                if detected_date:
                    if detected_date < cutoff_date:
                        logger.warning(f"  ❌ SKIPPING (too old): {detected_date} < {cutoff_date}")
                        continue
                    else:
                        logger.info(f"  ✅ Date OK: {detected_date} >= {cutoff_date}")
                else:
                    # No date detected - include it (we can't verify it's too old)
                    logger.info(f"  ⚠️  No date detected - INCLUDING (can't verify age)")
            
            extracted.append(ExtractedLink(
                url=url,
                title=title,
                snippet=None,  # Not needed in stage 2
                detected_date=detected_date,
                relevance_score=float(link_data.get('relevance_score', 0.5))
            ))
            logger.info(f"  ✅ Added link: {url[:80]}")
        
        # Sort by relevance score
        extracted.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"Stage 2 complete: {len(extracted)} links after filtering")
        
        return extracted[:max_links]
        
    except Exception as e:
        logger.exception(f"Stage 2 failed: {e}")
        # Fallback: return all article links without filtering
        logger.warning("Falling back to all article links without topic/date filtering")
        return [
            ExtractedLink(
                url=link['url'],
                title=link.get('title', ''),
                snippet=None,
                detected_date=None,
                relevance_score=0.5
            )
            for link in article_links[:max_links]
        ]


def _fallback_extract_links(
    links: List[dict],
    topic: str,
    time_range_days: Optional[int],
    max_links: int
) -> List[ExtractedLink]:
    """
    Fallback heuristic extraction when LLM fails or returns 0 links.
    
    Uses simple heuristics to identify article links:
    - URL length and structure
    - Presence of article-like patterns
    - Link text length
    """
    logger.info(f"Fallback: Extracting links using heuristics from {len(links)} candidates")
    
    scored_links = []
    topic_lower = topic.lower()
    
    for link in links:
        url = link['url'].lower()
        text = (link.get('text', '') or '').lower()
        context = (link.get('context', '') or '').lower()
        
        score = 0.0
        
        # Score by URL structure (article URLs are typically longer and have specific patterns)
        url_parts = url.split('/')
        url_depth = len([p for p in url_parts if p])
        
        # Article URLs typically have:
        # - More path segments (depth > 4)
        # - Contain article-like keywords
        # - Have file extensions (.html, .php) or IDs
        article_indicators = [
            '/article/', '/news/', '/story/', '/post/', '/blog/',
            '.html', '.php', '.aspx',
            '/2024/', '/2023/',  # Year in URL
        ]
        
        if any(indicator in url for indicator in article_indicators):
            score += 0.3
        
        if url_depth > 4:
            score += 0.2
        
        # Check for article IDs (numbers in URL)
        if any(char.isdigit() for char in url.split('/')[-1]):
            score += 0.2
        
        # Score by link text (article links usually have LONG, DESCRIPTIVE text - sentences/headlines)
        text_word_count = len(text.split())
        if text_word_count >= 8:  # Article headlines are usually 8+ words
            score += 0.4  # Strong indicator
        elif text_word_count >= 5:  # Minimum for article-like text
            score += 0.2
        elif text_word_count < 3:  # Very short text is likely navigation
            score -= 0.3  # Penalty for navigation-like links
        
        # Score by topic relevance
        topic_words = set(topic_lower.split())
        text_words = set(text.split())
        context_words = set(context.split())
        
        if topic_words & text_words:
            score += 0.3
        elif topic_words & context_words:
            score += 0.2
        
        # Penalize obvious non-articles
        exclude_patterns = ['/category/', '/tag/', '/author/', '/archive/', '/page/']
        if any(pattern in url for pattern in exclude_patterns):
            score -= 0.5
        
        # CRITICAL: Penalize category pages (URLs ending with / and few segments)
        url_clean = url.rstrip('/')
        url_parts = [p for p in url_clean.split('/') if p]
        if url.endswith('/') and len(url_parts) <= 4:
            score -= 1.0  # Heavy penalty - these are category pages
        
        if score > 0.3:  # Minimum threshold
            scored_links.append((link, score))
    
    # Sort by score
    scored_links.sort(key=lambda x: x[1], reverse=True)
    
    # Convert to ExtractedLink objects
    extracted = []
    cutoff_date = None
    if time_range_days:
        cutoff_date = datetime.now() - timedelta(days=time_range_days)
    
    for link, score in scored_links[:max_links * 2]:  # Get more candidates for date filtering
        # Try to extract date from context
        detected_date = None
        context = link.get('context', '')
        
        # Simple date extraction (look for common patterns)
        import re
        date_patterns = [
            r'(\d{1,2})\s+(day|days)\s+ago',
            r'(\d{1,2})\s+(hour|hours)\s+ago',
            r'(\d{1,2})\s+(week|weeks)\s+ago',
            r'(\d{1,2})\s+(month|months)\s+ago',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, context.lower())
            if match:
                num = int(match.group(1))
                unit = match.group(2)
                if 'day' in unit:
                    detected_date = datetime.now() - timedelta(days=num)
                elif 'hour' in unit:
                    detected_date = datetime.now() - timedelta(hours=num)
                elif 'week' in unit:
                    detected_date = datetime.now() - timedelta(weeks=num)
                elif 'month' in unit:
                    detected_date = datetime.now() - timedelta(days=num * 30)
                break
        
        # Filter by date if specified
        if time_range_days and detected_date and detected_date < cutoff_date:
            continue
        
        extracted.append(ExtractedLink(
            url=link['url'],
            title=link.get('text', '')[:150] or '',
            snippet=link.get('context', '')[:200] if link.get('context') else None,
            detected_date=detected_date,
            relevance_score=min(score, 1.0)  # Cap at 1.0
        ))
        
        if len(extracted) >= max_links:
            break
    
    logger.info(f"Fallback extracted {len(extracted)} links")
    return extracted

