"""
Type definitions for AgentV2
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, TypedDict
from datetime import datetime


class PageType(str, Enum):
    """Supported page types"""
    BLOG_LISTING = "blog_listing"
    FORUM_THREAD = "forum_thread"
    # Future types:
    # PRESS_RELEASES = "press_releases"
    # PRODUCT_PAGES = "product_pages"
    # RESEARCH_REPORTS = "research_reports"


@dataclass
class ExtractedLink:
    """A link extracted from a page"""
    url: str
    title: str
    snippet: Optional[str] = None
    detected_date: Optional[datetime] = None
    relevance_score: float = 0.0  # 0.0 to 1.0


@dataclass
class ExtractedContent:
    """Content extracted from a page"""
    url: str
    title: str
    content: str
    publish_date: Optional[datetime] = None
    content_type: str = "article"  # article, forum_thread, etc.
    summary: Optional[str] = None  # Per-article summary
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AgentV2Request:
    """Request for AgentV2"""
    url: str
    prompt: str
    page_type: PageType
    max_items: int = 10
    time_range_days: Optional[int] = None  # None = no time filter


@dataclass
class AgentV2Response:
    """Response from AgentV2"""
    items: List[ExtractedContent]
    summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentState(TypedDict):
    """State schema for LangGraph agent"""
    # Goal definition
    goal: Dict[str, Any]  # target_items, topic, time_range_days, quality_threshold
    
    # Input
    seed_url: str
    prompt: str
    page_type: str
    
    # Extracted data
    extracted_items: List[Dict[str, Any]]  # List of ExtractedContent as dicts
    links_found: List[Dict[str, Any]]  # List of ExtractedLink as dicts
    listing_html: Optional[str]
    
    # Progress tracking
    current_link_index: int
    iteration: int
    quality_score: float
    
    # Error handling
    error: Optional[str]
    should_abort: bool
    consecutive_failures: int
    no_progress_iterations: int
    
    # History
    history: List[Dict[str, Any]]  # Action history for debugging

