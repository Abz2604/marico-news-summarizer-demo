"""
Generic LLM-Based Content Extraction

Replaces readability library with LLM-based extraction that works on ANY content type:
- Articles
- Forum threads with multiple posts
- Discussions
- Blog posts
- etc.
"""

import json
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import re

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """Content extracted from a page"""
    title: str
    content: str  # Main extracted content
    publish_date: Optional[datetime] = None
    content_type: str = "article"  # article, forum_thread, discussion, etc.
    metadata: Optional[Dict] = None  # post_count, author, etc.


def clean_html_for_extraction(html: str, max_chars: int = 20000) -> str:
    """
    Clean HTML for content extraction.
    Keep more content than analysis (20K vs 8K).
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove noise but keep content
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'nav', 'header', 'footer']):
        tag.decompose()
    
    # Get text with structure preserved
    text = soup.get_text(separator='\n', strip=True)
    
    # Truncate if too long
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (content truncated for LLM)"
    
    return text


async def quick_date_check(html: str, url: str, intent: Dict) -> Tuple[bool, Optional[datetime]]:
    """
    Fast date extraction and validation BEFORE full content extraction.
    This saves expensive LLM calls for old articles.
    
    Returns:
        (should_process, publish_date)
        - should_process: True if article passes date filter or date unknown
        - publish_date: Extracted date or None
    """
    settings = get_settings()
    time_range_days = intent.get('time_range_days', 7)
    
    # Step 1: Try to extract date from HTML metadata (fast, no LLM)
    soup = BeautifulSoup(html, 'html.parser')
    
    # Common meta tags for dates
    date_meta_tags = [
        ('meta', {'property': 'article:published_time'}),
        ('meta', {'name': 'publish-date'}),
        ('meta', {'name': 'date'}),
        ('meta', {'property': 'og:published_time'}),
        ('time', {'datetime': True}),
    ]
    
    extracted_date = None
    
    for tag_name, attrs in date_meta_tags:
        tag = soup.find(tag_name, attrs)
        if tag:
            date_str = tag.get('content') or tag.get('datetime')
            if date_str:
                try:
                    # Parse ISO format or common formats
                    extracted_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    logger.info(f"📅 Found date in metadata: {extracted_date.strftime('%Y-%m-%d')}")
                    break
                except Exception:
                    continue
    
    # Step 2: If no metadata date, use fast LLM extraction (GPT-4o-mini)
    if not extracted_date:
        # Get page title and first 2000 chars for date detection
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ""
        
        # Look for date patterns in visible text
        page_text = soup.get_text(separator='\n', strip=True)[:2000]
        
        prompt = f"""Extract the publication date from this page.

URL: {url}
Title: {title}

Content (first 2000 chars):
{page_text}

Look for dates in common formats:
- "November 5, 2025" or "Nov 5, 2025"
- "2025-11-05"
- "Published: [date]"
- "Posted on [date]"

Return ONLY JSON (no markdown):
{{
  "found": true/false,
  "date": "YYYY-MM-DD" or null,
  "confidence": 0.0-1.0
}}

If no clear publication date found, return {{"found": false, "date": null, "confidence": 0.0}}"""
        
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",  # Fast and cheap for simple extraction
                api_key=settings.openai_api_key,
                temperature=0
            )
            
            response = await llm.ainvoke(prompt)
            response_text = response.content.strip()
            
            # Clean markdown
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(json_lines)
            
            result = json.loads(response_text)
            
            if result.get('found') and result.get('date'):
                extracted_date = datetime.strptime(result['date'], '%Y-%m-%d')
                logger.info(f"📅 LLM extracted date: {extracted_date.strftime('%Y-%m-%d')} (confidence: {result.get('confidence', 0.0)})")
        
        except Exception as e:
            logger.warning(f"Quick date extraction failed: {e}")
            # If date extraction fails, allow processing (better to include than exclude)
            return (True, None)
    
    # Step 3: Check if date passes filter
    if extracted_date:
        # For very recent time ranges (0-1 days), be lenient
        if time_range_days <= 1:
            days_back = 2  # Include today + yesterday
        else:
            days_back = time_range_days
        
        cutoff = datetime.now() - __import__('datetime').timedelta(days=days_back)
        
        if extracted_date < cutoff:
            logger.info(f"❌ Date too old: {extracted_date.strftime('%Y-%m-%d')} (cutoff: {cutoff.strftime('%Y-%m-%d')})")
            return (False, extracted_date)
        else:
            logger.info(f"✅ Date passes filter: {extracted_date.strftime('%Y-%m-%d')}")
            return (True, extracted_date)
    
    # If no date found, allow processing (we'll let LLM relevance check handle it)
    logger.info("⚠️ No date found, allowing processing")
    return (True, None)


async def extract_content_with_llm(
    html: str,
    url: str,
    page_type: str,
    intent: Dict
) -> Optional[ExtractedContent]:
    """
    Extract content from a page using LLM.
    Works on any content structure: articles, forums, discussions, etc.
    
    Args:
        html: Page HTML
        url: Page URL
        page_type: Type detected by page_decision (article, forum_thread, etc.)
        intent: User intent dict
        
    Returns:
        ExtractedContent or None if extraction fails
    """
    settings = get_settings()
    
    # Clean HTML
    cleaned_html = clean_html_for_extraction(html, max_chars=15000)
    
    # Get page title from HTML
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    html_title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Build extraction prompt based on page type
    topic = intent.get('topic', '')
    
    prompt = f"""Extract the main content from this page.

