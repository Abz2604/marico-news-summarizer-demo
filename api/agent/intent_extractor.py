"""
Intent Extraction from Natural Language Prompts

PHILOSOPHY: LLM-First Approach
------------------------------
This module uses LLMs directly for intent extraction rather than heuristics.

WHY LLM-DIRECT?
1. **Flexibility**: Handles any phrasing naturally ("what's been going on lately?")
2. **Maintenance**: Zero code changes for new patterns (LLM learns from context)
3. **Robustness**: Understands semantic intent, not just keyword matching
4. **Cost**: ~$0.001 per request (negligible vs. insight quality gains)

TRADE-OFF:
- Cost: +$0.001/request vs heuristics
- Speed: +200-400ms vs heuristics
- Value: Handles edge cases naturally, requires minimal maintenance

For this project: Budget is NOT a constraint, insight quality IS the KPI.
Therefore, LLM-direct is the right architectural choice.
"""

import json
import logging

from langchain_openai import ChatOpenAI
from config import get_settings

from .intent import (
    UserIntent,
    OutputFormat,
    TimeRange,
    FocusArea
)

logger = logging.getLogger(__name__)


class IntentExtractor:
    """
    Extract structured intent from user prompts using LLM.
    
    This is a pure LLM implementation - no heuristics, no fallbacks.
    The LLM handles all cases from simple to complex, colloquial to formal.
    """
    
    def __init__(self, openai_api_key: str):
        settings = get_settings()
        model_name = settings.intent_extractor_model or settings.openai_model or "gpt-4o-mini"
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=openai_api_key
        )
    
    async def extract_intent(self, prompt: str, max_articles: int = 3) -> UserIntent:
        """
        Extract structured intent from user prompt using LLM.
        
        Args:
            prompt: User's natural language request (any phrasing works!)
            max_articles: Default article count (can be overridden by prompt)
            
        Returns:
            UserIntent object with all extracted parameters
            
        Examples:
            - "Summarize Marico news" → standard 3 bullets, 7 days
            - "What's been happening with Apple lately?" → understands "lately" = recent
            - "Give me the gist, keep it short" → understands concise format
            - "Executive summary last 3 days" → understands both format and time
        """
        
        logger.info(f"🎯 Extracting intent from: '{prompt[:60]}...'")
        return await self._llm_extract(prompt, max_articles)
    
    async def _llm_extract(self, prompt: str, max_articles: int) -> UserIntent:
        """
        Use LLM to extract structured intent from natural language.
        
        This handles ALL cases - simple, complex, colloquial, formal.
        No heuristics needed!
        """
        
        llm_prompt = f"""You are an intent extraction specialist. Parse the user's request into structured parameters for an insights tool.

USER REQUEST: "{prompt}"

Extract these parameters (keep the exact keys and types):

1. TIME RANGE: How far back should we search?
   Options: today | yesterday | last_3_days | last_5_days | last_7_days | last_14_days | last_30_days | last_60_days | last_90_days | this_week | this_month | any
   
   Phrase mapping examples:
   - "lately", "recent", "recently" → last_5_days
   - "today", "today's" → today
   - "this week", "past week" → this_week
   - "this month", "current month" → this_month
   - "last month", "past month", "past 30 days" → last_30_days
   - "last 2 months" → last_60_days; "last 3 months"/"quarter" → last_90_days
   - "last X days" → map to appropriate enum
   - No mention → last_7_days (default)

2. OUTPUT FORMAT: How should the summary be formatted?
   Options:
   - executive_summary: 3-5 sentence overview only, no bullets
   - bullet_points: Categorized bullet list (default)
   - detailed: 5+ points per article, with context
   - one_per_article: Single bullet per article
   - concise: 1–2 high-level points per article

   Phrase mapping examples:
   - "executive summary", "high level", "overview", "gist" → executive_summary
   - "brief", "short", "quick" → concise
   - "detailed", "comprehensive", "in-depth" → detailed
   - "one per article", "single bullet" → one_per_article
   - No mention → bullet_points (default)

3. BULLETS PER ARTICLE: If bullet format, how many bullets per article? (integer 0–10)
   Default: 3

4. INCLUDE EXECUTIVE SUMMARY: Include an executive summary at the end? (boolean)
   Default: true (unless format is already executive_summary)

5. MAX ARTICLES: How many articles to analyze? (integer 1–20)
   Look for: "X articles", "top X", "X stories"
   Default: {max_articles}

6. FOCUS AREAS: What aspects should we focus on? (list)
   Options: financial_performance, market_activity, corporate_actions, products_innovation, leadership_changes, regulatory_legal
   Empty list = all topics (most common)
   
   Keywords to map:
   - "earnings", "revenue", "profit", "financial" → financial_performance
   - "stock", "market", "trading", "share price" → market_activity
   - "merger", "acquisition", "M&A", "dividend" → corporate_actions
   - "product", "launch", "innovation" → products_innovation
   - "CEO", "leadership", "executive" → leadership_changes
   - "regulation", "lawsuit", "legal" → regulatory_legal

7. PAGE SECTION: What section of the page should we focus on? (string)
   Options: news_listing, company_profile, article, category_page, search_results, other
   Empty string = all sections
   Keywords to map:
   - "news", "articles", "updates" → news_listing
   - "company", "profile", "about" → company_profile
   - "article", "blog", "post" → article
   - "category", "tag", "section" → category_page
   - "search", "results" → search_results
   - "forum", "discussion" → forum_page

IMPORTANT: Do NOT assume the subject is a specific company. The user may ask about an industry, sector, market theme, geography, or cross-company topic. Reflect the subject in the free-text "topic" used downstream (outside this JSON); keep keys here unchanged.

EXAMPLES (keys unchanged):
- "Summarize last 3 days of Apple news" → {{"time_range": "last_3_days", "output_format": "bullet_points", "bullets_per_article": 3}}
- "EV sector funding trends, last month" → {{"time_range": "last_30_days", "output_format": "bullet_points"}}
- "Indian FMCG industry updates this week" → {{"time_range": "this_week", "output_format": "bullet_points"}}
- "Macro tailwinds in US semiconductors, one bullet per article" → {{"output_format": "one_per_article", "bullets_per_article": 1}}

Respond with ONLY valid JSON (no markdown, no trailing comments, double quotes only):
{{
  "time_range": "last_7_days",
  "time_range_days": 7,
  "output_format": "bullet_points",
  "bullets_per_article": 3,
  "include_executive_summary": true,
  "max_articles": {max_articles},
  "focus_areas": [],
  "page_section": "",
  "confidence": 0.95,
  "reasoning": "Brief explanation of what you understood"
}}
"""
        
        try:
            response = await self.llm.ainvoke(llm_prompt)
            response_text = response.content.strip()
            
            # Handle markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block or (not line.startswith("```")):
                        json_lines.append(line)
                response_text = "\n".join(json_lines)
            
            result = json.loads(response_text)
            
            # Map focus areas
            focus_areas_str = result.get("focus_areas", [])
            focus_areas = [FocusArea(f) for f in focus_areas_str] if focus_areas_str else None
            
            extracted_max = result.get("max_articles", max_articles)

            # Normalize time_range_days to match time_range to avoid LLM drift
            tr = str(result.get("time_range", "last_7_days"))
            normalized_days_map = {
                "today": 0,
                "yesterday": 1,
                "last_3_days": 3,
                "last_5_days": 5,
                "last_7_days": 7,
                "last_14_days": 14,
                "last_30_days": 30,
                "last_60_days": 60,
                "last_90_days": 90,
                "this_week": 7,
                "this_month": 30,
            }
            normalized_days = normalized_days_map.get(tr, result.get("time_range_days", 7))
            
            # Smart article limit logic:
            # If user specified ONLY time range (no explicit article count), set high limit
            # to let date filtering be the primary gatekeeper
            prompt_lower = prompt.lower()
            has_time_keywords = any(kw in prompt_lower for kw in [
                'last', 'days', 'week', 'month', 'today', 'yesterday', 'recent'
            ])
            has_article_count = any(kw in prompt_lower for kw in [
                'article', 'top', '5', '10', '20'
            ])
            
            # If time-focused query without explicit count, boost limit moderately
            # We now have smart date pre-filtering, so we don't need as high a limit
            if has_time_keywords and not has_article_count and extracted_max == max_articles:
                extracted_max = 12  # Moderate boost - we pre-filter by date now
                logger.info(f"📊 Time-focused query detected, boosting max_articles to {extracted_max}")
            
            intent = UserIntent(
                raw_prompt=prompt,
                topic=prompt.strip(),
                time_range=TimeRange(result.get("time_range", "last_7_days")),
                time_range_days=normalized_days,
                output_format=OutputFormat(result.get("output_format", "bullet_points")),
                bullets_per_article=result.get("bullets_per_article", 3),
                include_executive_summary=result.get("include_executive_summary", True),
                max_articles=extracted_max,
                focus_areas=focus_areas,
                confidence=result.get("confidence", 0.95),
                ambiguities=[result.get("reasoning")] if result.get("reasoning") else None
            )
            
            logger.info(f"✅ Intent extracted (confidence: {intent.confidence:.2f}, max_articles: {intent.max_articles})")
            return intent
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ LLM returned invalid JSON: {e}")
            logger.error(f"Response: {response_text[:200]}")
            # Return safe defaults
            return self._safe_default_intent(prompt, max_articles)
            
        except Exception as e:
            logger.error(f"❌ LLM intent extraction failed: {e}")
            # Return safe defaults
            return self._safe_default_intent(prompt, max_articles)
    
    def _safe_default_intent(self, prompt: str, max_articles: int) -> UserIntent:
        """
        Fallback to safe defaults if LLM fails.
        This should rarely happen (LLM is highly reliable).
        """
        logger.warning("⚠️ Using safe default intent (LLM extraction failed)")
        return UserIntent(
            raw_prompt=prompt,
            topic=prompt.strip(),
            time_range=TimeRange.LAST_7_DAYS,
            time_range_days=7,
            output_format=OutputFormat.BULLET_POINTS,
            bullets_per_article=3,
            include_executive_summary=True,
            max_articles=max_articles,
            focus_areas=None,
            confidence=0.5,  # Low confidence since we're using defaults
            ambiguities=["LLM extraction failed, using safe defaults"]
        )


async def extract_intent(prompt: str, max_articles: int = 10) -> UserIntent:
    """
    Convenience function for extracting intent.
    
    Args:
        prompt: User's natural language request
        max_articles: Default article count
        
    Returns:
        UserIntent object
    """
    settings = get_settings()
    extractor = IntentExtractor(settings.openai_api_key)
    return await extractor.extract_intent(prompt, max_articles)

