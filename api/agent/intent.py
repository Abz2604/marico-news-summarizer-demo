"""
Intent Extraction Data Models
Structured representation of user's request
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum


class OutputFormat(str, Enum):
    """Desired output format from user"""
    EXECUTIVE_SUMMARY = "executive_summary"  # 2-3 sentence overview only
    BULLET_POINTS = "bullet_points"  # Standard categorized bullets (default)
    DETAILED = "detailed"  # Comprehensive analysis with more points
    ONE_PER_ARTICLE = "one_per_article"  # Single bullet per article
    CONCISE = "concise"  # Brief, high-level only


class TimeRange(str, Enum):
    """Time-based filter specifications"""
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_3_DAYS = "last_3_days"
    LAST_5_DAYS = "last_5_days"
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    LAST_60_DAYS = "last_60_days"
    LAST_90_DAYS = "last_90_days"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    ANY = "any"  # No time restriction


class FocusArea(str, Enum):
    """Content focus areas"""
    FINANCIAL = "financial_performance"
    MARKET = "market_activity"
    CORPORATE_ACTIONS = "corporate_actions"
    PRODUCTS = "products_innovation"
    LEADERSHIP = "leadership_changes"
    REGULATORY = "regulatory_legal"
    ALL = "all_topics"


@dataclass
class UserIntent:
    """
    Structured representation of user's request.
    
    Extracted from natural language prompts like:
    - "Summarize last 5 days of Marico news"
    - "Executive summary of Apple earnings"
    - "One bullet per article about Tesla"
    """
    
    # Original request
    raw_prompt: str
    
    # Core intent
    topic: str  # What they're researching
    
    # Time constraints
    time_range: TimeRange = TimeRange.LAST_7_DAYS
    time_range_days: int = 7  # Numeric representation for calculations
    
    # Output preferences
    output_format: OutputFormat = OutputFormat.BULLET_POINTS
    bullets_per_article: int = 3  # Default: 3 bullets per article
    include_executive_summary: bool = True  # Add exec summary at end
    
    # Content filters
    max_articles: int = 3  # How many articles to analyze
    focus_areas: Optional[List[FocusArea]] = None  # None = all topics
    target_section: str = ""  # Which page section to focus on (forum_page, news_listing, etc.)
    
    # Quality preferences
    min_article_length: int = 150  # Minimum words
    exclude_paywalls: bool = True
    
    # Metadata
    confidence: float = 1.0  # How confident we are in extraction (0-1)
    ambiguities: Optional[List[str]] = None  # Things we couldn't parse clearly
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging"""
        return {
            "topic": self.topic,
            "time_range": self.time_range.value,
            "time_range_days": self.time_range_days,
            "output_format": self.output_format.value,
            "bullets_per_article": self.bullets_per_article,
            "include_executive_summary": self.include_executive_summary,
            "max_articles": self.max_articles,
            "focus_areas": [f.value for f in (self.focus_areas or [])],
            "target_section": self.target_section,
            "confidence": self.confidence,
            "ambiguities": self.ambiguities or []
        }
    
    def get_cutoff_date(self) -> Optional[datetime]:
        """
        Calculate the earliest acceptable article date based on time_range.
        
        Returns:
            datetime object for the cutoff, or None if no time restriction
        """
        now = datetime.now()
        
        if self.time_range == TimeRange.TODAY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        elif self.time_range == TimeRange.YESTERDAY:
            yesterday = now - timedelta(days=1)
            return yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        
        elif self.time_range == TimeRange.THIS_WEEK:
            # Start of week (Monday)
            days_since_monday = now.weekday()
            week_start = now - timedelta(days=days_since_monday)
            return week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        elif self.time_range == TimeRange.THIS_MONTH:
            # Start of month
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        elif self.time_range == TimeRange.ANY:
            return None
        
        else:
            # For LAST_X_DAYS, use time_range_days
            return now - timedelta(days=self.time_range_days)
    
    def get_summarization_prompt_guidance(self) -> str:
        """
        Generate guidance text for the summarization LLM based on intent.
        
        Returns:
            String with instructions for the LLM
        """
        
        if self.output_format == OutputFormat.EXECUTIVE_SUMMARY:
            return """Create a 3-5 sentence executive summary that synthesizes key themes across all articles.
Focus on high-level insights suitable for C-suite executives.
Do NOT create bullet points - only narrative summary."""
        
        elif self.output_format == OutputFormat.ONE_PER_ARTICLE:
            return f"""Create EXACTLY 1 concise bullet point per article.
Total bullets: {self.max_articles}
Each bullet must capture the CORE insight in one sentence.
{'Include a 2-3 sentence executive summary at the end.' if self.include_executive_summary else 'No executive summary needed.'}"""
        
        elif self.output_format == OutputFormat.DETAILED:
            return f"""Create a comprehensive analysis with 5+ key points from EACH article.
Include detailed context, numbers, quotes, and analysis.
Organize by category.
{'Include a 3-4 sentence executive summary at the end.' if self.include_executive_summary else 'No executive summary needed.'}"""
        
        elif self.output_format == OutputFormat.CONCISE:
            return f"""Create brief, high-level summaries with 1-2 key points per article.
Focus on essential information only.
{'Include a 2 sentence executive summary at the end.' if self.include_executive_summary else 'No executive summary needed.'}"""
        
        else:  # BULLET_POINTS (default)
            return f"""Extract {self.bullets_per_article} key points from EACH article (not {self.bullets_per_article} total).
Organize points by category (Financial Performance, Market Activity, etc.).
{'Include a 2-3 sentence executive summary at the end.' if self.include_executive_summary else 'No executive summary needed.'}"""
    
    def get_focus_area_filter(self) -> Optional[str]:
        """
        Generate focus area instruction for LLM.
        
        Returns:
            String with focus area instructions, or None if no filter
        """
        if not self.focus_areas or FocusArea.ALL in self.focus_areas:
            return None
        
        focus_list = [f.value.replace("_", " ").title() for f in self.focus_areas]
        return f"FOCUS ONLY ON: {', '.join(focus_list)}"

