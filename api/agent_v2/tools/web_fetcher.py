"""
Web Fetcher Tool - Bright Data Integration

Fetches web pages using Bright Data web unlocker.
"""

import logging
from typing import Optional
from agent_v2.data_processors import clean_html_for_llm
from agent.brightdata_fetcher import fetch_url

logger = logging.getLogger(__name__)


async def fetch_page(
    url: str,
    render_js: bool = False,
    clean: bool = True
) -> Optional[str]:
    """
    Fetch a web page using Bright Data.
    
    Args:
        url: URL to fetch
        render_js: Whether to render JavaScript (for lazy-loaded content)
        clean: Whether to clean HTML for LLM processing
        
    Returns:
        HTML content (cleaned if clean=True) or None if failed
    """
    logger.info(f"Fetching: {url} (render_js={render_js})")
    
    html = await fetch_url(url, timeout=60, render_js=render_js)
    
    if not html:
        logger.warning(f"Failed to fetch: {url}")
        return None
    
    if clean:
        # Clean HTML for LLM processing
        cleaned = clean_html_for_llm(html, max_chars=20000)
        logger.debug(f"Cleaned HTML: {len(html)} → {len(cleaned)} chars")
        return cleaned
    
    return html

