from __future__ import annotations

from urllib.parse import urlparse

from .base import ListingAdapter
from .default import DefaultHeuristicAdapter


def get_adapter_for(url: str) -> ListingAdapter:
    # For now return default heuristic adapter for all domains
    # Later: map specific domains to custom adapters
    return DefaultHeuristicAdapter()


