"""
Date Extraction from Articles
LLM-First approach for extracting publish dates
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from bs4 import BeautifulSoup

from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


class DateParser:
    """Extract publish dates from article HTML using multiple strategies"""
    
    def __init__(self, openai_api_key: str):
        settings = get_settings()
        model_name = settings.date_parser_model or settings.openai_model or "gpt-4o-mini"
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=openai_api_key
        )
    
    async def extract_date(self, html: str, url: str) -> Tuple[Optional[datetime], float, str]:
        """
        Extract publish date from article HTML.
        
        Returns:
            (datetime | None, confidence: 0-1, method: str)
        """
        
        # Strategy 1: Metadata extraction (FIRST - most reliable and fast)
        metadata_date, metadata_conf = self._extract_from_metadata(html)
        if metadata_date and metadata_conf > 0.8:
            logger.info(f"✅ Date extracted from metadata: {metadata_date} (confidence: {metadata_conf:.2f})")
            return metadata_date, metadata_conf, "metadata"
        
        # Strategy 2: Structured patterns in HTML text (fast)
        pattern_date, pattern_conf = self._extract_from_patterns(html)
        if pattern_date and pattern_conf > 0.6:
            logger.info(f"✅ Date extracted from patterns: {pattern_date} (confidence: {pattern_conf:.2f})")
            return pattern_date, pattern_conf, "patterns"
        
        # Strategy 3: LLM-based extraction (fallback - slower but handles edge cases)
        llm_date, llm_conf = await self._llm_extract(html, url)
        if llm_date and llm_conf > 0.7:
            # 🔍 VALIDATION: If LLM date is >6 months old, cross-check with metadata
            days_old = (datetime.now() - llm_date).days
            if days_old > 180 and metadata_date:
                logger.warning(f"⚠️ LLM date seems old ({days_old} days), cross-checking with metadata...")
                # Prefer metadata if it's more recent
                if metadata_date and (datetime.now() - metadata_date).days < days_old:
                    logger.info(f"✅ Using metadata date {metadata_date} instead of LLM date {llm_date}")
                    return metadata_date, metadata_conf, "metadata_validated"
            
            logger.info(f"✅ Date extracted via LLM: {llm_date} (confidence: {llm_conf:.2f})")
            return llm_date, llm_conf, "llm"
        
        # Fallback: Use metadata even with lower confidence if available
        if metadata_date:
            logger.info(f"✅ Date extracted from metadata (fallback): {metadata_date} (confidence: {metadata_conf:.2f})")
            return metadata_date, metadata_conf, "metadata_fallback"
        
        # No reliable date found
        logger.warning(f"⚠️ Could not extract date from {url[:60]}")
        return None, 0.0, "none"
    
    async def _llm_extract(self, html: str, url: str) -> Tuple[Optional[datetime], float]:
        """
        Use LLM to extract publish date from HTML.
        Works with any format: "2 days ago", "Oct 30, 2024", "yesterday"
        """
        
        # Extract text content and metadata section
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get metadata section (likely contains date info)
        metadata_section = ""
        for tag in soup.find_all(['time', 'meta', 'script']):
            metadata_section += str(tag)[:500] + "\n"
        
        # Get first 1500 chars of visible text (usually has date near top)
        text_content = soup.get_text()[:1500]
        
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        
        llm_prompt = f"""Extract the article publish date from the HTML content.

URL: {url}

METADATA SECTION:
{metadata_section[:1000]}

ARTICLE TEXT (first 1500 chars):
{text_content}

TASK:
Find when this article was published. Look for:
- <time> tags with datetime attributes
- Meta tags (article:published_time, datePublished, etc.)
- Visible dates near the article title
- Relative dates ("2 days ago", "yesterday", "1 hour ago")

IMPORTANT CONTEXT:
- Today's date is: {today.strftime("%Y-%m-%d")} (Current year: {current_year})
- When the year is missing or ambiguous, prefer {current_year}
- If month > current month ({current_month}) and no year is specified, the article is likely from {current_year - 1}
- Content articles are typically recent (within 1-2 years)
- If you see "Oct 17" or "October 17" without a year, default to {current_year}

Respond with ONLY valid JSON:
{{
  "publish_date": "YYYY-MM-DD" or null if not found,
  "confidence": 0.0-1.0 (how confident you are),
  "reasoning": "Brief explanation of where you found the date"
}}

