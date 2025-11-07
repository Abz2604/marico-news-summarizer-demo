"""
Strategic Planning Module

This module implements PLANNING - the agent thinks strategically before acting.
Unlike reactive navigation, the planner creates a STRATEGY upfront.

PHILOSOPHY: "Think before you act"
- Analyze the seed URL and user intent
- Create a multi-step navigation strategy
- Set success criteria
- Anticipate failure modes
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class NavigationPlan:
    """Strategic plan for content discovery"""
    strategy: str  # High-level strategy description
    expected_page_type: str  # What we expect to find at seed URL
    navigation_steps: List[str]  # Ordered list of expected steps
    success_criteria: Dict[str, Any]  # How to know if we succeeded
    fallback_strategies: List[str]  # What to do if primary strategy fails
    estimated_depth: int  # Expected navigation depth
    confidence: float  # Confidence in this plan (0.0-1.0)
    reasoning: str  # Why this plan makes sense


async def create_navigation_plan(
    seed_url: str,
    user_intent: Dict,
    max_articles: int = 10
) -> NavigationPlan:
    """
    Create a strategic navigation plan BEFORE starting exploration.
    
    This is the PLANNING phase - think strategically about:
    1. What type of site is this?
    2. What's the best path to get what user wants?
    3. What could go wrong?
    4. How do we know if we succeeded?
    
    Args:
        seed_url: Starting URL
        user_intent: User intent dictionary from intent_extractor
        max_articles: Target number of articles
        
    Returns:
        NavigationPlan with strategic guidance
    """
    settings = get_settings()
    
    topic = user_intent.get('topic', 'general content')
    target_section = user_intent.get('target_section', '')
    time_range_days = user_intent.get('time_range_days', 7)
    output_format = user_intent.get('output_format', 'bullet_points')
    
    prompt = f"""You are a strategic planning AI helping to efficiently extract web content.

═══════════════════════════════════════════════════════════════════════════════
📋 PLANNING MISSION
═══════════════════════════════════════════════════════════════════════════════
USER WANTS: {topic}
TARGET SECTION: {target_section or '(flexible - use intelligence)'}
TIME WINDOW: Last {time_range_days} days
DESIRED OUTPUT: {output_format}
TARGET ARTICLES: {max_articles}

STARTING URL: {seed_url}

═══════════════════════════════════════════════════════════════════════════════
🎯 YOUR TASK: CREATE A STRATEGIC NAVIGATION PLAN
═══════════════════════════════════════════════════════════════════════════════

Analyze the URL and create a STRATEGIC PLAN before we start navigating.

**STEP 1: URL PATTERN ANALYSIS**
Look at the URL structure and predict:
- What type of page is this likely to be?
  Examples:
  - stockpricequote/company-name → Company profile page
  - company.com/news → News listing page
  - forum.com/topic/123 → Forum thread
  - blog.com/2024/11/article-title → Individual article
  - company.com → Homepage

**STEP 2: STRATEGIC THINKING**
Given the page type and user intent, what's the BEST navigation strategy?

Common strategies:
1. **Direct Extraction**: Seed URL is already the content → extract immediately
2. **One-Hop Navigation**: Seed is hub → click to section (News/Blog/Forum) → extract
3. **Two-Hop Deep Dive**: Seed is hub → section listing → individual items → extract
4. **Search & Filter**: Large listing → filter by date/topic → extract matches

**STEP 3: SUCCESS CRITERIA**
How will we know if we succeeded?
- Number of articles found (target: {max_articles})
- Recency (within {time_range_days} days)
- Relevance to topic
- Content quality (not paywalled, complete text)

**STEP 4: FAILURE ANTICIPATION**
What could go wrong and what's our backup plan?
- Paywall → skip and continue
- No articles in time window → expand window or try related sections
- Wrong section → navigate to correct one
- Empty listing → try seed URL itself as content

═══════════════════════════════════════════════════════════════════════════════
📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return ONLY valid JSON (no markdown):

{{
  "strategy": "One sentence describing the overall approach",
  "expected_page_type": "company_profile" | "news_listing" | "forum_thread" | "article" | "homepage" | "blog" | "other",
  "navigation_steps": [
    "Step 1: What we'll do first",
    "Step 2: What we'll do next",
    "Step 3: Final action"
  ],
  "success_criteria": {{
    "min_articles": {max(3, max_articles // 2)},
    "target_articles": {max_articles},
    "max_age_days": {time_range_days},
    "required_relevance": 0.8
  }},
  "fallback_strategies": [
    "Fallback 1 if primary fails",
    "Fallback 2 if still failing"
  ],
  "estimated_depth": 2,
  "confidence": 0.85,
  "reasoning": "2-3 sentence explanation of why this plan makes sense given the URL structure and user intent"
}}

Think strategically. Anticipate. Plan ahead."""
    
    try:
        # Use GPT-4o for strategic planning (needs intelligence)
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0
        )
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown code blocks
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
        
        plan = NavigationPlan(
            strategy=result.get('strategy', 'Explore and extract'),
            expected_page_type=result.get('expected_page_type', 'other'),
            navigation_steps=result.get('navigation_steps', []),
            success_criteria=result.get('success_criteria', {}),
            fallback_strategies=result.get('fallback_strategies', []),
            estimated_depth=result.get('estimated_depth', 2),
            confidence=result.get('confidence', 0.5),
            reasoning=result.get('reasoning', 'No reasoning provided')
        )
        
        logger.info(f"📋 PLAN CREATED:")
        logger.info(f"   Strategy: {plan.strategy}")
        logger.info(f"   Expected type: {plan.expected_page_type}")
        logger.info(f"   Estimated depth: {plan.estimated_depth}")
        logger.info(f"   Confidence: {plan.confidence:.2f}")
        logger.info(f"   Steps: {len(plan.navigation_steps)}")
        
        return plan
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse planning response: {e}")
        logger.error(f"Response: {response_text[:300]}")
        # Return safe default plan
        return _create_default_plan(seed_url, user_intent, max_articles)
    
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return _create_default_plan(seed_url, user_intent, max_articles)


def _create_default_plan(seed_url: str, user_intent: Dict, max_articles: int) -> NavigationPlan:
    """Fallback plan if AI planning fails"""
    logger.warning("⚠️ Using default navigation plan (AI planning failed)")
    
    return NavigationPlan(
        strategy="Explore seed URL and extract relevant content",
        expected_page_type="unknown",
        navigation_steps=[
            "Analyze seed page structure",
            "Navigate to content sections if needed",
            "Extract articles matching criteria"
        ],
        success_criteria={
            "min_articles": max(3, max_articles // 2),
            "target_articles": max_articles,
            "max_age_days": user_intent.get('time_range_days', 7),
            "required_relevance": 0.8
        },
        fallback_strategies=[
            "Try seed URL itself as content source",
            "Expand time window if needed"
        ],
        estimated_depth=2,
        confidence=0.5,
        reasoning="Default plan due to planning error"
    )

