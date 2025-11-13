"""
Tools - Specialized functions for AgentV2
"""

from .web_fetcher import fetch_page
from .link_extractor import extract_links
from .content_extractor import extract_content

__all__ = [
    "fetch_page",
    "extract_links",
    "extract_content",
]

