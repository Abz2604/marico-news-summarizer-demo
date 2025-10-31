"""
Bright Data Web Unlocker Integration
Clean, simple, professional HTTP fetching that bypasses all blocks.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv
import asyncio

load_dotenv()

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 2  # seconds


class BrightDataFetcher:
    """
    Professional web fetching using Bright Data's Scraping Browser.
    Bypasses all anti-bot measures, CAPTCHAs, and blocks.
    """
    
    def __init__(self):
        # Get API credentials
        self.api_token = os.getenv("BRIGHTDATA_API_KEY")
        self.zone = os.getenv("BRIGHTDATA_ZONE", "web_unlocker1_marico")
        
        if not self.api_token:
            raise ValueError(
                "BRIGHTDATA_API_KEY not found in environment variables!\n"
                "Check your .env file."
            )
        
        self.api_url = "https://api.brightdata.com/request"
        logger.info(f"BrightData fetcher initialized with zone: {self.zone}")
    
    async def fetch(
        self, 
        url: str, 
        timeout: int = 60, 
        max_retries: int = MAX_RETRIES,
        render_js: bool = False,
        wait_for_selector: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch URL content using Bright Data with retry logic.
        
        Args:
            url: Target URL to fetch
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts (default: 5)
            render_js: Whether to render JavaScript (for dynamic content, lazy loading)
            wait_for_selector: CSS selector to wait for before returning (e.g., ".load-more")
            
        Returns:
            HTML content or None if failed after all retries
        """
        logger.info(f"Fetching with BrightData: {url} (render_js={render_js})")
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_retries} for {url}")
                
                # Use requests in thread pool for async compatibility
                loop = asyncio.get_event_loop()
                html = await loop.run_in_executor(
                    None, 
                    self._fetch_sync, 
                    url, 
                    timeout,
                    render_js,
                    wait_for_selector
                )
                
                if html:
                    logger.info(f"✅ Success on attempt {attempt}")
                    return html
                else:
                    logger.warning(f"⚠️ Attempt {attempt} returned no content")
                        
            except Exception as e:
                logger.error(f"❌ Attempt {attempt} failed: {e}")
                
            # If we have more retries left, wait with exponential backoff
            if attempt < max_retries:
                backoff_time = INITIAL_BACKOFF * (2 ** (attempt - 1))  # Exponential backoff: 2s, 4s, 8s, 16s
                logger.info(f"⏱️ Waiting {backoff_time}s before retry...")
                await asyncio.sleep(backoff_time)
        
        logger.error(f"❌ All {max_retries} attempts failed for {url}")
        return None
    
    def _fetch_sync(
        self, 
        url: str, 
        timeout: int,
        render_js: bool = False,
        wait_for_selector: Optional[str] = None
    ) -> Optional[str]:
        """Synchronous fetch using Bright Data API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "zone": self.zone,
                "url": url,
                "format": "raw"  # Get raw HTML
            }
            
            # Add JavaScript rendering if requested (for dynamic content)
            if render_js:
                payload["render_js"] = True
                payload["wait"] = 3000  # Wait 3s for JS to execute
                logger.info("🚀 JavaScript rendering enabled (for lazy-loaded content)")
                
                if wait_for_selector:
                    payload["wait_for_selector"] = wait_for_selector
                    logger.info(f"⏳ Waiting for selector: {wait_for_selector}")
            
            logger.info(f"Bright Data API request: zone={self.zone}, url={url}, render_js={render_js}")
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                html = response.text
                logger.info(f"✅ Success! HTML length: {len(html):,} bytes")
                return html
            else:
                logger.error(f"❌ API failed ({response.status_code})")
                logger.error(f"Response: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Fetch error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def fetch_multiple(self, urls: list[str], timeout: int = 30) -> dict[str, Optional[str]]:
        """
        Fetch multiple URLs efficiently.
        
        Args:
            urls: List of URLs to fetch
            timeout: Timeout per request
            
        Returns:
            Dict mapping URL to HTML content
        """
        import asyncio
        
        results = {}
        tasks = [self.fetch(url, timeout) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, response in zip(urls, responses):
            if isinstance(response, Exception):
                logger.error(f"Failed {url}: {response}")
                results[url] = None
            else:
                results[url] = response
        
        return results


# Global instance (singleton pattern)
_fetcher: Optional[BrightDataFetcher] = None


def get_fetcher() -> BrightDataFetcher:
    """Get or create the global BrightData fetcher instance."""
    global _fetcher
    if _fetcher is None:
        _fetcher = BrightDataFetcher()
    return _fetcher


async def fetch_url(
    url: str, 
    timeout: int = 30,
    render_js: bool = False,
    wait_for_selector: Optional[str] = None
) -> Optional[str]:
    """
    Simple convenience function for fetching a single URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout
        render_js: Whether to render JavaScript (for dynamic content)
        wait_for_selector: CSS selector to wait for before returning
        
    Returns:
        HTML content or None
    """
    fetcher = get_fetcher()
    return await fetcher.fetch(url, timeout, render_js=render_js, wait_for_selector=wait_for_selector)

