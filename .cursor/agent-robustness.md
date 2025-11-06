# Agent Robustness Plan

## Problem Statement

Current agent fails on multi-hop navigation scenarios (e.g., forums) because:
1. Extracts all links upfront without understanding page type
2. Uses article-specific extraction (`readability`) for all content types
3. No recursive navigation strategy
4. Treats forum listings as content pages

## Core Principle

**"Decide at each step, not in advance"**

Most scenarios are simple (1-2 hops). Optimize for common case, handle complex case safely.

---

## Architecture: LLM-Driven Decision Making

### High-Level Flow

```
User Prompt
    ↓
[Intent Extraction] (gpt-4o-mini)
    ↓
[Recursive Smart Navigation] (gpt-4o for decisions)
    ↓
    Decision Point:
    ├─→ Is this CONTENT? → Extract it (gpt-4o)
    ├─→ Is this LISTING? → Extract links → Recurse
    ├─→ Is this HUB? → Navigate to section → Recurse
    └─→ Is this IRRELEVANT? → Stop
    ↓
[Deduplicate & Summarize]
```

### Core Function

```python
async def smart_navigate(
    url: str,
    intent: Intent,
    collected: List[Content],
    depth: int = 0,
    visited: Set[str] = None
) -> List[Content]:
    """
    Recursively navigate and extract content based on LLM decisions.
    """
    
    # Initialize
    if visited is None:
        visited = set()
    
    # SAFETY: Exit conditions
    if depth >= 3:  # Hard limit
        return collected
    if len(collected) >= intent.max_articles:
        return collected
    if normalize_url(url) in visited:  # Prevent loops
        return collected
    
    visited.add(normalize_url(url))
    
    # STEP 1: Fetch page
    html = await fetch_url(url)
    if not html:
        return collected
    
    # STEP 2: Extract actual links (for validation)
    available_links = extract_all_links(html, url)
    
    # STEP 3: LLM Decision (gpt-4o)
    decision = await analyze_and_decide(
        html=html,
        url=url,
        intent=intent,
        available_links=available_links  # Constrain choices
    )
    
    # STEP 4: Execute decision
    if decision.action == "EXTRACT_CONTENT":
        content = await extract_content(html, url, intent)  # gpt-4o
        if await is_relevant(content, intent):  # gpt-4o-mini
            collected.append(content)
    
    elif decision.action == "EXTRACT_LINKS":
        links = await extract_relevant_links(html, url, intent)  # gpt-4o
        for link in links[:20]:  # Hard limit per page
            collected = await smart_navigate(
                link, intent, collected, depth + 1, visited
            )
            if len(collected) >= intent.max_articles:
                break
    
    elif decision.action == "NAVIGATE_TO":
        # Validate URL exists in page
        if decision.target_url not in available_links:
            logger.warning(f"LLM chose non-existent URL, stopping")
            return collected
        
        collected = await smart_navigate(
            decision.target_url, intent, collected, depth + 1, visited
        )
    
    # action == "STOP" → do nothing
    
    return collected
```

---

## Essential Safety Mechanisms

### 1. Prevent Infinite Loops ✅ CRITICAL
- **Visited URL tracking**: `visited: Set[str]`
- **URL normalization**: Remove fragments, trailing slashes, lowercase
- **Max depth limit**: Hard stop at depth=3

```python
if normalize_url(url) in visited:
    return collected
visited.add(normalize_url(url))
```

### 2. Prevent Wrong Branches ✅ CRITICAL
- **URL validation**: LLM can only choose from actual links on page
- **Intent matching**: Every decision considers user's `target_section`
- **Early stopping**: If decision confidence too low, stop instead of guessing

```python
# Give LLM the actual links to choose from
available_links = extract_all_links(html, url)
decision = await analyze_and_decide(
    html, url, intent, available_links  # ← Constrained
)

# Validate chosen URL exists
if decision.target_url not in available_links:
    return collected  # Stop instead of following bad link
```

### 3. Prevent Runaway Costs ✅ CRITICAL
- **Article limit**: Stop when `len(collected) >= max_articles`
- **Link limit per page**: Max 20 links extracted from any listing
- **Depth limit**: Max 3 levels deep

```python
if len(collected) >= intent.max_articles:
    return collected

links = await extract_relevant_links(...)
for link in links[:20]:  # Hard cap
    ...
```