If multiple dates are present, choose the PUBLISH date (not update/modified date).
"""
        
        try:
            response = await self.llm.ainvoke(llm_prompt)
            response_text = response.content.strip()
            
            # Parse JSON
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(json_lines)
            
            result = json.loads(response_text)
            
            date_str = result.get("publish_date")
            confidence = result.get("confidence", 0.5)
            
            if not date_str or date_str == "null":
                return None, 0.0
            
            # Parse the date string
            date = datetime.strptime(date_str, "%Y-%m-%d")
            
            # Sanity check: date should be in past and not too old (< 3 years for news)
            now = datetime.now()
            days_old = (now - date).days
            
            # Future dates are definitely wrong
            if date > now:
                logger.warning(f"⚠️ LLM returned future date: {date}")
                return None, 0.0
            
            # News articles >3 years old are suspicious (likely wrong year)
            # But don't reject completely - return with lowered confidence
            if days_old > 1095:  # 3 years
                logger.warning(f"⚠️ LLM returned old date: {date} ({days_old} days old), lowering confidence")
                return date, min(confidence * 0.5, 0.7)  # Reduce confidence so metadata can override
            
            return date, float(confidence)
            
        except Exception as e:
            logger.error(f"❌ LLM date extraction failed: {e}")
            return None, 0.0
    
    def _extract_from_metadata(self, html: str) -> Tuple[Optional[datetime], float]:
        """
        Extract date from structured metadata (JSON-LD, Open Graph, meta tags).
        Fast and reliable when present.
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Strategy 1: JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                
                # Handle array of objects
                if isinstance(data, list):
                    data = data[0] if data else {}
                
                # Look for datePublished
                date_str = data.get('datePublished') or data.get('publishDate')
                if date_str:
                    date = self._parse_iso_date(date_str)
                    if date:
                        return date, 0.95  # High confidence
            except Exception:
                continue
        
        # Strategy 2: Open Graph / Twitter Cards
        meta_tags = [
            'article:published_time',
            'article:published',
            'og:published_time',
            'og:article:published_time',
            'datePublished',
            'publish_date',
            'publication_date'
        ]
        
        for tag_name in meta_tags:
            tag = soup.find('meta', property=tag_name) or soup.find('meta', attrs={'name': tag_name})
            if tag and tag.get('content'):
                date = self._parse_iso_date(tag['content'])
                if date:
                    return date, 0.90  # High confidence
        
        # Strategy 3: <time> tags
        time_tag = soup.find('time', datetime=True)
        if time_tag:
            date = self._parse_iso_date(time_tag['datetime'])
            if date:
                return date, 0.85
        
        return None, 0.0
    
    def _extract_from_patterns(self, html: str) -> Tuple[Optional[datetime], float]:
        """
        Extract date from common text patterns in HTML.
        Lower confidence but works when metadata is missing.
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()[:3000]  # First 3000 chars
        
        # Pattern 1: "October 30, 2024" or "Oct 30, 2024"
        pattern1 = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})'
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(0)
                date = datetime.strptime(date_str, "%b %d, %Y") if ',' in date_str else datetime.strptime(date_str, "%B %d %Y")
                return date, 0.70
            except Exception:
                pass
        
        # Pattern 2: "2024-10-30" or "30/10/2024"
        pattern2 = r'(\d{4})-(\d{2})-(\d{2})'
        match = re.search(pattern2, text)
        if match:
            try:
                date = datetime.strptime(match.group(0), "%Y-%m-%d")
                if datetime.now().year - 5 < date.year <= datetime.now().year:
                    return date, 0.65
            except Exception:
                pass
        
        # Pattern 3: Relative dates in text ("2 days ago", "yesterday")
        relative_match = re.search(r'(\d+)\s+(day|hour|week)s?\s+ago', text, re.IGNORECASE)
        if relative_match:
            try:
                num = int(relative_match.group(1))
                unit = relative_match.group(2).lower()
                
                if unit == 'day':
                    date = datetime.now() - timedelta(days=num)
                elif unit == 'hour':
                    date = datetime.now() - timedelta(hours=num)
                elif unit == 'week':
                    date = datetime.now() - timedelta(weeks=num)
                
                return date, 0.60
            except Exception:
                pass
        
        if 'yesterday' in text.lower()[:500]:
            date = datetime.now() - timedelta(days=1)
            return date, 0.55
        
        return None, 0.0
    
    def _parse_iso_date(self, date_str: str) -> Optional[datetime]:
        """Parse ISO 8601 date string to datetime"""
        
        try:
            # Remove timezone info for simplicity (just get the date)
            date_str = re.sub(r'[+-]\d{2}:?\d{2}$', '', date_str)
            date_str = date_str.replace('Z', '')
            
            # Try common formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y/%m/%d",
            ]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None


async def extract_article_date(html: str, url: str) -> Tuple[Optional[datetime], float, str]:
    """
    Convenience function to extract article publish date.
    
    Returns:
        (datetime | None, confidence: 0-1, method: str)
    """
    settings = get_settings()
    parser = DateParser(settings.openai_api_key)
    return await parser.extract_date(html, url)