PAGE TYPE: {page_type}
URL: {url}
USER LOOKING FOR: {topic}

EXTRACTION RULES:

If this is a FORUM THREAD or DISCUSSION:
- Extract ALL posts/comments with:
  - Username (who said it)
  - Post date (if visible)
  - Post content
- Preserve conversation flow
- Format: "Username (Date): Post content"

If this is an ARTICLE or BLOG POST:
- Extract the main text content
- Extract publish date if visible
- Extract author if available
- Don't include ads, navigation, or related content

If this is a PRESS RELEASE:
- Extract the full press release text
- Extract publish date and company name
- Include all key details

If this is a RESEARCH REPORT or WHITEPAPER:
- Extract the executive summary and key findings
- Extract publication date and authors
- Include methodology if present

If this is an EVENT PAGE:
- Extract event details (date, location, description)
- Extract speaker/participant information
- Include registration or attendance details if present

PAGE CONTENT:
{cleaned_html}

OUTPUT FORMAT (JSON only, no markdown):
{{
  "title": "Content title",
  "content": "The extracted content in readable format. For forums, include all posts with usernames. For articles, include the full text. For reports, include executive summary and key findings.",
  "publish_date": "YYYY-MM-DD if found, otherwise null",
  "content_type": "article" | "forum_thread" | "discussion" | "blog_post" | "press_release" | "research_report" | "event" | "other",
  "metadata": {{
    "author": "author name if applicable",
    "post_count": number_of_posts if forum,
    "usernames": ["list", "of", "usernames"] if forum,
    "event_date": "YYYY-MM-DD if event",
    "company": "company name if press release"
  }}
}}"""
    
    try:
        # Use GPT-4o for content extraction (needs understanding)
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0
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
                if in_block or (not line.startswith("```")):
                    json_lines.append(line)
            response_text = "\n".join(json_lines)
        
        result = json.loads(response_text)
        
        # Parse date if provided
        publish_date = None
        if result.get('publish_date'):
            try:
                publish_date = datetime.strptime(result['publish_date'], '%Y-%m-%d')
            except Exception:
                logger.warning(f"Failed to parse date: {result.get('publish_date')}")
        
        # Validate we got actual content
        content = result.get('content', '').strip()
        if not content or len(content) < 50:
            logger.warning(f"Extracted content too short ({len(content)} chars)")
            return None
        
        # Use HTML title as fallback
        title = result.get('title', '').strip() or html_title or "Untitled"
        
        extracted = ExtractedContent(
            title=title,
            content=content,
            publish_date=publish_date,
            content_type=result.get('content_type', 'article'),
            metadata=result.get('metadata', {})
        )
        
        logger.info(f"✅ Extracted content: {len(content)} chars, type: {extracted.content_type}")
        if extracted.metadata and 'post_count' in extracted.metadata:
            logger.info(f"   Forum thread with {extracted.metadata['post_count']} posts")
        
        return extracted
        
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON for content extraction: {e}")
        logger.error(f"Response: {response_text[:300]}")
        return None
    
    except Exception as e:
        logger.error(f"Content extraction failed: {e}")
        return None


async def validate_relevance(
    content: ExtractedContent,
    intent: Dict,
    skip_date_check: bool = False
) -> bool:
    """
    Quick relevance check using GPT-4o-mini.
    Filters out garbage content before it goes into summary.
    
    Args:
        content: Extracted content
        intent: User intent dict
        skip_date_check: If True, skip date validation (already done earlier)
        
    Returns:
        True if relevant, False otherwise
    """
    settings = get_settings()
    
    topic = intent.get('topic', '')
    time_range_days = intent.get('time_range_days', 7)
    
    # Check time range first (cheap check) - only if not already checked
    if not skip_date_check and content.publish_date:
        # For very recent time ranges (0-1 days), be lenient
        # Include content from the past 2 calendar days to account for timezone/timing issues
        if time_range_days <= 1:
            days_back = 2  # Include today + yesterday
        else:
            days_back = time_range_days
        
        cutoff = datetime.now() - __import__('datetime').timedelta(days=days_back)
        if content.publish_date < cutoff:
            logger.info(f"❌ Content too old: {content.publish_date.strftime('%Y-%m-%d')}")
            return False
    
    # LLM relevance check
    prompt = f"""Is this content relevant to the user's request?

USER WANTS: {topic}
TIME RANGE: Last {time_range_days} days

CONTENT:
- Title: {content.title}
- Date: {content.publish_date.strftime('%Y-%m-%d') if content.publish_date else 'Unknown'}
- Preview: {content.content[:500]}

Answer with JSON only (no markdown):
{{
  "is_relevant": true/false,
  "reason": "Brief explanation (1 sentence)"
}}"""
    
    try:
        # Use GPT-4o-mini for simple yes/no
        llm = ChatOpenAI(
            model="gpt-4o-mini",
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
        is_relevant = result.get('is_relevant', False)
        reason = result.get('reason', 'No reason')
        
        if is_relevant:
            logger.info(f"✅ Content relevant: {reason}")
        else:
            logger.info(f"❌ Content not relevant: {reason}")
        
        return is_relevant
        
    except Exception as e:
        logger.error(f"Relevance validation failed: {e}")
        # If validation fails, assume relevant (don't lose content)
        return True

