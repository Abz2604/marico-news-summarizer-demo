"""
Article Deduplication
LLM-First approach for semantic deduplication
"""

import json
import hashlib
import logging
from typing import List
from urllib.parse import urlparse

from config import get_settings
from .llm_factory import get_fast_llm

from .types import ArticleContent

logger = logging.getLogger(__name__)


class Deduplicator:
    """Deduplicate articles using semantic similarity (LLM-based)"""
    
    def __init__(self, openai_api_key: str = None):
        """Initialize with Azure OpenAI LLM (openai_api_key param ignored, kept for compatibility)."""
        settings = get_settings()
        self.enable_semantic = settings.enable_semantic_dedup
        self.min_articles = max(1, settings.dedup_min_articles)
        self.llm = get_fast_llm(temperature=0)  # Fast model for deduplication
    
    async def deduplicate(self, articles: List[ArticleContent]) -> List[ArticleContent]:
        """
        Remove duplicate articles based on semantic similarity.
        
        Returns:
            Deduplicated list of articles
        """
        
        if len(articles) <= 1:
            return articles
        
        # Step 1: Exact deduplication (fast)
        articles = self._exact_dedup(articles)
        
        if len(articles) <= 1:
            return articles
        
        # Step 2: Semantic deduplication (LLM-based) — gated by config and size
        if not self.enable_semantic or len(articles) < self.min_articles:
            logger.info(
                f"🔍 Skipping semantic dedup (enabled={self.enable_semantic}, articles={len(articles)}, min={self.min_articles})"
            )
            return articles
        articles = await self._semantic_dedup(articles)
        
        logger.info(f"✅ Deduplication complete: {len(articles)} unique articles")
        return articles
    
    def _exact_dedup(self, articles: List[ArticleContent]) -> List[ArticleContent]:
        """Fast exact deduplication using content hashes and URLs"""
        
        seen_hashes = set()
        seen_urls = set()
        unique_articles = []
        
        for article in articles:
            # Normalize URL
            normalized_url = self._normalize_url(article.url)
            
            # Content hash (first 1000 chars)
            content_sample = article.text[:1000].strip().lower()
            content_hash = hashlib.md5(content_sample.encode()).hexdigest()
            
            # Check if seen
            if normalized_url in seen_urls or content_hash in seen_hashes:
                logger.debug(f"⚠️ Exact duplicate skipped: {article.url[:60]}")
                continue
            
            seen_urls.add(normalized_url)
            seen_hashes.add(content_hash)
            unique_articles.append(article)
        
        removed = len(articles) - len(unique_articles)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} exact duplicates")
        
        return unique_articles
    
    async def _semantic_dedup(self, articles: List[ArticleContent]) -> List[ArticleContent]:
        """
        Semantic deduplication using LLM.
        Removes articles about the same event/story.
        """
        
        if len(articles) <= 1:
            return articles
        
        unique_articles = [articles[0]]  # Keep first article
        
        # Compare each new article against unique set
        for candidate in articles[1:]:
            is_duplicate = False
            
            # Compare against each unique article
            for existing in unique_articles:
                is_dup = await self._are_semantically_similar(candidate, existing)
                if is_dup:
                    logger.info(f"🗑️ Semantic duplicate: {candidate.url[:60]}")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_articles.append(candidate)
        
        removed = len(articles) - len(unique_articles)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} semantic duplicates")
        
        return unique_articles
    
    async def _are_semantically_similar(self, article1: ArticleContent, article2: ArticleContent) -> bool:
        """
        Check if two articles are about the same event/story using LLM.
        """
        
        # Sample content (first 800 chars each)
        sample1 = f"Title: {article1.title}\nContent: {article1.text[:800]}"
        sample2 = f"Title: {article2.title}\nContent: {article2.text[:800]}"
        
        llm_prompt = f"""Determine if these two articles are about the SAME event/story or DIFFERENT events.

ARTICLE 1:
{sample1}

ARTICLE 2:
{sample2}

Consider them the SAME if:
- Same company announcement (e.g., both about "Tesla Q3 earnings")
- Same event (e.g., both about "Apple launches iPhone 16")
- Same news story from different sources

Consider them DIFFERENT if:
- Different events (e.g., "Tesla earnings" vs "Tesla recall")
- Different time periods (e.g., "Q2 results" vs "Q3 results")
- Different aspects of company (e.g., "product launch" vs "stock price")

Respond with ONLY valid JSON:
{{
  "are_same_story": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}
"""
        
        try:
            response = await self.llm.ainvoke(llm_prompt)
            response_text = response.content.strip()
            
            # Parse JSON
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(json_lines)
            
            result = json.loads(response_text)
            
            are_same = result.get("are_same_story", False)
            confidence = result.get("confidence", 0.5)
            
            # Only consider duplicate if high confidence
            return are_same and confidence > 0.7
            
        except Exception as e:
            logger.error(f"❌ Semantic similarity check failed: {e}")
            # Conservative: assume different if unsure
            return False
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison"""
        try:
            parsed = urlparse(url.lower())
            # Remove query params and fragments
            normalized = f"{parsed.netloc}{parsed.path}".rstrip('/')
            return normalized
        except Exception:
            return url.lower()


async def deduplicate_articles(articles: List[ArticleContent]) -> List[ArticleContent]:
    """
    Convenience function to deduplicate articles.
    
    Returns:
        Deduplicated list of articles
    """
    if not articles:
        return articles
    
    settings = get_settings()
    dedup = Deduplicator(settings.openai_api_key)
    return await dedup.deduplicate(articles)

