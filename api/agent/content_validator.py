"""
Content Quality Validation
LLM-First approach for detecting paywalls and quality issues
"""

import json
import logging
from dataclasses import dataclass
from typing import Tuple

from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ContentQuality:
    """Quality assessment of article content"""
    is_valid: bool
    confidence: float
    issues: list[str]
    word_count: int
    
    # Specific checks
    is_paywall: bool = False
    is_too_short: bool = False
    is_low_quality: bool = False


class ContentValidator:
    """Validate article content quality using LLM"""
    
    def __init__(self, openai_api_key: str):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=openai_api_key
        )
    
    async def validate(self, text: str, url: str) -> ContentQuality:
        """
        Validate article content quality.
        
        Returns:
            ContentQuality with validation results
        """
        
        issues = []
        word_count = len(text.split())
        
        # Check 1: Word count (fast)
        if word_count < 150:
            issues.append(f"Too short ({word_count} words)")
            return ContentQuality(
                is_valid=False,
                confidence=1.0,
                issues=issues,
                word_count=word_count,
                is_too_short=True
            )
        
        # Check 2: Paywall detection (LLM-based)
        is_paywall, paywall_confidence = await self._detect_paywall(text, url)
        
        if is_paywall and paywall_confidence > 0.7:
            issues.append(f"Paywall detected (confidence: {paywall_confidence:.2f})")
            return ContentQuality(
                is_valid=False,
                confidence=paywall_confidence,
                issues=issues,
                word_count=word_count,
                is_paywall=True
            )
        
        # Check 3: Basic quality (simple heuristics)
        if word_count < 300 and self._has_quality_issues(text):
            issues.append("Low quality content (short + low signal)")
            return ContentQuality(
                is_valid=False,
                confidence=0.8,
                issues=issues,
                word_count=word_count,
                is_low_quality=True
            )
        
        # Content is valid
        return ContentQuality(
            is_valid=True,
            confidence=0.95,
            issues=[],
            word_count=word_count
        )
    
    async def _detect_paywall(self, text: str, url: str) -> Tuple[bool, float]:
        """
        Use LLM to detect if content is behind a paywall.
        Handles hard paywalls, soft paywalls, subscription prompts.
        """
        
        # Sample first 1500 chars (paywalls usually appear early)
        sample = text[:1500]
        
        llm_prompt = f"""Determine if this article content is behind a paywall or subscription wall.

URL: {url}

CONTENT SAMPLE (first 1500 chars):
{sample}

PAYWALL INDICATORS:
- Hard paywall: "Subscribe to read", "Premium content", "This article is for subscribers only"
- Soft paywall: Shows intro then "Continue reading with subscription"
- Trial prompts: "Sign up for free trial to continue"
- Login walls: "Log in to read more", "Members only"
- Truncated content: Article suddenly ends mid-sentence with subscription prompt

NOT A PAYWALL:
- Newsletter signup boxes (optional, content still accessible)
- Ads or promotional banners
- Social media sharing prompts
- Comments section login (article itself is accessible)

Respond with ONLY valid JSON:
{{
  "is_paywall": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why you classified it this way",
  "paywall_type": "hard" | "soft" | "trial" | "login" | "none"
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
            
            is_paywall = result.get("is_paywall", False)
            confidence = result.get("confidence", 0.5)
            paywall_type = result.get("paywall_type", "none")
            
            if is_paywall:
                logger.info(f"🚫 Paywall detected ({paywall_type}, confidence: {confidence:.2f}): {url[:60]}")
            else:
                logger.debug(f"✅ No paywall detected: {url[:60]}")
            
            return is_paywall, float(confidence)
            
        except Exception as e:
            logger.error(f"❌ Paywall detection failed: {e}")
            # Conservative fallback: check for obvious keywords
            return self._simple_paywall_check(text), 0.6
    
    def _simple_paywall_check(self, text: str) -> bool:
        """Simple keyword-based paywall check as fallback"""
        text_lower = text.lower()
        
        paywall_keywords = [
            'subscribe to read',
            'subscription required',
            'premium content',
            'subscribers only',
            'log in to continue',
            'sign up to read',
            'become a member to',
            'this article is for',
        ]
        
        return any(keyword in text_lower for keyword in paywall_keywords)
    
    def _has_quality_issues(self, text: str) -> bool:
        """Check for basic quality issues"""
        
        # High ratio of non-alphanumeric characters (likely navigation/UI text)
        alphanumeric_ratio = sum(c.isalnum() or c.isspace() for c in text) / len(text)
        if alphanumeric_ratio < 0.8:
            return True
        
        # Too many repeated words (likely template/boilerplate)
        words = text.lower().split()
        if len(words) > 50:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.4:  # Less than 40% unique words
                return True
        
        return False


async def validate_content(text: str, url: str) -> ContentQuality:
    """
    Convenience function to validate article content.
    
    Returns:
        ContentQuality object with validation results
    """
    settings = get_settings()
    validator = ContentValidator(settings.openai_api_key)
    return await validator.validate(text, url)

