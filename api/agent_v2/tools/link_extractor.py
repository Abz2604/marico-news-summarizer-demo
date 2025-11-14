"""
Link Extractor Tool - Extract links from listing pages

Uses LLM to intelligently extract relevant article/thread links.
"""

import json
import logging
import re
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from agent_v2.ai_factory import get_ai_factory
from agent_v2.types import ExtractedLink

logger = logging.getLogger(__name__)


def extract_json_from_response(response_text: str) -> Optional[dict]:
    """
    Extract and parse JSON from LLM response, handling various formats.
    
    Handles:
    - Markdown code blocks (```json ... ```)
    - Plain JSON
    - JSON with extra text before/after
    - Malformed JSON with unescaped quotes
    
    Args:
        response_text: Raw LLM response text
        
    Returns:
        Parsed JSON dict or None if parsing fails
    """
    if not response_text:
        return None
    
    response_text = response_text.strip()
    
    # Remove markdown code blocks
    if "```" in response_text:
        lines = response_text.split("\n")
        json_lines = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or not in_code_block:
                json_lines.append(line)
        response_text = "\n".join(json_lines)
    
    # Try to find JSON object boundaries
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}')
    
    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        logger.warning("No JSON object found in response")
        return None
    
    # Extract JSON portion
    json_text = response_text[start_idx:end_idx + 1]
    
    # Try to parse
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        logger.debug(f"JSON text (first 500 chars): {json_text[:500]}")
        
        # Try to fix common issues: unescaped quotes in strings
        # This is a simple fix - might not work for all cases
        try:
            # Replace unescaped quotes inside string values (heuristic)
            # This is risky but sometimes works
            import re
            # Try to escape quotes that are inside string values
            # Pattern: "key": "value with "quotes" here"
            # This is complex, so let's just try a simpler approach
            # Remove any text after the last valid }
            json_text_clean = json_text
            # Try parsing with error recovery
            return json.loads(json_text_clean)
        except:
            pass
        
        return None


