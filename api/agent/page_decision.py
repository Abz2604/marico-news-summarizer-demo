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
from config import get_settings
from .llm_factory import get_smart_llm

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


async def _select_navigation_target(
    available_links: List[Dict],
    intent: Dict,
    page_title: str,
    reasoning: str,
    llm
) -> Optional[str]:
    """
    Second-phase: Select specific URL when NAVIGATE_TO is chosen.
    This is called only when needed, avoiding sending all URLs every time.
    """
    if not available_links:
        return None
    
    # Prepare link list with URLs (max 50 to keep it manageable)
    links_text = "\n".join([
        f"{i+1}. [{link['text'][:60] if link['text'] else 'No text'}]\n   URL: {link['url']}"
        for i, link in enumerate(available_links[:50])
    ])
    
    target_section = intent.get('target_section', '')
    topic = intent.get('topic', '')
    
    prompt = f"""You decided to NAVIGATE_TO a better section. Now select the specific link.

Current page: {page_title}
Your reasoning: {reasoning}
User goal: {topic}
Target section: {target_section or 'any relevant section'}

Available links (select ONE):
{links_text}

Select the BEST link to navigate to. Consider:
- Which link gets closest to the user's goal?
- Which section/page would have the content they need?
- Semantic matches (e.g., "nails" section for nail content)

Respond with JSON only:
{{
  "selected_url": "full URL of chosen link",
  "link_number": 1-50,
  "reason": "Why this link is best (1 sentence)"
}}"""
    
    try:
        response = await llm.ainvoke(prompt)
        response_text = response.content.strip()
        
        # Handle markdown
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
        selected_url = result.get('selected_url')
        
        if selected_url:
            logger.info(f"✅ Selected: {selected_url[:80]}")
            logger.info(f"   Reason: {result.get('reason', 'N/A')}")
            return selected_url
        
        return None
        
    except Exception as e:
        logger.error(f"URL selection failed: {e}")
        return None


