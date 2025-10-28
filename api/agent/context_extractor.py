"""
Context Extractor - Intelligently extracts topic/company context from URLs and prompts
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_context_from_url_and_prompt(url: str, prompt: str) -> dict:
    """
    Extract contextual information about what the user is looking for.
    
    Returns:
        {
            "company": "Marico",  # If a company is identified
            "topic": "Marico news",  # General topic
            "context_type": "company_stock_page",  # Type of page
            "is_specific": True  # Whether this is about a specific entity
        }
    """
    context = {
        "company": None,
        "topic": None,
        "context_type": "unknown",
        "is_specific": False
    }
    
    # Extract from URL
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    
    # Pattern 1: MoneyControl stock quote
    # /india/stockpricequote/category/COMPANY/code
    if "moneycontrol.com" in parsed.netloc and "stockpricequote" in parsed.path:
        if len(path_parts) >= 4:
            company_slug = path_parts[3]
            company_name = company_slug.replace("-", " ").title()
            context["company"] = company_name
            context["topic"] = f"{company_name} news"
            context["context_type"] = "company_stock_page"
            context["is_specific"] = True
            logger.info(f"Extracted company from stockpricequote URL: {company_name}")
    
    # Pattern 2: MoneyControl company-article
    # /company-article/COMPANY/news/code
    elif "moneycontrol.com" in parsed.netloc and "company-article" in parsed.path:
        if len(path_parts) >= 2:
            company_slug = path_parts[1]
            company_name = company_slug.replace("-", " ").title()
            context["company"] = company_name
            context["topic"] = f"{company_name} news"
            context["context_type"] = "company_news_page"
            context["is_specific"] = True
            logger.info(f"Extracted company from company-article URL: {company_name}")
    
    # Extract from prompt (fallback or enhancement)
    if not context["company"]:
        # Look for company names in prompt (common patterns)
        prompt_lower = prompt.lower()
        
        # Pattern: "Marico news", "about Marico", "for Marico"
        company_patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+news\b',
            r'\babout\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
            r'\bfor\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
        ]
        
        for pattern in company_patterns:
            match = re.search(pattern, prompt)
            if match:
                company_name = match.group(1)
                context["company"] = company_name
                context["topic"] = f"{company_name} news"
                context["is_specific"] = True
                logger.info(f"Extracted company from prompt: {company_name}")
                break
    
    # If we found a company, mark as specific
    if context["company"]:
        context["is_specific"] = True
        if not context["topic"]:
            context["topic"] = f"{context['company']} news"
    else:
        # Generic topic from prompt
        context["topic"] = prompt
        context["is_specific"] = False
    
    logger.info(f"Context extracted: {context}")
    return context


def validate_page_relevance(html: str, page_url: str, expected_context: dict) -> dict:
    """
    Validate if a page is actually about what we're looking for.
    
    Returns:
        {
            "is_relevant": True/False,
            "confidence": "high"/"medium"/"low",
            "reason": "explanation"
        }
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Get page title and text sample
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Get first 1000 chars of body text
    body_text = soup.get_text(separator=" ", strip=True)[:1000].lower()
    title_lower = title.lower()
    url_lower = page_url.lower()
    
    # If looking for a specific company
    if expected_context.get("is_specific") and expected_context.get("company"):
        company_name = expected_context["company"].lower()
        
        # Check if company name appears in title or URL
        in_title = company_name in title_lower
        in_url = company_name in url_lower
        in_body = company_name in body_text
        
        # Generic news indicators (BAD signs)
        generic_news_indicators = [
            "world news", "international news", "latest news", "breaking news",
            "top stories", "news headlines", "global news"
        ]
        is_generic = any(indicator in title_lower for indicator in generic_news_indicators)
        
        if in_title and in_url:
            return {
                "is_relevant": True,
                "confidence": "high",
                "reason": f"Company '{company_name}' found in both title and URL"
            }
        elif in_title or (in_url and in_body):
            return {
                "is_relevant": True,
                "confidence": "medium",
                "reason": f"Company '{company_name}' found in page"
            }
        elif is_generic:
            return {
                "is_relevant": False,
                "confidence": "high",
                "reason": f"Page appears to be generic news, not specific to '{company_name}'"
            }
        elif in_body:
            return {
                "is_relevant": True,
                "confidence": "low",
                "reason": f"Company '{company_name}' mentioned in content"
            }
        else:
            return {
                "is_relevant": False,
                "confidence": "medium",
                "reason": f"No clear mention of '{company_name}'"
            }
    
    # For generic topics, harder to validate
    return {
        "is_relevant": True,
        "confidence": "low",
        "reason": "Cannot validate generic topic"
    }