def normalize_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Normalize various date formats to datetime object.
    
    Handles:
    - Relative dates: "1 day ago", "2 days ago", "4 days ago", "1 hour ago", "2 weeks ago"
    - Absolute dates: "Oct 15, 2024", "2024-10-15", "15/10/2024"
    - Returns None if unparseable
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        datetime object or None
    """
    if not date_str or date_str.lower() in ('null', 'none', ''):
        logger.debug(f"normalize_date: Empty or null date string")
        return None
    
    original_date_str = date_str
    date_str = date_str.strip()
    logger.debug(f"normalize_date: Input: '{original_date_str}' -> stripped: '{date_str}'")
    
    # Try relative date patterns first (most common on listing pages)
    relative_patterns = [
        (r'(\d+)\s+(day|days)\s+ago', lambda m: datetime.now() - timedelta(days=int(m.group(1)))),
        (r'(\d+)\s+(hour|hours)\s+ago', lambda m: datetime.now() - timedelta(hours=int(m.group(1)))),
        (r'(\d+)\s+(week|weeks)\s+ago', lambda m: datetime.now() - timedelta(weeks=int(m.group(1)))),
        (r'(\d+)\s+(month|months)\s+ago', lambda m: datetime.now() - timedelta(days=int(m.group(1)) * 30)),
        (r'(\d+)\s+(year|years)\s+ago', lambda m: datetime.now() - timedelta(days=int(m.group(1)) * 365)),
        (r'(\d+)d\s+ago', lambda m: datetime.now() - timedelta(days=int(m.group(1)))),  # "4d ago"
        (r'(\d+)h\s+ago', lambda m: datetime.now() - timedelta(hours=int(m.group(1)))),  # "2h ago"
        (r'(\d+)w\s+ago', lambda m: datetime.now() - timedelta(weeks=int(m.group(1)))),  # "1w ago"
    ]
    
    for pattern, converter in relative_patterns:
        match = re.search(pattern, date_str, re.IGNORECASE)
        if match:
            try:
                result = converter(match)
                logger.info(f"normalize_date: ✅ Matched relative pattern '{pattern}': '{date_str}' -> {result}")
                return result
            except Exception as e:
                logger.warning(f"normalize_date: Failed to convert relative date '{date_str}' with pattern '{pattern}': {e}")
                continue
    
    # Try absolute date formats
    absolute_formats = [
        '%Y-%m-%d',           # 2024-10-15
        '%Y/%m/%d',           # 2024/10/15
        '%d/%m/%Y',           # 15/10/2024
        '%m/%d/%Y',           # 10/15/2024
        '%B %d, %Y',          # October 15, 2024
        '%b %d, %Y',           # Oct 15, 2024
        '%d %B %Y',            # 15 October 2024
        '%d %b %Y',            # 15 Oct 2024
        '%Y-%m-%d %H:%M:%S',  # 2024-10-15 12:00:00
        '%Y-%m-%dT%H:%M:%S',  # 2024-10-15T12:00:00
    ]
    
    for fmt in absolute_formats:
        try:
            result = datetime.strptime(date_str, fmt)
            return result
        except ValueError:
            continue
    
    # If all else fails, try dateutil-like parsing (common formats)
    # Handle "Published: Oct 15, 2024" or "Updated: 2 days ago"
    if ':' in date_str:
        # Extract date part after colon
        date_part = date_str.split(':', 1)[1].strip()
        logger.debug(f"normalize_date: Extracting date after colon: '{date_part}'")
        return normalize_date(date_part)
    
    return None


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
            # Dates can be in text OR in attributes (data-updated, data-date, datetime, etc.)
            context_parts = []
            extracted_date = None  # Algorithmically extracted date (from attributes)
            
            # Walk up the DOM tree to find container elements (like card__content)
            # IMPORTANT: Also check the link's own parent container (the <a> tag might contain the structure)
            parent = a_tag.parent
            current = parent
            checked_elements = set()  # Avoid duplicates
            date_attrs = ['data-updated', 'data-date', 'datetime', 'title', 'data-published', 'data-modified', 'data-time']
            
            # Track all attributes found for debugging
            all_attrs_found = []
            
            # FIRST: Check if the link itself contains a container with date (like <a><div class="card__content"><div data-updated>)
            # This handles cases where the entire card structure is inside the <a> tag
            # CRITICAL: Many blog sites put the entire card structure inside the <a> tag!
            for descendant in a_tag.find_all(['div', 'span', 'time', 'article', 'section'], recursive=True):
                if id(descendant) in checked_elements:
                    continue
                checked_elements.add(id(descendant))
                
                for attr in date_attrs:
                    attr_value = descendant.get(attr, '')
                    if attr_value:
                        # Always add to context for LLM fallback
                        all_attrs_found.append(f"descendant.{descendant.name}.{attr}={attr_value}")
                        context_parts.append(f"{attr}={attr_value}")
                        logger.debug(f"Found date attribute {descendant.name}.{attr}={attr_value} inside <a> tag for {absolute_url[:80]}")
                        
                        # Try algorithmic extraction
                        if not extracted_date:
                            logger.debug(f"Checking descendant {descendant.name}.{attr}='{attr_value}' inside <a> tag for {absolute_url[:80]}")
                            normalized = normalize_date(attr_value)
                            if normalized:
                                extracted_date = attr_value
                                logger.info(f"✅ Algorithmically extracted date from descendant {descendant.name}.{attr} inside <a>: '{extracted_date}' for {absolute_url[:80]}")
                                break
                if extracted_date:
                    break
            
            # Check up to 4 levels up to find card containers
            for level in range(4):
                if not current:
                    break
                
                # Check for date attributes in current element (ALGORITHMIC EXTRACTION)
                if not extracted_date:  # Only extract once (first match wins)
                    for attr in date_attrs:
                        attr_value = current.get(attr, '')
                        if attr_value:
                            logger.debug(f"Checking {current.name}.{attr}='{attr_value}' for link {absolute_url[:80]}")
                            # Check if this looks like a valid date
                            normalized = normalize_date(attr_value)
                            if normalized:  # Valid date format?
                                extracted_date = attr_value
                                logger.info(f"✅ Algorithmically extracted date from {current.name}.{attr}: '{extracted_date}' for {absolute_url[:80]}")
                                break
                            else:
                                logger.debug(f"  ❌ normalize_date() returned None for '{attr_value}'")
                
                # Add to context for LLM fallback
                for attr in date_attrs:
                    attr_value = current.get(attr, '')
                    if attr_value:
                        all_attrs_found.append(f"{current.name}.{attr}={attr_value}")
                        context_parts.append(f"{attr}={attr_value}")
                        logger.debug(f"Found date attribute {attr}={attr_value} on {current.name}")
                
                # Get text from current element
                current_text = current.get_text(strip=True)
                if current_text and len(current_text) < 500:
                    context_parts.append(current_text)
                
                # Check siblings of current element for date attributes and text
                # IMPORTANT: Check siblings of current itself (same parent), not just siblings of current.parent
                if current.parent:
                    # Get all siblings of current (including current itself, we'll skip it)
                    siblings = []
                    # Method 1: Use direct children (works for most cases)
                    for sib in current.parent.children:
                        if hasattr(sib, 'name') and sib.name in ['div', 'span', 'time', 'p', 'article', 'section']:
                            siblings.append(sib)
                    
                    # Method 2: Also check find_all with recursive=False (catches more cases)
                    find_all_siblings = current.parent.find_all(['div', 'span', 'time', 'p', 'article', 'section'], recursive=False)
                    for sib in find_all_siblings:
                        if sib not in siblings:
                            siblings.append(sib)
                    
                    # Method 3: If still no siblings, check all descendants of parent (for nested structures)
                    # This handles cases where the date might be in a nested div inside a sibling
                    if not siblings:
                        all_descendants = current.parent.find_all(['div', 'span', 'time', 'p', 'article', 'section'])
                        siblings = [s for s in all_descendants if s != current]
                    
                    for sibling in siblings:
                        # Skip current element itself
                        if id(sibling) == id(current):
                            continue
                        if id(sibling) in checked_elements:
                            continue
                        checked_elements.add(id(sibling))
                        
                        # Check sibling attributes for dates (ALGORITHMIC EXTRACTION)
                        if not extracted_date:  # Only extract once
                            for attr in date_attrs:
                                attr_value = sibling.get(attr, '')
                                if attr_value:
                                    logger.debug(f"Checking sibling {sibling.name}.{attr}='{attr_value}' for link {absolute_url[:80]}")
                                    normalized = normalize_date(attr_value)
                                    if normalized:  # Valid date format?
                                        extracted_date = attr_value
                                        logger.info(f"✅ Algorithmically extracted date from sibling {sibling.name}.{attr}: '{extracted_date}' for {absolute_url[:80]}")
                                        break
                                    else:
                                        logger.debug(f"  ❌ normalize_date() returned None for '{attr_value}'")
                            if extracted_date:
                                break
                        
                        # Add to context for LLM fallback
                        for attr in date_attrs:
                            attr_value = sibling.get(attr, '')
                            if attr_value:
                                all_attrs_found.append(f"sibling.{sibling.name}.{attr}={attr_value}")
                                context_parts.append(f"{attr}={attr_value}")
                                logger.debug(f"Found date attribute {attr}={attr_value} on sibling {sibling.name}")
                        
                        # Get sibling text (especially short text which might be dates)
                        sibling_text = sibling.get_text(strip=True)
                        if sibling_text:
                            if len(sibling_text) < 50:  # Short text likely to be dates
                                context_parts.append(sibling_text)
                            elif 'ago' in sibling_text.lower() or 'day' in sibling_text.lower() or 'hour' in sibling_text.lower():
                                # Contains date-like words, include it
                                context_parts.append(sibling_text[:100])
                
                # Move up to parent
                current = current.parent
            
            # Also check the link's own attributes (ALGORITHMIC EXTRACTION)
            if not extracted_date:
                for attr in ['data-updated', 'data-date', 'datetime', 'title']:
                    attr_value = a_tag.get(attr, '')
                    if attr_value:
                        logger.debug(f"Checking link.{attr}='{attr_value}' for {absolute_url[:80]}")
                        normalized = normalize_date(attr_value)
                        if normalized:  # Valid date format?
                            extracted_date = attr_value
                            logger.info(f"✅ Algorithmically extracted date from link.{attr}: '{extracted_date}' for {absolute_url[:80]}")
                            break
                        else:
                            logger.debug(f"  ❌ normalize_date() returned None for '{attr_value}'")
                    # Also add to context
                    if attr_value:
                        context_parts.append(f"link_{attr}={attr_value}")
            
            # Combine context parts (remove duplicates, preserve order)
            seen = set()
            unique_parts = []
            for part in context_parts:
                if part and part not in seen and len(part.strip()) > 0:
                    seen.add(part)
                    unique_parts.append(part)
            
            context = " | ".join(unique_parts)[:500] if unique_parts else ""
            
            # Store link with algorithmically extracted date
            all_links.append({
                'url': absolute_url,
                'text': text[:150] if text else '',
                'context': context,
                'extracted_date': extracted_date  # Algorithmically extracted (or None)
            })
            
            # Log summary of what we found
            if all_attrs_found:
                logger.info(f"Link {absolute_url[:80]}: Found {len(all_attrs_found)} date attributes: {', '.join(all_attrs_found[:3])}{'...' if len(all_attrs_found) > 3 else ''}")
            else:
                logger.debug(f"Link {absolute_url[:80]}: No date attributes found in DOM traversal")
            
            if extracted_date:
                logger.info(f"Link {absolute_url[:80]}: ✅ Algorithmic date = '{extracted_date}'")
            else:
                logger.debug(f"Link {absolute_url[:80]}: No algorithmic date found, will rely on LLM")
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
    
    # Stage 2: Filter by topic relevance and date, then rank (batched)
    filtered_links = await _stage2_filter_and_rank(all_article_links, topic, time_range_days, max_links)
    
    # If Stage 2 returns empty (all batches failed), use fallback with date filtering
    if not filtered_links:
        logger.warning("Stage 2 returned 0 links, using fallback with date filtering")
        return _fallback_extract_links_strict(all_article_links, topic, time_range_days, max_links)
    
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
        # Log sample context to check if dates are present
        if batch_idx == 0 and batch:
            logger.info(f"Stage 1: Sample context from first batch (checking for dates):")
            for i, link in enumerate(batch[:5]):  # First 5 links for better sampling
                context = link.get('context', '')
                logger.info(f"  Link {i+1}: {link.get('text', '')[:60]}")
                logger.info(f"    URL: {link.get('url', '')[:80]}")
                logger.info(f"    Context (full): {context if context else 'N/A'}")
                # Check if context contains date-like patterns
                if context:
                    import re
                    date_patterns = [
                        r'\d+\s+(day|days)\s+ago',
                        r'\d+\s+(hour|hours)\s+ago',
                        r'\d+d\s+ago',
                        r'\d+h\s+ago',
                        r'\d+\s+(week|weeks)\s+ago',
                        r'(\d{1,2})\s+(day|days)\s+ago',  # More specific
                    ]
                    found_date = False
                    for pattern in date_patterns:
                        matches = re.findall(pattern, context, re.IGNORECASE)
                        if matches:
                            logger.info(f"    ✅ Found date pattern '{pattern}' in context! Matches: {matches}")
                            found_date = True
                            break
                    if not found_date:
                        logger.warning(f"    ❌ No date patterns found in context")
                else:
                    logger.warning(f"    ❌ Context is empty!")
        
        # Build link list with algorithmic dates if available
        link_list_parts = []
        for i, link in enumerate(batch):
            text = link['text'][:80] or 'No text'
            url = link['url']
            context = link['context'][:200] if link['context'] else 'N/A'
            algo_date = link.get('extracted_date')  # Algorithmically extracted date
            
            if algo_date:
                # Algorithmic date found - use it, but still show context for LLM
                link_list_parts.append(f"{i+1}. [{text}]\n   URL: {url}\n   Date (algorithmic): {algo_date}\n   Context: {context}")
            else:
                # No algorithmic date - LLM needs to extract from context
                link_list_parts.append(f"{i+1}. [{text}]\n   URL: {url}\n   Context: {context}")
        
        link_list = "\n".join(link_list_parts)
        
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

DATE EXTRACTION (CRITICAL - READ CAREFULLY):
- **PRIORITY 1**: If a link shows "Date (algorithmic): [date]", USE THAT DATE EXACTLY as-is (e.g., "13 hours ago", "2 days ago")
- **PRIORITY 2**: If no algorithmic date, look in the Context field for dates. Dates can appear in TWO ways:
  1. **In text**: "1 DAY AGO", "2 DAYS AGO", "4 days ago", "13 hours ago", "hours ago", "Published: [date]", "Oct 15, 2024"
  2. **In attributes**: The Context field may contain attribute values like "data-updated=13 hours ago" or "data-date=2 days ago"
- **IMPORTANT**: Extract the date EXACTLY as it appears (including from attributes)
- If you see "data-updated=13 hours ago" or "data-updated=2 days ago" in Context, extract "13 hours ago" or "2 days ago"
- If you see "1 day ago" or "2 days ago" or "4 days ago" in Context text, return that EXACT STRING
- **DO NOT convert relative dates to YYYY-MM-DD** - return them as-is (e.g., "13 hours ago", "2 days ago", "1 day ago")
- Only set to null if NO date is visible (no algorithmic date AND no date in context)

Return ONLY valid JSON (no markdown):
{{
  "articles": [
    {{
      "url": "full URL from list above",
      "title": "link text or extracted title",
      "detected_date": "date as it appears in Context (e.g., '2 days ago', '1 day ago') OR null if not found"
    }}
  ]
}}"""
        
        batch_tasks.append((batch_idx, prompt, batch))
    
    # Execute all batches concurrently
    import asyncio
    results = await asyncio.gather(*[
        _process_batch(batch_idx, prompt, batch, batch)  # Pass original batch for date lookup
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


async def _process_batch(batch_idx: int, prompt: str, batch: List[dict], original_batch: List[dict] = None) -> List[dict]:
    """Process a single batch of links"""
    try:
        logger.info(f"Processing batch {batch_idx + 1} with {len(batch)} links")
        
        ai_factory = get_ai_factory()
        llm = ai_factory.get_smart_llm(temperature=0)
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Extract and parse JSON with robust error handling
        result = extract_json_from_response(response_text)
        if not result:
            logger.error(f"Batch {batch_idx + 1}: Failed to parse JSON from LLM response")
            logger.debug(f"Response text (first 500 chars): {response_text[:500]}")
            return []
        
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
            
            detected_date = article.get('detected_date')
            url = article.get('url', '')
            
            # Check if we have algorithmic date from original link
            algo_date = None
            if original_batch:
                for link in original_batch:
                    if link.get('url') == url:
                        algo_date = link.get('extracted_date')
                        break
            
            # Convert JSON null to None, and handle string "null"
            if detected_date is None or (isinstance(detected_date, str) and detected_date.lower() in ('null', 'none', '')):
                # No LLM date - use algorithmic date if available
                if algo_date:
                    logger.info(f"Stage 1: Using algorithmic date '{algo_date}' for {url[:80]}")
                    article['detected_date'] = algo_date
                else:
                    article['detected_date'] = None
            else:
                # LLM found a date - use it (it might be from text context)
                article['detected_date'] = detected_date
            
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
    Processes in batches of 20 links to avoid JSON parsing issues.
    Applies date filtering - only includes links with dates within the specified range.
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
        if not link or not isinstance(link, dict) or 'url' not in link or not link.get('url'):
            continue
        valid_links.append(link)
    
    if not valid_links:
        logger.warning("Stage 2: No valid article links to filter")
        return []
    
    # Calculate cutoff date for STRICT date filtering
    cutoff_date = None
    if time_range_days:
        cutoff_date = datetime.now() - timedelta(days=time_range_days)
        logger.info(f"Stage 2: Date filter active - cutoff_date = {cutoff_date} (only articles from last {time_range_days} days)")
    else:
        logger.info(f"Stage 2: No date filter (time_range_days = {time_range_days})")
    
    # Batch processing: 20 links per batch
    batch_size = 20
    batches = [valid_links[i:i + batch_size] for i in range(0, len(valid_links), batch_size)]
    
    # Prepare batch tasks for parallel processing
    time_filter_text = f"Last {time_range_days} days" if time_range_days else "No time filter"
    cutoff_date_str = cutoff_date.isoformat() if cutoff_date else "N/A"
    
    async def process_stage2_batch(batch_idx: int, batch: List[dict]) -> List[ExtractedLink]:
        """Process a single Stage 2 batch"""
        # Build link list for this batch
        link_list_parts = []
        for i, link in enumerate(batch):
            try:
                title = link.get('title', 'No title')[:80] if link.get('title') else 'No title'
                url = link.get('url', 'NO URL')
                date = link.get('detected_date')
                
                # Format date for prompt
                date_str = str(date) if date is not None else 'Not specified'
                link_list_parts.append(f"{i+1}. [{title}]\n   URL: {url}\n   Date: {date_str}")
            except Exception as e:
                logger.error(f"Stage 2 Batch {batch_idx + 1}: Error formatting link {i+1}: {e}")
                continue
        
        if not link_list_parts:
            return []
        
        link_list = "\n".join(link_list_parts)
        
        prompt = f"""Filter article links by relevance to the user's request.

USER WANTS: {topic}
TIME RANGE: {time_filter_text} (cutoff date: {cutoff_date_str})

ARTICLE LINKS (already identified as articles):
{link_list}

TASK: 
1. Filter links by topic relevance (be PERMISSIVE - include if even loosely related to: {topic})
2. Prioritize links with dates within the time range ({time_filter_text})
3. Rank by: relevance to topic first, then recency (if dates available)

RANKING PRIORITY:
- Highly relevant to topic + within time range = highest priority
- Loosely relevant to topic + within time range = high priority
- Relevant to topic + no date = medium priority
- Not relevant to topic = exclude

IMPORTANT: 
- Be PERMISSIVE with topic matching. If an article mentions any aspect of the topic, include it.
- Include links even if date is not specified (date filtering will be applied separately)
- Only exclude if completely unrelated to the topic

Return ONLY valid JSON (no markdown):
{{
  "links": [
    {{
      "url": "full URL from list above",
      "title": "title from list above",
      "detected_date": "date from list above (keep as-is, e.g., '2 days ago' or '2024-10-15')",
      "relevance_score": 0.85
    }}
  ]
}}"""
        
        try:
            ai_factory = get_ai_factory()
            llm = ai_factory.get_smart_llm(temperature=0)
            
            response = await llm.ainvoke(prompt)
            response_text = response.content.strip()
            
            # Extract and parse JSON with robust error handling
            result = extract_json_from_response(response_text)
            if not result:
                logger.warning(f"Stage 2 Batch {batch_idx + 1}: Failed to parse JSON, skipping batch")
                return []
            
            links_data = result.get('links', [])
            logger.info(f"Stage 2 Batch {batch_idx + 1}: LLM returned {len(links_data)} links")
            
            # Convert to ExtractedLink objects and apply date filtering
            batch_extracted = []
            for link_data in links_data:
                url = link_data.get('url', 'NO URL')
                title = link_data.get('title', '')
                detected_date_str = link_data.get('detected_date')
                
                # Normalize date (handles relative dates like "1 day ago", "2 days ago", etc.)
                detected_date = normalize_date(detected_date_str)
                
                # Date filtering: Only exclude if date exists AND is too old
                # If no date, include it (let content extractor find date later)
                if time_range_days and cutoff_date:
                    if detected_date:
                        # We have a date - check if it's within range
                        if detected_date < cutoff_date:
                            days_old = (datetime.now() - detected_date).days
                            logger.warning(f"Stage 2: Excluding {url[:60]} - date {detected_date} is {days_old} days old (cutoff: {cutoff_date}, need < {time_range_days} days)")
                            continue
                        else:
                            days_old = (datetime.now() - detected_date).days
                            logger.info(f"Stage 2: ✅ Including {url[:60]} - date {detected_date} is {days_old} days old (within {time_range_days} days)")
                    else:
                        # No date detected - include it anyway (date might be on article page)
                        logger.info(f"Stage 2: ⚠️ Including {url[:60]} - no date detected (will check on article page)")
                
                batch_extracted.append(ExtractedLink(
                    url=url,
                    title=title,
                    snippet=None,
                    detected_date=detected_date,
                    relevance_score=float(link_data.get('relevance_score', 0.5))
                ))
            
            return batch_extracted
        
        except Exception as e:
            logger.error(f"Stage 2 Batch {batch_idx + 1} failed: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    # Process all batches in parallel
    import asyncio
    batch_tasks = [process_stage2_batch(batch_idx, batch) for batch_idx, batch in enumerate(batches)]
    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
    
    # Merge results from all batches
    all_extracted = []
    for batch_idx, result in enumerate(batch_results):
        if isinstance(result, Exception):
            logger.error(f"Stage 2 Batch {batch_idx + 1} raised exception: {result}")
            continue
        if result:
            all_extracted.extend(result)
    
    logger.info(f"Stage 2: Merged {len(all_extracted)} links from {len(batches)} batches")
    
    # Sort by relevance score (highest first)
    all_extracted.sort(key=lambda x: x.relevance_score, reverse=True)
    
    logger.info(f"Stage 2 complete: {len(all_extracted)} links after date filtering (from {len(article_links)} total)")
    
    # Emit stage 2 progress
    _emit_event("extract_links:stage2:filtered", {
        "relevant_links": len(all_extracted),
        "total_articles": len(article_links)
    })
    
    # Return top max_links
    result = all_extracted[:max_links]
    logger.info(f"Stage 2: Returning top {len(result)} links (requested: {max_links})")
    return result


def _fallback_extract_links_strict(
    article_links: List[dict],
    topic: str,
    time_range_days: Optional[int],
    max_links: int
) -> List[ExtractedLink]:
    """
    Fallback with date filtering - only includes links with dates within range.
    Used when Stage 2 LLM processing fails.
    """
    # Calculate cutoff date for date filtering
    cutoff_date = None
    if time_range_days:
        cutoff_date = datetime.now() - timedelta(days=time_range_days)
    
    filtered_links = []
    topic_lower = topic.lower()
    
    for link in article_links:
        url = link.get('url', '')
        title = link.get('title', '')
        link_text = (link.get('text', '') or title or '').lower()
        
        # Date filtering: Only include if normalized date is within range
        if time_range_days and cutoff_date:
            link_date_str = link.get('detected_date')
            link_date = normalize_date(link_date_str) if link_date_str else None
            
            # If no date or date is too old, exclude
            if not link_date or link_date < cutoff_date:
                continue
        
        # Basic topic relevance check (simple keyword matching)
        topic_score = 0.0
        if any(word in link_text for word in topic_lower.split() if len(word) > 3):
            topic_score = 0.5
        
        filtered_links.append(ExtractedLink(
            url=url,
            title=title or link.get('text', '')[:100] or 'Untitled',
            snippet=None,
            detected_date=normalize_date(link.get('detected_date')),
            relevance_score=topic_score
        ))
        
        # Stop when we have enough
        if len(filtered_links) >= max_links:
            break
    
    return filtered_links


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
    # Fallback heuristic extraction
    
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
    
    # Get candidates (more than max_links to account for date filtering, but not too many)
    candidate_count = min(max_links * 3, len(scored_links)) if time_range_days else min(max_links, len(scored_links))
    for link, score in scored_links[:candidate_count]:
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

