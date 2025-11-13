"""
Content Extractor Tool - Extract content from individual pages

Uses LLM to extract clean, structured content from articles/threads.
"""

import json
import logging
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup
from ..ai_factory import get_ai_factory
from ..types import ExtractedContent
from ..data_processors import clean_html_for_llm

logger = logging.getLogger(__name__)


async def extract_content(
    html: str,
    url: str,
    page_type: str,
    topic: str
) -> Optional[ExtractedContent]:
    """
    Extract content from a page using LLM.
    
    Args:
        html: Page HTML (should be cleaned)
        url: Page URL
        page_type: Type of page (article, forum_thread, etc.)
        topic: Topic context for extraction
        
    Returns:
        ExtractedContent or None if extraction fails
    """
    # Get page title
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    html_title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Clean HTML for extraction (more content than analysis)
    cleaned_html = clean_html_for_llm(html, max_chars=20000, preserve_structure=True)
    
    prompt = f"""Extract content from this page.

URL: {url}
Page Type: {page_type}
User Topic: {topic}

PAGE CONTENT:
{cleaned_html}

TASK: Extract the main content from this page.

For ARTICLES:
- Extract full article text (introduction → body → conclusion)
- Include subheadings for structure
- Preserve important formatting (lists, quotes)
- Skip: Ads, navigation, "Related Articles", social buttons

For FORUM THREADS:
- Extract ALL posts/comments (don't summarize!)
- Format: "Username (Date): Post content"
- Preserve chronological order
- Include quoted text if it adds context

Return ONLY valid JSON (no markdown):
{{
  "title": "Extracted title",
  "content": "Complete extracted content",
  "publish_date": "YYYY-MM-DD if found, otherwise null",
  "content_type": "{page_type}",
  "metadata": {{
    "word_count": approximate_word_count,
    "has_quotes": true/false,
    "has_statistics": true/false
  }}
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
        
        # Parse date if provided
        publish_date = None
        if result.get('publish_date'):
            try:
                publish_date = datetime.strptime(result['publish_date'], '%Y-%m-%d')
            except Exception:
                pass
        
        # Validate content
        content = result.get('content', '').strip()
        if not content or len(content) < 50:
            logger.warning(f"Extracted content too short ({len(content)} chars)")
            return None
        
        title = result.get('title', '').strip() or html_title or "Untitled"
        
        extracted = ExtractedContent(
            url=url,
            title=title,
            content=content,
            publish_date=publish_date,
            content_type=result.get('content_type', page_type),
            metadata=result.get('metadata', {})
        )
        
        logger.info(f"Extracted content: {len(content)} chars, type: {extracted.content_type}")
        
        return extracted
        
    except Exception as e:
        logger.error(f"Content extraction failed: {e}")
        return None