def clean_html_for_llm(html: str, max_chars: int = 8000, url: str = "") -> str:
    """
    Smart HTML cleaning that preserves context while removing noise.
    
    Strategy:
    - Keep semantic structure (headers, main content areas)
    - Remove navigation/footer boilerplate
    - Keep images as [IMG: alt_text] to preserve context
    - Keep timestamps/dates (critical for forums/articles)
    - Preserve forum post structure
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Remove complete noise (no context value)
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'canvas']):
        tag.decompose()
    
    # 2. Remove common boilerplate (navigation, ads, footers)
    for tag in soup.find_all(['nav', 'aside', 'footer']):
        tag.decompose()
    
    # Remove elements with common ad/navigation classes/ids
    boilerplate_patterns = ['nav', 'menu', 'sidebar', 'footer', 'header', 'ads', 'advertisement']
    for pattern in boilerplate_patterns:
        for tag in soup.find_all(class_=lambda x: x and pattern in x.lower()):
            tag.decompose()
        for tag in soup.find_all(id=lambda x: x and pattern in x.lower()):
            tag.decompose()
    
    # 3. Replace images with context-preserving text
    for img in soup.find_all('img'):
        alt_text = img.get('alt', '').strip()
        if alt_text:
            img.replace_with(f"[IMG: {alt_text}]")
        else:
            img.decompose()
    
    # 4. Extract text with structure markers
    # Prioritize main content areas
    main_content = soup.find('main') or soup.find('article') or soup.find(class_=lambda x: x and 'content' in x.lower()) or soup
    
    # Build structured text
    lines = []
    
    # 5. SPECIAL HANDLING FOR FORUMS - detect and preserve post structure
    # IMPORTANT: Be very selective to avoid false positives (comment sections, etc.)
    
    # First check: Is this likely a forum based on URL?
    is_likely_forum_url = any(pattern in url.lower() for pattern in 
                              ['/forum', 'forum.', 'community', 'discussion', '/thread'])
    
    forum_posts = []
    
    if is_likely_forum_url:
        # Only check for forum structure if URL suggests it's a forum
        # Use VERY specific patterns to avoid false positives
        forum_post_patterns = ['forum-post', 'thread-post', 'forum_post', 'thread_post', 'message-body', 'post-content']
        
        for pattern in forum_post_patterns:
            forum_posts.extend(main_content.find_all(class_=lambda x: x and pattern.replace('-', '') in x.lower().replace('-', '').replace('_', '')))
        
        # Additional check: Look for typical forum structure (author + date + content in same container)
        for potential_post in main_content.find_all(['div', 'article']):
            classes = ' '.join(potential_post.get('class', [])).lower()
            if 'post' in classes and 'author' in str(potential_post)[:500] and ('date' in str(potential_post)[:500] or 'time' in str(potential_post)[:500]):
                if potential_post not in forum_posts:
                    forum_posts.append(potential_post)
    
    # Require at least 5 posts to confidently identify as forum (avoids comment sections)
    if len(forum_posts) >= 5:
        logger.info(f"🗨️  Detected forum structure with {len(forum_posts)} posts - preserving post boundaries")
        lines.append("═══ FORUM THREAD DETECTED ═══")
        
        for i, post in enumerate(forum_posts[:20], 1):  # Max 20 posts to show
            # Extract author
            author_elem = post.find(class_=lambda x: x and ('author' in x.lower() or 'user' in x.lower()))
            author = author_elem.get_text(strip=True) if author_elem else "Unknown"
            
            # Extract date
            date_elem = post.find(['time', 'datetime']) or post.find(class_=lambda x: x and 'date' in x.lower())
            date = date_elem.get_text(strip=True) if date_elem else ""
            
            # Extract post content (text only, no nested metadata)
            content_elem = post.find(class_=lambda x: x and ('content' in x.lower() or 'text' in x.lower() or 'body' in x.lower()))
            content = content_elem.get_text(strip=True) if content_elem else post.get_text(strip=True)
            
            # Format as clear post
            lines.append(f"\n--- POST #{i} ---")
            lines.append(f"Author: {author}")
            if date:
                lines.append(f"Date: {date}")
            lines.append(f"Content: {content[:500]}")  # Limit post length
        
        lines.append("\n═══ END FORUM POSTS ═══")
    else:
        # 6. Standard extraction (not a forum)
        # Extract with semantic markers
        for elem in main_content.descendants:
            if isinstance(elem, str):
                text = elem.strip()
                if text:
                    lines.append(text)
            elif elem.name in ['h1', 'h2', 'h3']:
                text = elem.get_text(strip=True)
                if text:
                    lines.append(f"\n## {text}")
            elif elem.name in ['time', 'datetime']:
                text = elem.get_text(strip=True)
                if text:
                    lines.append(f"[DATE: {text}]")
        
        # Fallback: if structured extraction got nothing, use simple text
        if not lines:
            lines = [main_content.get_text(separator='\n', strip=True)]
    
    # Join and clean up
    text = '\n'.join(lines)
    
    # Remove excessive whitespace
    import re
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
    text = re.sub(r' {2,}', ' ', text)  # Max 1 space
    
    # Truncate intelligently (try to break at sentence/paragraph)
    if len(text) > max_chars:
        text = text[:max_chars]
        # Try to break at paragraph
        last_para = text.rfind('\n\n')
        if last_para > max_chars * 0.8:  # If we're close enough
            text = text[:last_para]
        text += "\n\n... (content continues)"
    
    return text


async def analyze_and_decide(
    html: str,
    url: str,
    intent: Dict,  # From UserIntent.to_dict()
    depth: int,
    max_depth: int = 3,
    plan: Optional[Dict] = None
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
        plan: Optional navigation plan with expected_page_type for context
        
    Returns:
        PageDecision with action to take
    """
    settings = get_settings()
    
    # Extract actual links for validation
    available_links = extract_all_links(html, url)
    
    # Clean HTML for LLM (pass URL for forum detection)
    cleaned_html = clean_html_for_llm(html, max_chars=8000, url=url)
    
    # Get page title
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else "No title"
    
    # Build smart link summary (don't send all links - wasteful!)
    link_count = len(available_links)
    
    if link_count == 0:
        link_summary = "No clickable links found on page."
    else:
        # Categorize links
        internal_links = [l for l in available_links if url.split('/')[2] in l['url']]
        external_links = [l for l in available_links if url.split('/')[2] not in l['url']]
        
        # Get sample links (max 8 to show diversity)
        sample_links = available_links[:8]
        sample_text = "\n".join([
            f"  - [{link['text'][:50] if link['text'] else 'No text'}]"
            for link in sample_links
        ])
        
        link_summary = f"""Total links: {link_count} ({len(internal_links)} internal, {len(external_links)} external)

Sample links (showing {len(sample_links)} of {link_count}):
{sample_text}
{'... and ' + str(link_count - len(sample_links)) + ' more links' if link_count > len(sample_links) else ''}

Note: Full link list available if you choose NAVIGATE_TO or EXTRACT_LINKS action."""
    
    # Build LLM prompt
    topic = intent.get('topic', '')
    target_section = intent.get('target_section', '')
    time_range_days = intent.get('time_range_days', 7)
    
    # Extract plan context if available
    expected_page_type = None
    plan_strategy = None
    if plan:
        expected_page_type = plan.get('expected_page_type')
        plan_strategy = plan.get('strategy')
    
    # Build plan context string
    plan_context = ""
    if expected_page_type and depth == 0:
        # At depth 0, the plan tells us what type of page we SHOULD be on
        plan_context = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║ 🎯 STRATEGIC CONTEXT (from planning phase) - HIGHEST PRIORITY            ║
