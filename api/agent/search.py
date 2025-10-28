from __future__ import annotations

import logging
from typing import List

import httpx

from config import get_settings


logger = logging.getLogger(__name__)


async def bing_search_urls(query: str, site_filter: str | None = None, count: int = 10) -> List[str]:
    settings = get_settings()
    if not settings.bing_search_api_key:
        return []

    headers = {"Ocp-Apim-Subscription-Key": settings.bing_search_api_key}
    params = {"q": f"site:{site_filter} {query}" if site_filter else query, "count": count}

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(settings.bing_search_endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
            web_pages = (data or {}).get("webPages", {}).get("value", [])
            urls = []
            for item in web_pages:
                url = item.get("url")
                if not url:
                    continue
                urls.append(url)
            return urls
    except Exception as exc:  # noqa: BLE001
        logger.warning("bing search failed: %s", exc)
        return []