### 4. Handle Edge Cases ✅ IMPORTANT
- **Fetch failures**: Return collected so far, don't crash
- **Empty pages**: LLM returns "STOP" action
- **Paywalls**: Relevance check filters them out
- **Non-existent dates**: Continue anyway, filter in dedup phase

---

## LLM Allocation Strategy

### Use GPT-4o for:
1. **Page analysis & decision** (complex reasoning)
2. **Content extraction** (varied structures: articles, forums, discussions)
3. **Link extraction with relevance ranking** (needs understanding)

### Use GPT-4o-mini for:
1. **Intent extraction** (structured, simple)
2. **Relevance validation** (yes/no decision)

**Why not Gemini/GPT-5 now?**
- GPT-4o is proven and sufficient
- System design > model choice
- Add model diversity only if specific failures emerge after testing

---

## Implementation Phases

### Phase 1: Core Navigation (Days 1-2)
**Goal**: Replace existing navigate + fetch nodes with recursive smart navigation

1. Create `smart_navigate()` function with 3 safety mechanisms:
   - Visited URL tracking
   - Depth limit
   - Article count limit

2. Implement `analyze_and_decide()` with gpt-4o:
   - Returns: `{action, reasoning, confidence, page_type, target_url?}`
   - Actions: `EXTRACT_CONTENT | EXTRACT_LINKS | NAVIGATE_TO | STOP`
   - Takes `available_links` as constraint

3. Update intent extractor to capture `target_section`:
   - "forum" → forum_page
   - "news" → news_listing
   - Empty → no preference

**Test**: Forum navigation scenario (Marico moneycontrol example)

### Phase 2: Generic Extraction (Day 3)
**Goal**: Replace `readability` with LLM-based extraction

1. Implement `extract_content()` with gpt-4o:
   - Handles articles, forum threads, discussions
   - Returns structured content with metadata

2. Implement `extract_relevant_links()` with gpt-4o:
   - Ranks by relevance score
   - Filters by time range if dates visible
   - Returns top 20 links

3. Implement `is_relevant()` with gpt-4o-mini:
   - Quick relevance check
   - Prevents garbage in summary

**Test**: Multiple content types (article, forum, news listing)

### Phase 3: URL Validation (Day 4)
**Goal**: Prevent LLM hallucinations

1. Implement `extract_all_links()` helper:
   - Returns all actual links from HTML
   - Makes URLs absolute
   - Normalizes them

2. Add validation in `smart_navigate()`:
   - Check target_url exists before navigating
   - Log warning if LLM hallucinated
   - Stop branch instead of following bad link

**Test**: Edge cases (malformed URLs, hallucinations)

### Phase 4: Integration & Testing (Day 5)
**Goal**: Wire into existing graph, end-to-end testing

1. Replace `_node_navigate()` and `_node_fetch()` with `smart_navigate()`
2. Test on 10+ scenarios:
   - Simple: Direct article links
   - Medium: News listing → Articles
   - Complex: Company profile → Forum → Threads → Posts
   - Edge: Paywalls, 404s, circular links

3. Monitor:
   - Success rate
   - Cost per query (LLM calls)
   - Time to complete
   - Decision quality

**Adjust prompts based on failures**

---

## Key Prompts

### Prompt 1: analyze_and_decide (gpt-4o)

```
You are a web navigation assistant helping extract content matching user intent.

USER INTENT:
- Topic: {intent.topic}
- Target section: {intent.target_section} (e.g., "forum", "news", or empty)
- Time range: {intent.time_range_days} days

CURRENT PAGE:
- URL: {url}
- Navigation depth: {depth}/3
- Title: {page_title}

AVAILABLE LINKS (you can ONLY choose from these):
{list of actual links with anchor text}

PAGE CONTENT (first 8000 chars):
{cleaned_html}

TASK: Decide what to do with this page.

OPTIONS:
1. EXTRACT_CONTENT - This page HAS the content (article, forum posts, discussion)
2. EXTRACT_LINKS - This page LISTS content (news listing, forum threads index)
3. NAVIGATE_TO - Navigate to a specific section (choose from AVAILABLE LINKS)
4. STOP - This page is irrelevant or dead-end

RULES:
- If target_section is "forum", prioritize forum/discussion/community sections
- A listing of threads is NOT content - go INTO threads
- Only choose URLs from AVAILABLE LINKS (no hallucinations)
- If unsure, prefer STOP over wrong action

OUTPUT (JSON only):
{
  "action": "EXTRACT_CONTENT|EXTRACT_LINKS|NAVIGATE_TO|STOP",
  "reasoning": "why you chose this",
  "confidence": 0.0-1.0,
  "page_type": "article|forum_thread|forum_listing|news_listing|company_profile|other",
  "target_url": "full URL from AVAILABLE LINKS (only if action=NAVIGATE_TO)"
}
```