╚═══════════════════════════════════════════════════════════════════════════╝

Expected page type: {expected_page_type}
Strategy: {plan_strategy}

🚨 🚨 🚨 MANDATORY RULE 🚨 🚨 🚨
The planning phase analyzed this seed URL and determined it's a '{expected_page_type}' page.
This is MORE RELIABLE than analyzing HTML snippets!

REQUIRED ACTIONS BY PAGE TYPE:
✅ 'forum_thread' → MUST use EXTRACT_CONTENT (posts are on THIS page)
✅ 'article' → MUST use EXTRACT_CONTENT (article text is on THIS page)  
✅ 'forum_listing' → Use EXTRACT_LINKS (need to click into threads)
✅ 'content_listing' → Use EXTRACT_LINKS (need to click into articles)

⚠️  DO NOT choose EXTRACT_LINKS if plan says 'forum_thread' or 'article'!
⚠️  The content you need is ALREADY on this page - extract it directly!
⚠️  Ignoring this will result in navigation loops and failure!
"""
    
    prompt = f"""You are an expert web navigation strategist with deep understanding of information architecture and content discovery.

═══════════════════════════════════════════════════════════════════════════════
📋 MISSION
═══════════════════════════════════════════════════════════════════════════════
User wants: {topic}
Target section: {target_section or '(any section - use your judgment)'}
Time sensitivity: Last {time_range_days} days (recent content only!)
{plan_context}
═══════════════════════════════════════════════════════════════════════════════
📍 CURRENT SITUATION
═══════════════════════════════════════════════════════════════════════════════
URL: {url}
Title: {page_title}
Navigation depth: {depth}/{max_depth} (deeper = more focused)

═══════════════════════════════════════════════════════════════════════════════
📄 PAGE CONTENT (Primary decision input - analyze this carefully!)
═══════════════════════════════════════════════════════════════════════════════
{cleaned_html}

═══════════════════════════════════════════════════════════════════════════════
🔗 LINKS OVERVIEW (Summary only - detailed links provided if you choose navigation)
═══════════════════════════════════════════════════════════════════════════════
{link_summary}

═══════════════════════════════════════════════════════════════════════════════
🎯 YOUR TASK: STRATEGIC DECISION-MAKING
═══════════════════════════════════════════════════════════════════════════════

🚀 **OPTIMIZATION: LISTING PAGE PRIORITY AT DEPTH 0**
If depth = 0 (seed URL) and page shows MULTIPLE article links/items:
→ **STRONGLY PREFER EXTRACT_LINKS** - This is the most efficient path!
→ NAVIGATE_TO should only be used if this is clearly NOT a listing (e.g., homepage, profile)

Use CHAIN-OF-THOUGHT reasoning:

Step 1: ANALYZE THE PAGE CONTENT (Focus on content, not links!)
- What type of page is this based on CONTENT? (hub, listing, individual article/thread, profile, etc.)
- **CRITICAL**: Count how many distinct items/articles you see:
  * ONE article with FULL text? → Individual content page
  * MULTIPLE article titles with snippets? → Listing/directory page
  * Multiple thread titles? → Forum listing (not thread)
  * One thread with multiple posts? → Forum thread
- Key question: Is FULL/COMPLETE information visible, or just previews?
- If FULL content of ONE item → EXTRACT_CONTENT
- If MULTIPLE items with previews → EXTRACT_LINKS

Step 2: ASSESS RELEVANCE TO USER INTENT
- Does the page CONTENT match what user is looking for?
- If target_section specified, is that content VISIBLE here?
- Are we at the destination or do we need to navigate further?

Step 3: CONSIDER NAVIGATION DEPTH **CRITICAL**
- Current depth: {depth}/{max_depth}

**DEPTH-BASED RULES (MUST FOLLOW):**

DEPTH 0 (Seed URL - OPTIMIZATION MODE):
- **PREFERRED**: EXTRACT_LINKS if this looks like a listing page (news, blog, forum directory)
- **ALLOWED**: EXTRACT_CONTENT if this is a direct article/thread
- **FALLBACK**: NAVIGATE_TO only if clearly NOT a listing (homepage, profile, irrelevant hub)
- **Goal**: Start extraction immediately if possible!

