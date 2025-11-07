"""
LLM-Based Page Analysis and Decision Making

This module replaces rule-based page analysis with LLM-driven decisions.
The LLM decides at each navigation step what action to take.
"""

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


class PageAction(str, Enum):
    """Actions the agent can take on a page"""
    EXTRACT_CONTENT = "EXTRACT_CONTENT"  # This page has content to extract
    EXTRACT_LINKS = "EXTRACT_LINKS"      # This page lists content (need to go deeper)
    NAVIGATE_TO = "NAVIGATE_TO"          # Navigate to a specific section
    STOP = "STOP"                        # Dead end or irrelevant


@dataclass
class PageDecision:
    """Decision about what to do with a page"""
    action: PageAction
    reasoning: str
    confidence: float  # 0.0 to 1.0
    page_type: str  # article, forum_thread, forum_listing, news_listing, company_profile, other
    target_url: Optional[str] = None  # Only if action=NAVIGATE_TO
    contains_relevant_content: bool = False


def extract_all_links(html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Extract ALL actual links from HTML page.
    This constrains the LLM to only choose from real links.
    
    Returns:
        List of dicts with 'url', 'text', and 'href'
    """
    from urllib.parse import urljoin, urlparse
    
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    seen_urls = set()
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        text = a_tag.get_text(strip=True)
        
        # Skip empty, javascript, or fragment-only links
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        
        # Make absolute URL
        try:
            absolute_url = urljoin(base_url, href)
            parsed = urlparse(absolute_url)
            
            # Skip if not http/https
            if parsed.scheme not in ['http', 'https']:
                continue
            
            # Deduplicate
            if absolute_url in seen_urls:
                continue
            
            seen_urls.add(absolute_url)
            links.append({
                'url': absolute_url,
                'text': text[:100] if text else '',  # Truncate long text
                'href': href
            })
        except Exception as e:
            logger.debug(f"Failed to process link: {href} - {e}")
            continue
    
    logger.info(f"📎 Extracted {len(links)} actual links from page")
    return links


def clean_html_for_llm(html: str, max_chars: int = 30000) -> str:
    """
    Clean and truncate HTML for LLM consumption.
    Remove noise, keep structure hints.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove noise
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'img', 'svg']):
        tag.decompose()
    
    # Get text with minimal structure
    text = soup.get_text(separator='\n', strip=True)
    
    # Truncate
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    
    return text


