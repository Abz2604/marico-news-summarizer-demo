from __future__ import annotations

from typing import List, Optional, Protocol


class ListingAdapter(Protocol):
    async def discover_listing(self, seed_url: str) -> Optional[str]:
        """Given an arbitrary seed URL, try to find a news/blog listing URL within the same site.

        Returns a fully qualified listing URL or None.
        """

    async def collect_article_links(self, listing_url: str, window_days: int = 5, limit: int = 5) -> List[str]:
        """Given a listing URL, collect recent article links within a time window.

        Returns a list of absolute URLs (deduped, ordered).
        """