### Prompt 2: extract_content (gpt-4o)

```
Extract main content from this page.

PAGE TYPE: {decision.page_type}
URL: {url}
USER WANTS: {intent.topic}

EXTRACTION RULES:
- If FORUM THREAD: Extract all posts with username, date, content
- If ARTICLE: Extract main text, date, author
- If DISCUSSION: Extract question + all responses

PAGE HTML (first 15000 chars):
{cleaned_html}

OUTPUT (JSON):
{
  "title": "...",
  "content": "extracted content in readable format",
  "publish_date": "YYYY-MM-DD or null",
  "metadata": {
    "post_count": N (if forum),
    "author": "..." (if article)
  }
}
```

### Prompt 3: extract_relevant_links (gpt-4o)

```
Extract links relevant to user intent.

USER WANTS: {intent.topic}
TARGET: {intent.target_section}
TIME RANGE: Last {intent.time_range_days} days

LINKS ON PAGE:
{list of links with anchor text}

Return ONLY relevant links, ranked by relevance.
Filter by date if visible in anchor text.
Max 20 links.

OUTPUT (JSON):
{
  "links": [
    {
      "url": "...",
      "anchor_text": "...",
      "relevance_score": 0.0-1.0,
      "detected_date": "YYYY-MM-DD or null"
    }
  ]
}
```

### Prompt 4: is_relevant (gpt-4o-mini)

```
Is this content relevant to user intent?

USER WANTS: {intent.topic}
TIME RANGE: Last {intent.time_range_days} days

CONTENT:
- Title: {content.title}
- Date: {content.publish_date}
- Preview: {content.content[:300]}

OUTPUT (JSON):
{
  "is_relevant": true/false,
  "reason": "brief explanation"
}
```

---

## Success Metrics

After implementation, measure:

1. **Functional**:
   - ✅ Forum scenario works (Marico moneycontrol)
   - ✅ Simple article links work (no regression)
   - ✅ No infinite loops observed
   - ✅ No wrong branches taken

2. **Performance**:
   - Average LLM calls per query: Target <15 calls
   - Average time to complete: Target <60 seconds
   - Cost per query: Target <$0.15

3. **Quality**:
   - Content extraction success rate: Target >90%
   - Relevance accuracy: Target >85%
   - Decision quality (manual review): Target >90%

---

## What We're NOT Doing (Avoiding Over-Engineering)

❌ **Complex confidence fallbacks** - Simple is better, just stop if low confidence
❌ **JS detection heuristics** - Use Bright Data's default, add render_js only if user reports issues
❌ **Multi-action decisions** - One action per decision, keep it simple
❌ **Extensive navigation trails** - Basic logging is enough, don't build debugging UI
❌ **Model diversity** - One model (GPT-4o) until we see specific failures
❌ **Dynamic depth adjustment** - Fixed max_depth=3 is sufficient
❌ **Link prioritization algorithms** - LLM handles ranking, don't add heuristics

**Philosophy**: Ship simple solution first. Add complexity only when real-world failures demand it.

---

## Rollout Plan

1. **Week 1**: Implement Phases 1-3, test internally
2. **Week 2**: Phase 4 integration, test on production data
3. **Week 3**: Monitor, collect failure cases, adjust prompts
4. **Week 4**: Consider model diversity / advanced features only if needed

---

## Implementation Status ✅

### Phase 1-3: COMPLETED

**New Modules Created:**

1. **`page_decision.py`** ✅
   - `analyze_and_decide()` - LLM-based page analysis with GPT-4o
   - `extract_all_links()` - Constrains LLM to real links only
   - `normalize_url()` - For cycle detection
   - URL validation to prevent hallucinations