async def analyze_and_decide(
    html: str,
    url: str,
    intent: Dict,  # From UserIntent.to_dict()
    depth: int,
    max_depth: int = 3
) -> PageDecision:
    """
    Analyze a page and decide what action to take.
    
    This is the CORE decision-making function that replaces all navigation logic.
    
    Args:
        html: Page HTML content
        url: Page URL
        intent: User intent dict with topic, target_section, time_range, etc.
        depth: Current navigation depth
        max_depth: Maximum allowed depth
        
    Returns:
        PageDecision with action to take
    """
    settings = get_settings()
    
    # Extract actual links for validation
    available_links = extract_all_links(html, url)
    
    # Clean HTML for LLM
    cleaned_html = clean_html_for_llm(html, max_chars=8000)
    
    # Get page title
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else "No title"
    
    # Build link list for prompt
    link_list = "\n".join([
        f"  - [{link['text'][:60] if link['text'] else 'No text'}] → {link['url']}"
        for link in available_links[:100]  # Max 100 links in prompt
    ])
    
    if not link_list:
        link_list = "(No links found on page)"
    
    # Build LLM prompt
    topic = intent.get('topic', '')
    target_section = intent.get('target_section', '')
    time_range_days = intent.get('time_range_days', 7)
    
    prompt = f"""You are an expert web navigation strategist with deep understanding of information architecture and content discovery.

═══════════════════════════════════════════════════════════════════════════════
📋 MISSION
═══════════════════════════════════════════════════════════════════════════════
User wants: {topic}
Target section: {target_section or '(any section - use your judgment)'}
Time sensitivity: Last {time_range_days} days (recent content only!)

═══════════════════════════════════════════════════════════════════════════════
📍 CURRENT SITUATION
═══════════════════════════════════════════════════════════════════════════════
URL: {url}
Title: {page_title}
Navigation depth: {depth}/{max_depth} (deeper = more focused)

═══════════════════════════════════════════════════════════════════════════════
🔗 AVAILABLE ACTIONS & LINKS
═══════════════════════════════════════════════════════════════════════════════
{link_list}

═══════════════════════════════════════════════════════════════════════════════
📄 PAGE CONTENT SAMPLE
═══════════════════════════════════════════════════════════════════════════════
{cleaned_html}

═══════════════════════════════════════════════════════════════════════════════
🎯 YOUR TASK: STRATEGIC DECISION-MAKING
═══════════════════════════════════════════════════════════════════════════════

Use CHAIN-OF-THOUGHT reasoning:

Step 1: ANALYZE THE PAGE
- What type of page is this? (hub, listing, content, profile, etc.)
- Does it contain the END GOAL content or is it a waypoint?
- What patterns do you see in the links and content structure?

Step 2: ASSESS RELEVANCE TO USER INTENT
- Does this page match what user is looking for?
- If target_section specified, does this page relate to it?
- Are we getting closer or further from the goal?

Step 3: CONSIDER NAVIGATION DEPTH **CRITICAL**
- Current depth: {depth}/{max_depth}

**DEPTH-BASED RULES (MUST FOLLOW):**

DEPTH 0-1 (Exploration):
- Can use NAVIGATE_TO to find better sections
- Can use EXTRACT_LINKS if on a listing page
- Goal: Find the right listing page

DEPTH 2+ (Extraction ONLY):
- **FORBIDDEN**: NAVIGATE_TO (already deep enough!)
- **ALLOWED**: EXTRACT_CONTENT (if individual article/post)
- **ALLOWED**: STOP (if irrelevant)
- **FORBIDDEN**: EXTRACT_LINKS (too deep for more listings)
- Rule: At depth 2+, you're iterating through a list from depth 1. Extract or skip, don't navigate!

Step 4: CHOOSE OPTIMAL ACTION

ACTION OPTIONS:

1. **EXTRACT_CONTENT** ← Use when you're on a page WITH the actual information
   ✓ Individual article with full text
   ✓ Forum thread with discussion posts
   ✓ Blog post with complete content
   ✓ Press release with full details
   ✗ NOT for: Navigation pages, directories, listings, tables of contents

2. **EXTRACT_LINKS** ← Use when you're on a DIRECTORY of content
   ✓ News listing page showing multiple articles
   ✓ Forum board showing thread titles
   ✓ Category page with links to posts
   ✓ Search results page
   ✗ NOT for: Individual content pages (those should be EXTRACT_CONTENT)
   ⚠️  CRITICAL: A "list of threads" needs deeper navigation - go INTO the threads

3. **NAVIGATE_TO** ← Use when you need to reach a better section FIRST
   ✓ Homepage → "News Section" link
   ✓ Company profile → "Press Releases" link
   ✓ Generic page → "Forum" or "Blog" section
   ⚠️  Must select URL from AVAILABLE ACTIONS list above
   ⚠️  Best at depth 0-1, avoid at depth 2+

4. **STOP** ← Use when path is not productive
   ✓ Reached max depth without finding content
   ✓ Page is completely irrelevant
   ✓ Dead end (no useful links forward)

═══════════════════════════════════════════════════════════════════════════════
🧠 ADVANCED REASONING GUIDELINES
═══════════════════════════════════════════════════════════════════════════════

**Semantic Understanding:**
If target_section = "forum" → look for: forum, community, discussions, Q&A, talk
If target_section = "news" → look for: news, press, media, newsroom, updates, announcements
If target_section = "blog" → look for: blog, insights, articles, stories, posts
If target_section = "investor" → look for: investor, IR, shareholder, financial reports

**Pattern Recognition:**
- URLs with dates → likely individual articles (EXTRACT_CONTENT)
- URLs with /page/ or /p/ → pagination pages (EXTRACT_LINKS)
- URLs with /category/ or /tag/ → directory pages (NAVIGATE_TO or EXTRACT_LINKS)
- URLs with /thread/ or /post/ → individual content (EXTRACT_CONTENT)

**Quality Signals:**
High confidence (>0.8) when:
- Page type clearly matches one action
- Links are obviously relevant to user intent
- Content structure is straightforward

Lower confidence (<0.6) when:
- Ambiguous page structure
- Mixed content types
- Unclear if we're at the right depth

**Decision Quality Checklist:**
✓ Will this action get user closer to their goal?
✓ Am I respecting depth constraints? (don't navigate at depth 2+)
✓ If NAVIGATE_TO: Is the target URL actually in the available links?
✓ If EXTRACT_LINKS: Am I on a listing page, not individual content?
✓ If EXTRACT_CONTENT: Does this page have the actual information user wants?

═══════════════════════════════════════════════════════════════════════════════
📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return ONLY valid JSON (no markdown, no comments):

{{
  "action": "EXTRACT_CONTENT" | "EXTRACT_LINKS" | "NAVIGATE_TO" | "STOP",
  "reasoning": "2-3 sentence explanation of your chain-of-thought decision",
  "confidence": 0.95,
  "page_type": "article" | "forum_thread" | "forum_listing" | "content_listing" | "blog_post" | "press_release" | "research_report" | "event_page" | "company_profile" | "other",
  "target_url": "full URL from AVAILABLE ACTIONS (only if NAVIGATE_TO, else null)",
  "contains_relevant_content": true/false
}}

Think strategically. Think like an expert information architect. Make the decision that best serves the user's goal."""
    
    try:
        # Use GPT-4o for complex reasoning
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
        
        # Validate action
        action = PageAction(result['action'])
        
        # ═══════════════════════════════════════════════════════════════════
        # ENFORCE DEPTH-BASED RULES (Don't trust LLM blindly!)
        # ═══════════════════════════════════════════════════════════════════
        if depth >= 2:
            # At depth 2+, only EXTRACT_CONTENT or STOP are allowed
            if action == PageAction.NAVIGATE_TO:
                logger.warning(f"⚠️ LLM chose NAVIGATE_TO at depth {depth} (forbidden!), forcing STOP")
                logger.warning(f"   Original reasoning: {result.get('reasoning', 'N/A')}")
                action = PageAction.STOP
                result['reasoning'] = f"Depth {depth} reached - no more navigation allowed"
            elif action == PageAction.EXTRACT_LINKS:
                logger.warning(f"⚠️ LLM chose EXTRACT_LINKS at depth {depth} (too deep!), forcing STOP")
                logger.warning(f"   Original reasoning: {result.get('reasoning', 'N/A')}")
                action = PageAction.STOP  
                result['reasoning'] = f"Depth {depth} reached - too deep for link extraction"
        
        # Validate target_url if NAVIGATE_TO
        target_url = result.get('target_url')
        if action == PageAction.NAVIGATE_TO:
            if not target_url:
                logger.warning("LLM chose NAVIGATE_TO but no target_url provided, changing to STOP")
                action = PageAction.STOP
            else:
                # Check if URL exists in available links
                available_urls = {link['url'] for link in available_links}
                if target_url not in available_urls:
                    logger.warning(f"LLM chose non-existent URL: {target_url[:100]}")
                    logger.warning(f"Available URLs count: {len(available_urls)}")
                    # Try to find close match
                    target_url = _find_closest_link(target_url, available_links)
                    if not target_url:
                        logger.warning("No close match found, changing action to STOP")
                        action = PageAction.STOP
        
        decision = PageDecision(
            action=action,
            reasoning=result.get('reasoning', 'No reasoning provided'),
            confidence=float(result.get('confidence', 0.5)),
            page_type=result.get('page_type', 'other'),
            target_url=target_url,
            contains_relevant_content=bool(result.get('contains_relevant_content', False))
        )
        
        logger.info(f"🤖 Decision: {decision.action.value} (confidence: {decision.confidence:.2f})")
        logger.info(f"   Reasoning: {decision.reasoning}")
        
        return decision
        
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}")
        logger.error(f"Response: {response_text[:300]}")
        # Fallback to STOP
        return PageDecision(
            action=PageAction.STOP,
            reasoning="Failed to parse LLM response",
            confidence=0.0,
            page_type="other"
        )
    
    except Exception as e:
        logger.error(f"Page decision failed: {e}")
        # Fallback to STOP
        return PageDecision(
            action=PageAction.STOP,
            reasoning=f"Error: {str(e)}",
            confidence=0.0,
            page_type="other"
        )


def _find_closest_link(target_url: str, available_links: List[Dict[str, str]]) -> Optional[str]:
    """
    Find the closest matching link if LLM hallucinates a URL.
    Uses simple string similarity.
    """
    if not available_links:
        return None
    
    # Try exact match first
    for link in available_links:
        if link['url'] == target_url:
            return link['url']
    
    # Try domain + path match
    from urllib.parse import urlparse
    try:
        target_parsed = urlparse(target_url)
        target_path = target_parsed.path.lower()
        
        for link in available_links:
            link_parsed = urlparse(link['url'])
            link_path = link_parsed.path.lower()
            
            # If paths are very similar
            if target_path and link_path and target_path in link_path:
                logger.info(f"Found close match: {link['url']}")
                return link['url']
    except Exception:
        pass
    
    return None


def normalize_url(url: str) -> str:
    """
    Normalize URL for cycle detection.
    Removes fragments, trailing slashes, makes lowercase.
    """
    from urllib.parse import urlparse, urlunparse
    
    try:
        parsed = urlparse(url)
        # Remove fragment, normalize path
        path = parsed.path.rstrip('/')
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            parsed.query,
            ''  # Remove fragment
        ))
        return normalized
    except Exception:
        return url.lower()

