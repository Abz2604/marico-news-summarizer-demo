"""
Bright Data Web Unlocker Integration
Clean, simple, professional HTTP fetching that bypasses all blocks.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


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
    
    async def fetch(self, url: str, timeout: int = 60) -> Optional[str]:
        """
        Fetch URL content using Bright Data Scraping Browser.
        
        Args:
            url: Target URL to fetch
            timeout: Request timeout in seconds
            
        Returns:
            HTML content or None if failed
        """
        logger.info(f"Fetching with BrightData: {url}")
        
        try:
            import asyncio
            
            # Use requests in thread pool for async compatibility
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(
                None, 
                self._fetch_sync, 
                url, 
                timeout
            )
            return html
                    
        except Exception as e:
            logger.error(f"❌ Fetch failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fetch_sync(self, url: str, timeout: int) -> Optional[str]:
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
            
            logger.info(f"Bright Data API request: zone={self.zone}, url={url}")
            
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


async def fetch_url(url: str, timeout: int = 30) -> Optional[str]:
    """
    Simple convenience function for fetching a single URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout
        
    Returns:
        HTML content or None
    """
    fetcher = get_fetcher()
    return await fetcher.fetch(url, timeout)

