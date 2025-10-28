from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class SeedLink:
    url: str
    depth_limit: int = 0


@dataclass
class ArticleContent:
    url: str
    resolved_url: str
    title: Optional[str]
    text: str
    fetched_at: datetime
    metadata: Optional[dict] = None


@dataclass
class SummaryResult:
    summary_markdown: str
    bullet_points: List[str]
    citations: List[dict]
    model: str
    token_usage: Optional[dict] = None