2. **`content_extractor_llm.py`** ✅
   - `extract_content_with_llm()` - Generic extraction using GPT-4o
   - Works on articles, forums, discussions, any structure
   - `validate_relevance()` - Quick check using GPT-4o-mini

3. **`link_extractor_smart.py`** ✅
   - `extract_relevant_links_with_llm()` - Smart link ranking
   - Date detection from link text
   - Relevance scoring
   - Time-based filtering

4. **`smart_navigator.py`** ✅
   - `smart_navigate()` - Recursive navigation with safety mechanisms
   - Cycle detection (visited URL tracking)
   - Depth limit (max 3)
   - Article count limit
   - `run_smart_navigation()` - Entry point for multiple seeds

**Integration:** ✅

- Updated `intent.py` to include `target_section` field
- Updated `intent_extractor.py` to capture `target_section` from prompts
- Added `_node_smart_navigate_and_fetch()` to `graph.py`
- Modified `run_agent()` with `use_smart_navigation` flag (default: True)
- Backward compatible: Can toggle between smart and legacy navigation

**Safety Mechanisms Implemented:**

✅ Cycle Detection - Visited URL tracking with normalization  
✅ Depth Limit - Hard stop at depth=3  
✅ Article Count Limit - Stops when target reached  
✅ URL Validation - LLM can only choose from real links  
✅ Relevance Filtering - Content validated before adding  
✅ Intent-Aware Decisions - Every decision considers target_section  

### Phase 4: Testing

**Next Steps:**

1. Test forum navigation scenario (Marico moneycontrol)
2. Test simple article scenarios (regression check)
3. Monitor LLM costs and performance
4. Adjust prompts based on real-world behavior
5. Collect metrics on success rate

---

## Testing Checklist

### Scenario 1: Forum Navigation (Primary Test Case)
```bash
# Test the exact scenario that was failing before
Prompt: "Go to the forum page from the forum section and find out what people are saying about Marico in the last month"
Seed: https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13

Expected Flow:
1. Analyze seed page → NAVIGATE_TO (find forum link)
2. Analyze forum listing → EXTRACT_LINKS (get thread URLs)
3. Analyze threads → EXTRACT_CONTENT (get posts)
4. Validate relevance → Keep only relevant content
5. Return forum discussions as articles

Success Criteria:
- ✅ Navigates to forum section
- ✅ Extracts individual thread URLs
- ✅ Extracts post content (not "1 word")
- ✅ Returns multiple articles with forum discussions
```

### Scenario 2: Simple Article Links (Regression Test)
```bash
Prompt: "Summarize Marico news from last week"
Seed: https://www.moneycontrol.com/news/business/markets/

Expected Flow:
1. Analyze seed → EXTRACT_LINKS (article URLs visible)
2. Analyze articles → EXTRACT_CONTENT
3. Return articles

Success Criteria:
- ✅ Works as well as legacy system
- ✅ No regression in quality
```

### Scenario 3: Direct Article (Edge Case)
```bash
Prompt: "Summarize this article"
Seed: https://www.moneycontrol.com/news/business/article-url

Expected Flow:
1. Analyze seed → EXTRACT_CONTENT (already an article)
2. Return single article

Success Criteria:
- ✅ Recognizes it's already content
- ✅ Doesn't try to extract links
```

---

## Open Questions

1. Should we cache LLM decisions for identical pages? (Performance optimization)
2. Should we add a "preview mode" that shows navigation path before executing? (UX)
3. Should we expose navigation depth as user parameter? (Advanced users)

**Decision**: Address these only after core functionality is stable.

---

## How to Test

**Enable Smart Navigation (Default):**
```python
result = await run_agent(
    prompt="Go to forum and find discussions",
    seed_links=["https://moneycontrol.com/.../marico/M13"],
    max_articles=10,
    use_smart_navigation=True  # Default
)
```

**Fall Back to Legacy (If Issues):**
```python
result = await run_agent(
    prompt="Summarize news",
    seed_links=["https://example.com/news"],
    max_articles=10,
    use_smart_navigation=False  # Use old system
)
```

**Monitor Events:**
All navigation decisions are logged with events:
- `nav:decision` - Shows LLM's decision and reasoning
- `nav:extracting_content` - Content extraction in progress
- `nav:content_added` - Successfully added article
- `nav:stopped` - Hit a dead end or irrelevant page

