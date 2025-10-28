"""
NewsAPI fallback for when web scraping fails.
This provides a reliable data source for demos and production fallback.

To use:
1. Get free API key from https://newsapi.org/
2. Set NEWSAPI_KEY in your .env file
3. The system will automatically fallback if scraping fails
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file
except ImportError:
    pass  # dotenv not available, assume env vars are set

from .types import ArticleContent

logger = logging.getLogger(__name__)


async def fetch_news_from_api(
    query: str,
    max_articles: int = 3,
    days_back: int = 7,
    language: str = "en",
) -> List[ArticleContent]:
    """
    Fetch news articles using NewsAPI.org as a fallback source.
    
    Args:
        query: Search query (e.g., "Marico", "FMCG company")
        max_articles: Maximum number of articles to fetch
        days_back: How many days back to search
        language: Article language code
        
    Returns:
        List of ArticleContent objects
    """
    api_key = os.getenv("NEWSAPI_KEY")
    
    if not api_key:
        logger.warning("NEWSAPI_KEY not configured, skipping NewsAPI fallback")
        return []
    
    try:
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": language,
            "apiKey": api_key,
            "pageSize": min(max_articles * 2, 20),  # Get more to filter
        }
        
        logger.info(f"Fetching news from NewsAPI: query='{query}', from={from_date}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        if data.get("status") != "ok":
            logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
            return []
        
        articles = data.get("articles", [])
        logger.info(f"NewsAPI returned {len(articles)} articles")
        
        result: List[ArticleContent] = []
        
        for article in articles[:max_articles]:
            # Skip articles without content
            description = article.get("description", "")
            content = article.get("content", "")
            
            if not description and not content:
                continue
            
            # Combine description and content
            text_parts = []
            if description:
                text_parts.append(description)
            if content:
                # NewsAPI often truncates with "[+X chars]", clean it up
                content_clean = content.split("[+")[0].strip()
                if content_clean and content_clean not in text_parts:
                    text_parts.append(content_clean)
            
            full_text = " ".join(text_parts)
            
            # Skip very short articles
            if len(full_text) < 100:
                continue
            
            published_at = article.get("publishedAt")
            fetched_at = datetime.fromisoformat(published_at.replace("Z", "+00:00")) if published_at else datetime.utcnow()
            
            result.append(
                ArticleContent(
                    url=article.get("url", ""),
                    resolved_url=article.get("url", ""),
                    title=article.get("title", ""),
                    text=full_text,
                    fetched_at=fetched_at,
                )
            )
            
            logger.info(f"Added article: {article.get('title', 'Unknown')[:50]}...")
        
        logger.info(f"Returning {len(result)} articles from NewsAPI")
        return result
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching from NewsAPI: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching from NewsAPI: {e}")
        return []


async def get_company_news(
    company_name: str,
    stock_ticker: Optional[str] = None,
    max_articles: int = 3,
    days_back: int = 7,
) -> List[ArticleContent]:
    """
    Get company-specific news using smart query construction.
    
    Args:
        company_name: Company name (e.g., "Marico")
        stock_ticker: Optional stock ticker (e.g., "MARICO.NS")
        max_articles: Number of articles to fetch
        days_back: Days to search back
        
    Returns:
        List of ArticleContent objects
    """
    # Build a smart query
    queries = [company_name]
    if stock_ticker:
        queries.append(stock_ticker)
    
    # Try with company name first
    query = f'"{company_name}"'
    if stock_ticker:
        query += f' OR "{stock_ticker}"'
    
    return await fetch_news_from_api(
        query=query,
        max_articles=max_articles,
        days_back=days_back,
    )


# Quick mapping for demo purposes
COMPANY_NAME_MAP = {
    "marico": "Marico Limited",
    "m13": "Marico",  # MoneyControl code
    # Add more mappings as needed
}


async def extract_company_from_url(url: str) -> Optional[str]:
    """Extract company name from MoneyControl or similar URLs."""
    import re
    
    # MoneyControl pattern
    mc_match = re.search(r"moneycontrol\.com/.*?/([^/]+)/", url)
    if mc_match:
        slug = mc_match.group(1).lower()
        return COMPANY_NAME_MAP.get(slug, slug.replace("-", " ").title())
    
    # Generic domain-based extraction
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    company = domain.split(".")[0]
    return company.title()

