from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
try:
    from readability import Document  # type: ignore
except Exception:  # noqa: BLE001
    Document = None  # type: ignore

logger = logging.getLogger(__name__)


def extract_main_text(html: str) -> str:
    """Extract primary article text.

    Prefer readability-lxml when available; fallback to simple BeautifulSoup text extraction.
    """

    if Document is not None:
        try:
            doc = Document(html)
            summary_html = doc.summary(html_partial=True)
            soup = BeautifulSoup(summary_html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = " ".join(soup.stripped_strings)
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("readability extraction failed: %s", exc)

    # Fallback
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return text


def extract_title(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception:
        return None
    return None
