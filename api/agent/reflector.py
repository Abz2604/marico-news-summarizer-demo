"""
Reflection Layer - Agent Self-Evaluation

PHILOSOPHY: "Did I actually accomplish what the user wanted?"

The agent evaluates its own results:
- Did we find enough content?
- Is it relevant to user intent?
- Is it recent enough?
- Did we meet success criteria?

If reflection shows gaps, agent can decide to:
- Continue searching
- Try different strategy
- Expand criteria
- Return what we have

This is METACOGNITION - thinking about thinking.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from config import get_settings
from .types import ArticleContent

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    """Result of agent's self-evaluation"""
    success: bool  # Did we accomplish the goal?
    quality_score: float  # 0.0-1.0, how well did we do?
    gaps: List[str]  # What's missing or could be better?
    strengths: List[str]  # What went well?
    recommendations: List[str]  # What should we do next?
    reasoning: str  # Explanation of evaluation
    should_continue: bool  # Should agent keep searching?


async def reflect_on_results(
    articles: List[ArticleContent],
    intent: Dict,
    plan: Optional[Dict] = None,
    max_articles: int = 10
) -> ReflectionResult:
    """
    Agent reflects on collected results and evaluates success.
    
    This is the REFLECTION phase - metacognition about our own performance:
    1. Did we get what user wanted?
    2. Is the quality good enough?
    3. What are the gaps?
    4. Should we continue or are we done?
    
    Args:
        articles: Collected articles
        intent: User intent dictionary
        plan: Original navigation plan (if available)
        max_articles: Target article count
        
    Returns:
        ReflectionResult with self-evaluation
    """
    settings = get_settings()
    
    topic = intent.get('topic', '')
    time_range_days = intent.get('time_range_days', 7)
    output_format = intent.get('output_format', 'bullet_points')
    target_section = intent.get('target_section', '')
    
    # Build article summary for reflection
    article_summaries = []
    for i, article in enumerate(articles[:20], 1):  # Max 20 for prompt
        age = article.age_days if article.age_days is not None else "unknown"
        article_summaries.append(
            f"[{i}] {article.title[:100] if article.title else 'No title'} "
            f"(Age: {age} days, Length: {len(article.text)} chars)"
        )
    
    article_list = '\n'.join(article_summaries) if article_summaries else "(No articles collected)"
    
    # Build plan summary if available
    plan_summary = ""
    if plan:
        plan_summary = f"""
ORIGINAL PLAN:
- Strategy: {plan.get('strategy', 'N/A')}
- Target articles: {plan.get('success_criteria', {}).get('target_articles', max_articles)}
- Expected depth: {plan.get('estimated_depth', 'N/A')}
"""
    
    prompt = f"""You are a self-reflective AI evaluating your own performance.

═══════════════════════════════════════════════════════════════════════════════
📋 MISSION RETROSPECTIVE
═══════════════════════════════════════════════════════════════════════════════
USER WANTED: {topic}
TARGET SECTION: {target_section or '(flexible)'}
TIME WINDOW: Last {time_range_days} days
OUTPUT FORMAT: {output_format}
TARGET ARTICLE COUNT: {max_articles}
{plan_summary}

═══════════════════════════════════════════════════════════════════════════════
📊 WHAT WE COLLECTED
═══════════════════════════════════════════════════════════════════════════════
Total articles: {len(articles)}

{article_list}

═══════════════════════════════════════════════════════════════════════════════
🤔 SELF-REFLECTION QUESTIONS
═══════════════════════════════════════════════════════════════════════════════

1. **QUANTITY CHECK**
   - Did we collect enough articles? (target: {max_articles})
   - Is this sufficient to create a good summary?

2. **QUALITY CHECK**
   - Are articles relevant to user's topic?
   - Are they recent enough? (within {time_range_days} days)
   - Do article lengths suggest substantial content?

3. **COVERAGE CHECK**
   - Do we have diverse perspectives?
   - Are there obvious gaps in coverage?
   - Did we miss important aspects?

4. **SUCCESS EVALUATION**
   - Can we create a {output_format} summary from this?
   - Will user be satisfied with these results?
   - Did we meet the success criteria?

5. **NEXT STEPS**
   - Should we continue searching? Or are we done?
   - If continuing, what strategy should we use?

═══════════════════════════════════════════════════════════════════════════════
📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return ONLY valid JSON (no markdown):

{{
  "success": true/false,
  "quality_score": 0.85,
  "gaps": [
    "Identified gap 1",
    "Identified gap 2"
  ],
  "strengths": [
    "What went well 1",
    "What went well 2"
  ],
  "recommendations": [
    "Recommendation if we were to continue",
    "Alternative approach to try"
  ],
  "reasoning": "2-3 sentence honest self-assessment of performance",
  "should_continue": false
}}

**DECISION CRITERIA:**
- success=true if: Found {max(3, max_articles // 2)}+ relevant, recent articles
- should_continue=true if: Found <{max(3, max_articles // 2)} articles AND believe more exist
- quality_score: 0.0-1.0 based on relevance, recency, quantity, diversity

Be honest. Be critical. Be metacognitive."""
    
    try:
        # Use GPT-4o for deep reflection (needs intelligence)
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0
        )
        
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown code blocks
        import json
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
        
        reflection = ReflectionResult(
            success=result.get('success', False),
            quality_score=result.get('quality_score', 0.5),
            gaps=result.get('gaps', []),
            strengths=result.get('strengths', []),
            recommendations=result.get('recommendations', []),
            reasoning=result.get('reasoning', 'No reasoning provided'),
            should_continue=result.get('should_continue', False)
        )
        
        logger.info(f"🤔 REFLECTION COMPLETE:")
        logger.info(f"   Success: {reflection.success}")
        logger.info(f"   Quality Score: {reflection.quality_score:.2f}")
        logger.info(f"   Should Continue: {reflection.should_continue}")
        logger.info(f"   Gaps: {len(reflection.gaps)}")
        logger.info(f"   Reasoning: {reflection.reasoning}")
        
        return reflection
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse reflection response: {e}")
        logger.error(f"Response: {response_text[:300]}")
        # Return safe default
        return _create_default_reflection(articles, max_articles)
    
    except Exception as e:
        logger.error(f"Reflection failed: {e}")
        return _create_default_reflection(articles, max_articles)


def _create_default_reflection(articles: List[ArticleContent], max_articles: int) -> ReflectionResult:
    """Fallback reflection if AI reflection fails"""
    logger.warning("⚠️ Using default reflection (AI reflection failed)")
    
    # Simple heuristic evaluation
    min_acceptable = max(3, max_articles // 2)
    success = len(articles) >= min_acceptable
    quality_score = min(1.0, len(articles) / max_articles)
    
    return ReflectionResult(
        success=success,
        quality_score=quality_score,
        gaps=["Unable to perform deep reflection"] if not success else [],
        strengths=["Collected some articles"] if len(articles) > 0 else [],
        recommendations=["Continue searching"] if len(articles) < min_acceptable else [],
        reasoning="Default heuristic evaluation due to reflection error",
        should_continue=len(articles) < min_acceptable
    )

