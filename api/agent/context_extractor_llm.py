"""
Universal Context Extractor using LLM
Works for ANY website, not just MoneyControl
"""

import json
import logging
from typing import Optional
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


async def extract_context_with_llm(url: str, prompt: str) -> dict:
    """
    Universal context extraction using LLM.
    
    Works for:
    - MoneyControl (moneycontrol.com)
    - Bloomberg (bloomberg.com)
    - Reuters (reuters.com)
    - Yahoo Finance (finance.yahoo.com)
    - Company websites (marico.com, apple.com)
    - Any other news/financial site
    
    Args:
        url: The seed URL to analyze
        prompt: User's request
        
    Returns:
        {
            "company": "Marico" or None,
            "topic": "Marico news",
            "source_type": "financial_news",
            "is_specific": True,
            "confidence": "high" | "medium" | "low",
            "reasoning": "explanation"
        }
    """
    
    settings = get_settings()
    
    # Parse URL for basic info
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path
    
    # Build comprehensive extraction prompt
    extraction_prompt = f"""You are analyzing a web page to understand what the user is researching.

URL: {url}
Domain: {domain}
Path: {path}
User Prompt: {prompt}

TASK: Extract the following information:

1. COMPANY/ENTITY: What specific company, organization, or entity is this about?
   
   Guidelines:
   - Extract from URL structure, domain name, path components
   - Recognize stock tickers and convert to company names
   - Understand domain → company mapping
   
   Examples:
   * "bloomberg.com/quote/AAPL:US" → Apple
   * "reuters.com/companies/TSLA.O" → Tesla  
   * "moneycontrol.com/stockpricequote/personal-care/marico/M13" → Marico
   * "finance.yahoo.com/quote/MRCO.NS" → Marico
   * "marico.com/investors" → Marico (official site)
   * "apple.com/newsroom" → Apple (official site)
   * "techcrunch.com/ai-startups" → None (generic tech news)
   * "bloomberg.com" → None (homepage, not specific)
   
   Stock Tickers to recognize:
   - AAPL, AAPL:US → Apple
   - TSLA, TSLA.O → Tesla
   - MRCO.NS, MRCO:IN → Marico
   - GOOGL → Google/Alphabet
   - MSFT → Microsoft

2. TOPIC: What is the user researching?
   - If specific company: "[Company] news" or "[Company] [aspect from prompt]"
   - If generic: extract main topic from prompt
   
   Examples:
   * Company: Marico, Prompt: "latest updates" → "Marico news"
   * Company: Apple, Prompt: "Q3 earnings" → "Apple Q3 earnings"
   * Company: None, Prompt: "AI startups funding" → "AI startups funding"

3. SOURCE_TYPE: What kind of website is this?
   Categories:
   - official_company_site: investors.apple.com, marico.com/investors
   - financial_news: bloomberg.com, reuters.com, wsj.com
   - stock_aggregator: moneycontrol.com, yahoo finance, seeking alpha
   - tech_news: techcrunch.com, theverge.com, arstechnica.com
   - general_news: cnn.com, bbc.com
   - other: everything else

4. IS_SPECIFIC: Is this about a specific entity (true) or general topic (false)?
   - True: if you identified a company/entity
   - False: if it's a general topic or broad category

5. CONFIDENCE: How confident are you in the extraction?
   - high: Clear indicators (ticker in URL, company in domain, obvious patterns)
   - medium: Reasonable inference (path structure, common patterns)
   - low: Guessing or fallback to prompt

CRITICAL RULES:
- Be intelligent about URL patterns - every site structures URLs differently
- Recognize that "MRCO.NS" and "Marico" are the same entity
- Domain "marico.com" obviously means company Marico
- If domain IS the company (apple.com, marico.com), extract it!
- Don't be overly conservative - use contextual clues

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "company": "Marico",
  "topic": "Marico news",
  "source_type": "stock_aggregator",
  "is_specific": true,
  "confidence": "high",
  "reasoning": "URL contains marico in path, MoneyControl stock page"
}}
"""
    
    try:
        # Use gpt-4o-mini for cost efficiency
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.openai_api_key
        )
        
        response = await llm.ainvoke(extraction_prompt)
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
        
        logger.info(f"✅ LLM context extraction successful: {result}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return _fallback_context_extraction(url, prompt)
        
    except Exception as e:
        logger.error(f"LLM context extraction failed: {e}")
        return _fallback_context_extraction(url, prompt)


def _fallback_context_extraction(url: str, prompt: str) -> dict:
    """
    Fallback to basic heuristics if LLM fails.
    Better than nothing, but not as smart.
    """
    
    logger.warning("Using fallback context extraction")
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    
    company = None
    source_type = "unknown"
    
    # Basic domain → company mapping
    domain_companies = {
        "marico.com": "Marico",
        "apple.com": "Apple",
        "microsoft.com": "Microsoft",
        "google.com": "Google",
        "tesla.com": "Tesla",
    }
    
    for domain_key, company_name in domain_companies.items():
        if domain_key in domain:
            company = company_name
            source_type = "official_company_site"
            break
    
    # Basic source type detection
    if not company:
        if any(s in domain for s in ["bloomberg", "reuters", "wsj"]):
            source_type = "financial_news"
        elif any(s in domain for s in ["moneycontrol", "yahoo"]):
            source_type = "stock_aggregator"
        elif any(s in domain for s in ["techcrunch", "theverge", "arstechnica"]):
            source_type = "tech_news"
    
    # Try to extract company from prompt
    if not company:
        import re
        # Look for capitalized words that might be company names
        words = prompt.split()
        for i, word in enumerate(words):
            if word and word[0].isupper() and len(word) > 2:
                # Check if followed by "news", "updates", etc.
                if i + 1 < len(words) and words[i + 1].lower() in ["news", "updates", "earnings", "stock"]:
                    company = word
                    break
    
    return {
        "company": company,
        "topic": prompt if not company else f"{company} news",
        "source_type": source_type,
        "is_specific": company is not None,
        "confidence": "low",
        "reasoning": "Fallback heuristics due to LLM failure"
    }


# Backward compatibility: maintain old function signature
def extract_context_from_url_and_prompt(url: str, prompt: str) -> dict:
    """
    Synchronous wrapper for backward compatibility.
    For new code, use extract_context_with_llm() directly.
    
    WARNING: This uses sync fallback only! 
    Update callers to use async version for LLM intelligence.
    """
    logger.warning("Using synchronous context extraction (fallback only)")
    return _fallback_context_extraction(url, prompt)

