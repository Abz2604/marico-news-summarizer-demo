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
from .focus_agent import extract_focused_content

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
    
    # ═════════════════════════════════════════════════════════════════════════
    # FOCUSAGENT PATTERN: Pre-filter content to reduce tokens by 50-70%
    # ═════════════════════════════════════════════════════════════════════════
    # Stage 1: Lightweight LLM extracts ONLY relevant chunks (CHEAP)
    # Stage 2: GPT-4o processes focused content (EXPENSIVE but on less data)
    # ═════════════════════════════════════════════════════════════════════════
    
    try:
        focused_content, original_size = await extract_focused_content(
            html=html,
            url=url,
            intent=intent,
            max_chunks=10
        )
        cleaned_html = focused_content
        logger.info(f"✨ FocusAgent: Using focused content ({len(focused_content)} chars from {original_size} bytes)")
    except Exception as e:
        logger.warning(f"FocusAgent failed, using standard cleaning: {e}")
        # Fallback to standard cleaning
    cleaned_html = clean_html_for_extraction(html, max_chars=15000)
    
    # Get page title from HTML
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    html_title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Build extraction prompt based on page type
    topic = intent.get('topic', '')
    
    prompt = f"""You are an expert content extraction specialist with deep understanding of web content structures.

═══════════════════════════════════════════════════════════════════════════════
🎯 MISSION: COMPREHENSIVE CONTENT EXTRACTION
═══════════════════════════════════════════════════════════════════════════════
PAGE TYPE: {page_type}
URL: {url}
USER'S GOAL: {topic}

═══════════════════════════════════════════════════════════════════════════════
📋 EXTRACTION STRATEGY BY CONTENT TYPE
═══════════════════════════════════════════════════════════════════════════════

**FORUM THREAD or DISCUSSION:**
Goal: Capture the complete conversation
✓ Extract EVERY post/comment (don't summarize!)
✓ Format: "Username (Date): Post content"
✓ Preserve chronological order
✓ Include quoted text if it adds context
✓ Note: Forums are multi-voice - capture all perspectives
Example output:
```
User123 (2024-11-05): Original question here...
ExpertUser (2024-11-05): Detailed answer...
User456 (2024-11-06): Follow-up question...
```

**ARTICLE or BLOG POST:**
Goal: Extract the complete narrative
✓ Full article text (introduction → body → conclusion)
✓ Include subheadings for structure
✓ Extract inline quotes, statistics, key facts
✓ Preserve formatting that aids comprehension
✗ Skip: Ads, "Related Articles", navigation, social share buttons

**PRESS RELEASE:**
Goal: Capture all official information
✓ Full text including dateline, body, boilerplate
✓ Company name and location
✓ Contact information (if present)
✓ Key facts in bullet format if structured that way
✓ Exact quotes from executives

**RESEARCH REPORT or WHITEPAPER:**
Goal: Extract insights and methodology
✓ Executive summary (complete)
✓ Key findings (all of them)
✓ Methodology overview
✓ Data tables or statistics (summarize if long)
✓ Conclusions and recommendations

**EVENT PAGE:**
Goal: Complete event logistics
✓ Event name and description
✓ Date, time, timezone
✓ Location (physical address or virtual link)
✓ Speakers/participants with bios if available
✓ Agenda or schedule
✓ Registration requirements

═══════════════════════════════════════════════════════════════════════════════
🧠 ADVANCED EXTRACTION TECHNIQUES
═══════════════════════════════════════════════════════════════════════════════

**Date Intelligence:**
Look for dates in these locations (priority order):
1. Meta tags: <meta property="article:published_time">
2. Structured data: JSON-LD schema
3. Visible date labels: "Published:", "Posted:", "Date:"
4. URL patterns: /2024/11/05/ or ?date=2024-11-05
5. Relative dates: "2 days ago" (calculate actual date if possible)

**Content Quality Signals:**
High-quality extraction includes:
- Main narrative/discussion (not noise)
- Relevant metadata (author, date, source)
- Structured formatting (paragraphs, lists, quotes)
- Context that helps understanding

**What to EXCLUDE:**
✗ Navigation menus
✗ Advertisements
✗ "Related Articles" sections
✗ Cookie banners
✗ Social sharing buttons
✗ Footer/copyright text
✗ Generic website info

═══════════════════════════════════════════════════════════════════════════════
📄 PAGE CONTENT TO ANALYZE
═══════════════════════════════════════════════════════════════════════════════
{cleaned_html}

═══════════════════════════════════════════════════════════════════════════════
📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return ONLY valid JSON (no markdown, no extra text):

{{
  "title": "Extracted title (from <title>, <h1>, or article heading)",
  "content": "Complete extracted content in readable format. For forums: all posts with usernames. For articles: full text with structure. Be comprehensive - this is the PRIMARY VALUE.",
  "publish_date": "YYYY-MM-DD if found, otherwise null",
  "content_type": "article" | "forum_thread" | "discussion" | "blog_post" | "press_release" | "research_report" | "event" | "other",
  "metadata": {{
    "author": "author name (null if not found)",
    "post_count": number_of_posts_if_forum,
    "usernames": ["unique", "usernames", "in", "forum"],
    "event_date": "YYYY-MM-DD if event page",
    "company": "company name if press release",
    "word_count": approximate_word_count_of_content,
    "has_quotes": true/false,
    "has_statistics": true/false
  }}
}}

CRITICAL REQUIREMENTS:
1. Content field must be COMPREHENSIVE (not a summary!)
2. Preserve structure that aids understanding (paragraphs, lists)
3. Extract ALL relevant information, don't be selective
4. For forums: capture EVERY post, not just highlights
5. Date must be YYYY-MM-DD format (null if not found)

Think like a meticulous researcher. Extract everything that matters."""
    
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
    
    # LLM relevance check (date already validated above if skip_date_check=False)
    prompt = f"""Is this content relevant to the user's request?

USER WANTS: {topic}
TIME RANGE: Last {time_range_days} days (date already validated - focus on topic relevance)
TODAY'S DATE: {datetime.now().strftime('%Y-%m-%d')} (for reference)

CONTENT:
- Title: {content.title}
- Date: {content.publish_date.strftime('%Y-%m-%d') if content.publish_date else 'Unknown'}
- Preview: {content.content[:500]}

IMPORTANT: 
- If date validation was already done (skip_date_check=False), focus ONLY on topic/content relevance
- Don't re-validate the date - assume it's already been checked
- Only check: Does the content match the user's topic/intent?

Answer with JSON only (no markdown):
{{
  "is_relevant": true/false,
  "reason": "Brief explanation focusing on topic relevance (1 sentence)"
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

