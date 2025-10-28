from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse, quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .search import bing_search_urls
from .adapters.registry import get_adapter_for
from .brightdata_fetcher import fetch_url


logger = logging.getLogger(__name__)


def _absolute(base_url: str, href: str) -> str:
    try:
        return urljoin(base_url, href)
    except Exception:
        return href


def _same_domain(url_a: str, url_b: str) -> bool:
    try:
        return urlparse(url_a).netloc == urlparse(url_b).netloc
    except Exception:
        return False


def _parse_possible_date(text: str) -> Optional[datetime]:
    text = text.strip()
    if not text:
        return None
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    # Relative patterns
    if re.search(r"\b(today)\b", text, re.I):
        return now
    if re.search(r"\b(yesterday)\b", text, re.I):
        return now - timedelta(days=1)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text)
    if m:
        day = int(m.group(1))
        mon_str = m.group(2).title()
        year = int(m.group(3))
        try:
            dt = datetime.strptime(f"{day} {mon_str} {year}", "%d %b %Y").replace(tzinfo=ist)
            return dt
        except Exception:
            return None
    # Minutes/hours ago
    rel = re.search(r"(\d+)\s+(min|hour|day)s?\s+ago", text, re.I)
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


def _moneycontrol_listing_from_seed(seed_url: str) -> Optional[str]:
    """Construct Moneycontrol tags URL from a stock page seed (tags page works better!).

    Example seed:
      https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13
    Tags page:
      https://www.moneycontrol.com/news/tags/marico.html
    """

    try:
        parsed = urlparse(seed_url)
        if "moneycontrol.com" not in parsed.netloc:
            return None
        
        # Extract company name from various URL patterns
        parts = [p for p in parsed.path.split("/") if p]
        
        # Pattern 1: /india/stockpricequote/category/COMPANY/code
        if len(parts) >= 5 and parts[0] == "india" and parts[1] == "stockpricequote":
            company_name = parts[3].lower()
            return f"https://www.moneycontrol.com/news/tags/{company_name}.html"
        
        # Pattern 2: /company-article/COMPANY/news/code
        if len(parts) >= 3 and parts[0] == "company-article":
            company_name = parts[1].lower()
            return f"https://www.moneycontrol.com/news/tags/{company_name}.html"
        
    except Exception:
        return None
    return None


async def discover_news_listing_url(seed_url: str) -> Optional[str]:
    """Find a news/blog listing URL from a seed page using adapter then heuristics."""

    # Try MoneyControl direct listing construction FIRST (site-specific is more reliable)
    direct = _moneycontrol_listing_from_seed(seed_url)
    if direct:
        logger.info(f"Using MoneyControl-specific listing URL: {direct}")
        return direct

    # Adapter-based discovery
    adapter = get_adapter_for(seed_url)
    listing = await adapter.discover_listing(seed_url)
    if listing:
        return listing

    # Fetch HTML using Bright Data
    html = await fetch_url(seed_url, timeout=20)
    if not html:
        logger.warning(f"Could not fetch {seed_url} for listing discovery")
        return None

    soup = BeautifulSoup(html, "html.parser")

    # 1) Find section headings containing 'news' and look for anchor inside/nearby
    for header_tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"], string=True):
        if "news" in header_tag.get_text(strip=True).lower():
            # search within the same parent for anchors
            parent = header_tag.parent
            if parent:
                a = parent.find("a", string=re.compile(r"see\s*more|view\s*all", re.I))
                if a and a.get("href"):
                    return _absolute(seed_url, a["href"])
            # siblings anchors
            sib_a = header_tag.find_next("a", string=re.compile(r"see\s*more|view\s*all", re.I))
            if sib_a and sib_a.get("href"):
                return _absolute(seed_url, sib_a["href"])

    # 2) Fallback: any anchor whose text contains 'news'
    for a in soup.find_all("a", string=True):
        if "news" in a.get_text(strip=True).lower() and a.get("href"):
            href = _absolute(seed_url, a["href"])
            if _same_domain(seed_url, href):
                return href

    # 3) Last resort: anchors with '/news' in href
    for a in soup.find_all("a", href=True):
        href_val = a["href"]
        if "/news" in href_val:
            href = _absolute(seed_url, href_val)
            if _same_domain(seed_url, href):
                return href

    return None


async def collect_recent_article_links(listing_url: str, window_days: int = 5, limit: int = 5) -> List[str]:
    """Collect recent article links using adapter then heuristics as fallback."""

    # Skip adapter for MoneyControl tags pages (heuristic works better)
    is_moneycontrol_tags = "moneycontrol.com/news/tags/" in listing_url
    
    if not is_moneycontrol_tags:
        adapter = get_adapter_for(listing_url)
        links = await adapter.collect_article_links(listing_url, window_days=window_days, limit=limit)
        if links:
            return links

    # Fetch listing page HTML using Bright Data
    logger.info(f"Fetching listing page: {listing_url}")
    html = await fetch_url(listing_url, timeout=20)
    
    if not html:
        logger.error(f"Failed to fetch listing URL: {listing_url}")
        return []

    # Parse HTML and extract article links
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    cutoff = now - timedelta(days=window_days)

    candidates: List[Tuple[str, Optional[datetime]]] = []
    for a in soup.find_all("a", href=True):
        href = _absolute(listing_url, a["href"])
        text = a.get_text(strip=True)
        if not href or not text:
            continue
        # Exclude the listing URL itself
        if href.rstrip("/") == listing_url.rstrip("/"):
            continue
        # Heuristic filters for likely news articles
        if any(s in href.lower() for s in ["/news", "/newsroom", "/news-", "/news/", "/article", "/story"]):
            # Exclude MoneyControl listing pattern without deeper path
            try:
                parsed = urlparse(href)
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) >= 3 and parts[0] == "company-article" and parts[2] == "news" and len(parts) == 3:
                    continue
                # Skip tag pages
                if "/tags/" in href and href.endswith(".html"):
                    continue
            except Exception:
                pass
            
            # Require minimum text length (real article link)
            if len(text) < 20:
                continue
            
            # Look for nearby date text
            date_text = None
            parent = a.parent
            if parent:
                # search small/span/time within parent or next elements
                for sib in parent.find_all(["span", "time", "small"], string=True):
                    date_text = sib.get_text(strip=True)
                    break
            parsed_dt = _parse_possible_date(date_text or "") if date_text else None
            candidates.append((href, parsed_dt))

    logger.info(f"Found {len(candidates)} candidate article links")

    # Deduplicate while preserving order
    seen = set()
    unique: List[Tuple[str, Optional[datetime]]] = []
    for href, dt in candidates:
        if href in seen:
            continue
        seen.add(href)
        unique.append((href, dt))

    # Filter by cutoff when we have dates; otherwise keep as unknown
    filtered: List[str] = []
    for href, dt in unique:
        if dt is None or dt >= cutoff:
            filtered.append(href)
        if len(filtered) >= limit:
            break

    logger.info(f"Returning {len(filtered)} filtered article links")
    return filtered


