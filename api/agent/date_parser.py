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
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=openai_api_key
        )
    
    async def extract_date(self, html: str, url: str) -> Tuple[Optional[datetime], float, str]:
        """
        Extract publish date from article HTML.
        
        Returns:
            (datetime | None, confidence: 0-1, method: str)
        """
        
        # Strategy 1: LLM-based extraction (primary)
        date, confidence = await self._llm_extract(html, url)
        if date and confidence > 0.7:
            logger.info(f"✅ Date extracted via LLM: {date} (confidence: {confidence:.2f})")
            return date, confidence, "llm"
        
        # Strategy 2: Metadata extraction (fast fallback)
        date, confidence = self._extract_from_metadata(html)
        if date and confidence > 0.8:
            logger.info(f"✅ Date extracted from metadata: {date} (confidence: {confidence:.2f})")
            return date, confidence, "metadata"
        
        # Strategy 3: Structured patterns in HTML text
        date, confidence = self._extract_from_patterns(html)
        if date and confidence > 0.6:
            logger.info(f"✅ Date extracted from patterns: {date} (confidence: {confidence:.2f})")
            return date, confidence, "patterns"
        
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

Today's date is: {datetime.now().strftime("%Y-%m-%d")}

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
            
            # Sanity check: date should be in past and not too old (< 5 years)
            now = datetime.now()
            if date > now or (now - date).days > 1825:  # 5 years
                logger.warning(f"⚠️ LLM returned suspicious date: {date}")
                return None, 0.0
            
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