DEPTH 1 (Following Links):
- **ALLOWED**: EXTRACT_CONTENT (extract from individual articles)
- **ALLOWED**: EXTRACT_LINKS (if reached a listing page via navigation)
- **AVOID**: NAVIGATE_TO (prefer extraction at this level)
- **ALLOWED**: STOP (if irrelevant)

DEPTH 2+ (Deep Extraction ONLY):
- **FORBIDDEN**: NAVIGATE_TO (already deep enough!)
- **FORBIDDEN**: EXTRACT_LINKS (too deep for more listings)
- **ALLOWED**: EXTRACT_CONTENT (if individual article/post)
- **ALLOWED**: STOP (if irrelevant)
- Rule: At depth 2+, you're iterating through a list from depth 1. Extract or skip, don't navigate!

Step 4: CHOOSE OPTIMAL ACTION

ACTION OPTIONS (prioritized for efficiency):

1. **EXTRACT_LINKS** ← **PREFERRED at depth 0** for listing pages (news, blog, forum directory)
   ✓ Multiple article titles/links visible (2+ items)
   ✓ Article previews or snippets shown (need to click for full content)
   ✓ News listing, blog category, forum board, press releases page
   ✓ This is the MOST EFFICIENT path - extract all relevant links and fetch them!
   ✗ NOT for: Single article pages, full content pages
   
   🔑 KEY TEST at depth 0: See multiple clickable article links? → EXTRACT_LINKS!

2. **EXTRACT_CONTENT** ← Use when ONE piece of content with FULL details
   ✓ Individual article with COMPLETE text (not just headline/snippet)
   ✓ Forum thread with ACTUAL discussion posts (not just thread title)
   ✓ Product page with FULL reviews (not just review summaries)
   ✓ Blog post with COMPLETE content (not just preview)
   ✗ NOT for: Listings with multiple items, preview/snippet pages, directories
   
   🔑 KEY TEST: Can you read the FULL content here, or do you need to click links to get details?
   - If FULL content visible → EXTRACT_CONTENT
   - If only titles/previews → EXTRACT_LINKS

3. **NAVIGATE_TO** ← **FALLBACK ONLY** - Use when seed URL is NOT a listing (e.g., homepage)
   ✓ Homepage → specific section link (e.g., "News", "Forum", "Reviews")
   ✓ Company profile → better section (e.g., "Press Releases")
   ⚠️  System will provide detailed link options when you choose this action
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
        llm = get_smart_llm(temperature=0)
        
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
        page_type = result.get('page_type', 'other')
        
        # ═══════════════════════════════════════════════════════════════════
        # CONSISTENCY CHECK: Action must match page type
        # ═══════════════════════════════════════════════════════════════════
        if action == PageAction.EXTRACT_CONTENT and page_type in ['content_listing', 'forum_listing']:
            logger.warning(f"⚠️ Inconsistency detected: EXTRACT_CONTENT on {page_type} page!")
            logger.warning(f"   This is a LISTING page with multiple items - should use EXTRACT_LINKS")
            logger.warning(f"   Correcting to EXTRACT_LINKS...")
            action = PageAction.EXTRACT_LINKS
            result['reasoning'] = f"Corrected: {page_type} pages should extract links to individual items, not content from listing"
        
        # ═══════════════════════════════════════════════════════════════════
        # PLAN ENFORCEMENT at Depth 0: Trust the plan over LLM misidentification
        # ═══════════════════════════════════════════════════════════════════
        if depth == 0 and expected_page_type:
            # At seed URL, plan knows the truth - enforce it!
            if expected_page_type in ['forum_thread', 'article'] and action != PageAction.EXTRACT_CONTENT:
                logger.warning(f"⚠️ PLAN OVERRIDE: Plan says '{expected_page_type}' but LLM chose {action}")
                logger.warning(f"   At depth 0, trusting plan over page analysis")
                logger.warning(f"   Forcing EXTRACT_CONTENT...")
                action = PageAction.EXTRACT_CONTENT
                result['reasoning'] = f"Plan override: Seed URL identified as {expected_page_type} by planning phase - extracting content directly"
        
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
                # LLM decided to navigate but didn't have URLs to choose from
                # Make a follow-up query with full link list
                logger.info("🔄 NAVIGATE_TO chosen - fetching specific URL from full link list...")
                
                target_url = await _select_navigation_target(
                    available_links=available_links,
                    intent=intent,
                    page_title=page_title,
                    reasoning=result.get('reasoning', ''),
                    llm=llm
                )
                
                if not target_url:
                    logger.warning("Could not select navigation target, changing to STOP")
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

