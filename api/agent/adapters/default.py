from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..brightdata_fetcher import fetch_url


logger = logging.getLogger(__name__)


def _abs(base: str, href: str) -> str:
    try:
        return urljoin(base, href)
    except Exception:
        return href


def _same_host(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc == urlparse(b).netloc
    except Exception:
        return False


def _parse_date(text: str) -> Optional[datetime]:
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    t = (text or "").strip()
    if not t:
        return None
    if re.search(r"\b(today)\b", t, re.I):
        return now
    if re.search(r"\b(yesterday)\b", t, re.I):
        return now - timedelta(days=1)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", t)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2).title()} {m.group(3)}", "%d %b %Y").replace(tzinfo=ist)
        except Exception:
            return None
    rel = re.search(r"(\d+)\s+(min|hour|day)s?\s+ago", t, re.I)
    if rel:
        val = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            return now - timedelta(minutes=val)
        if unit.startswith("hour"):
            return now - timedelta(hours=val)
        if unit.startswith("day"):
            return now - timedelta(days=val)
    return None


class DefaultHeuristicAdapter:
    async def discover_listing(self, seed_url: str) -> Optional[str]:
        # Fetch HTML using Bright Data
        html = await fetch_url(seed_url, timeout=20)
        if not html:
            logger.warning(f"Could not fetch {seed_url} for listing discovery")
            return None
            
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for obvious nav links
        for a in soup.find_all("a", href=True, string=True):
            label = a.get_text(strip=True).lower()
            if any(k in label for k in ["news", "press", "blog", "updates", "announcements"]):
                href = _abs(seed_url, a["href"])
                if _same_host(seed_url, href):
                    return href
        
        # Fallback to href patterns
        for a in soup.find_all("a", href=True):
            href = _abs(seed_url, a["href"])
            if _same_host(seed_url, href) and re.search(r"/(news|press|blog|stories|updates)/", href, re.I):
                return href

        return None

    async def collect_article_links(self, listing_url: str, window_days: int = 5, limit: int = 5) -> List[str]:
        # Fetch listing page using Bright Data
        html = await fetch_url(listing_url, timeout=20)
        if not html:
            logger.warning(f"Could not fetch listing URL: {listing_url}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        ist = ZoneInfo("Asia/Kolkata")
        cutoff = datetime.now(ist) - timedelta(days=window_days)
        
        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = _abs(listing_url, a["href"])
            label = a.get_text(strip=True)
            if not label:
                continue
            if not re.search(r"/(news|press|blog|story|article)/", href, re.I):
                continue
            
            # Find nearby date
            dt = None
            parent = a.parent
            if parent:
                for sib in parent.find_all(["time", "span", "small"], string=True):
                    dt = _parse_date(sib.get_text(strip=True))
                    if dt:
                        break
            
            if dt is None or dt >= cutoff:
                links.append(href)
            if len(links) >= limit:
                break

        # Dedup while preserving order
        seen = set()
        uniq = []
        for u in links:
            if u in seen:
                continue
            seen.add(u)
            uniq.append(u)
        
        return uniq[:limit]


