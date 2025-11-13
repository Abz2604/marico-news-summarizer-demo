# AgentV2 Potential Pitfalls & Issues

## Critical Issues

### 1. **No Error Recovery / Retry Logic**
**Problem**: If a tool fails, we just return empty results. No retries, no fallbacks.

**Examples**:
- Bright Data fetch fails → returns empty list
- LLM returns invalid JSON → returns empty list
- Network timeout → returns empty list

**Impact**: High failure rate, poor user experience

**Fix Needed**:
- Add retry logic for network operations
- Add fallback strategies (e.g., if LLM fails, try simpler extraction)
- Better error messages to user

---

### 2. **Sequential Article Fetching (Very Slow)**
**Problem**: In `_handle_blog_listing()`, we fetch articles one by one in a loop.

```python
for link in links[:request.max_items]:
    article_html = await fetch_page(...)  # Sequential!
    content = await extract_content(...)
```

**Impact**: 
- If fetching 10 articles, each takes 2-5 seconds = 20-50 seconds total
- User waits a long time
- No progress feedback

**Fix Needed**:
- Use `asyncio.gather()` for concurrent fetching
- Add rate limiting to avoid overwhelming Bright Data
- Add progress callbacks/SSE events

---

### 3. **No Rate Limiting / Cost Control**
**Problem**: 
- No limits on LLM calls
- No limits on Bright Data requests
- Could make 100+ LLM calls for a single request
- No cost tracking

**Impact**: 
- High costs
- Rate limit errors
- Service abuse

**Fix Needed**:
- Add rate limiting per request
- Track LLM token usage
- Add cost estimates
- Limit concurrent operations

---

### 4. **LLM JSON Parsing Failures**
**Problem**: If LLM returns invalid JSON, we catch exception and return empty list.

**Examples**:
- LLM adds extra text before/after JSON
- LLM uses single quotes instead of double quotes
- LLM returns malformed JSON structure
- LLM hallucinates URLs that don't exist in the list

**Impact**: Silent failures, lost content

**Fix Needed**:
- Better JSON parsing (try multiple strategies)
- Validate URLs exist in original list
- Add retry with different prompt if JSON fails
- Log the actual LLM response for debugging

---

### 5. **Date Parsing Edge Cases**
**Problem**: Date parsing is fragile.

**Issues**:
- Different date formats ("Nov 15, 2024" vs "2024-11-15" vs "15/11/2024")
- Relative dates ("2 days ago") not handled
- Timezone issues
- Date in link context might be wrong (e.g., "last updated" vs "published")

**Impact**: Wrong articles filtered out, or old articles included

**Fix Needed**:
- Use robust date parser (dateutil)
- Handle relative dates
- Validate dates make sense (not in future)
- Prefer structured data (meta tags) over text parsing

---

### 6. **No Validation of Extracted URLs**
**Problem**: LLM might hallucinate URLs or return URLs not in the original list.

**Example**:
```python
# LLM might return:
{"url": "https://example.com/article/999"}  # But this wasn't in the link list!
```

**Impact**: 404 errors, wasted fetches

**Fix Needed**:
- Validate URLs exist in original link list
- Normalize URLs before comparison
- Log mismatches for debugging

---

### 7. **HTML Cleaning Might Remove Important Content**
**Problem**: `clean_html_for_llm()` might be too aggressive.

**Issues**:
- Removes too much (e.g., removes article content thinking it's navigation)
- Forum posts might be removed if they look like navigation
- Important metadata (dates, authors) might be lost

**Impact**: Missing content, poor extraction quality

**Fix Needed**:
- Test with real pages
- Add preserve patterns (e.g., preserve article tags, main content)
- Make cleaning configurable per page type

---

### 8. **No Handling of Lazy-Loaded Content**
**Problem**: Many sites use lazy loading. We fetch once with `render_js=False`.

**Example**: 
- Reuters shows 5 articles initially
- Need to scroll/click "Load More" to see more
- We only get 5 articles

**Impact**: Missing most content on modern sites

**Fix Needed**:
- Detect lazy loading (check for "Load More" buttons, low link count)
- Re-fetch with `render_js=True` if needed
- Wait for content to load

---

### 9. **No Deduplication**
**Problem**: Same article might appear multiple times.

**Examples**:
- Same article linked from different sections
- URL variations (with/without trailing slash, query params)
- Canonical URLs not checked

**Impact**: Duplicate content, wasted processing

**Fix Needed**:
- Normalize URLs (remove query params, trailing slashes)
- Check canonical URLs
- Deduplicate by content similarity

---

### 10. **Token Limits Not Handled**
**Problem**: Large HTML pages might exceed token limits.

**Issues**:
- 20KB HTML → cleaned to 15KB → still might be too much
- LLM has context limits (128K for gpt-4o, but we should be conservative)
- Multiple large pages in one request

**Impact**: Truncated content, failed extractions

**Fix Needed**:
- Track token usage
- Truncate intelligently (at sentence/paragraph boundaries)
- Split large content into chunks if needed

---

## Medium Priority Issues

### 11. **No Timeout Handling**
**Problem**: Operations can hang indefinitely.

**Issues**:
- Bright Data fetch might hang
- LLM call might hang
- No overall request timeout

**Impact**: Hung requests, resource exhaustion

**Fix Needed**:
- Add timeouts to all async operations
- Add overall request timeout
- Cancel operations that exceed timeout

---

### 12. **No Caching**
**Problem**: Same URL fetched multiple times.

**Examples**:
- User runs same request twice
- Different users request same URL
- No caching of fetched content or extracted links

**Impact**: Wasted API calls, slower responses

**Fix Needed**:
- Add Redis/file cache for fetched HTML
- Cache extracted links
- Cache extracted content
- TTL based on content type (articles = longer, listings = shorter)

---

### 13. **No Progress Feedback**
**Problem**: User has no idea what's happening.

**Issues**:
- Long-running requests (30+ seconds)
- No progress updates
- No way to cancel

**Impact**: Poor UX, users think it's broken

**Fix Needed**:
- Add SSE (Server-Sent Events) for progress
- Emit events: "Fetching page...", "Extracting links...", "Found 5 links...", etc.
- Add cancellation support

---

### 14. **Topic Filtering Might Be Too Strict/Loose**
**Problem**: LLM relevance scoring is subjective.

**Issues**:
- Might filter out relevant articles (false negatives)
- Might include irrelevant articles (false positives)
- No way to tune sensitivity

**Impact**: Missing content or too much noise

**Fix Needed**:
- Add relevance threshold parameter
- Allow user to adjust sensitivity
- Log relevance scores for debugging

---

### 15. **No Handling of Paywalls**
**Problem**: Some articles might be behind paywalls.

**Issues**:
- Bright Data might get paywall page
- Content extractor might extract paywall message
- No detection of paywall content

**Impact**: Wasted processing, poor content quality

**Fix Needed**:
- Detect paywall indicators ("Subscribe", "Sign in to read", etc.)
- Skip paywalled content
- Log paywall detection

---

## Low Priority Issues

### 16. **No Logging/Monitoring**
**Problem**: Hard to debug issues in production.

**Issues**:
- No structured logging
- No metrics (success rate, latency, cost)
- No error tracking

**Fix Needed**:
- Add structured logging (JSON)
- Add metrics (Prometheus/Datadog)
- Add error tracking (Sentry)

---

### 17. **No Input Validation**
**Problem**: Malformed requests can cause errors.

**Issues**:
- Invalid URLs
- Empty prompts
- Negative time ranges

**Fix Needed**:
- Validate all inputs
- Return clear error messages
- Use Pydantic for validation

---

### 18. **No Handling of Redirects**
**Problem**: URLs might redirect.

**Issues**:
- HTTP → HTTPS redirects
- URL shorteners
- Canonical URLs

**Impact**: Might fetch wrong page or fail

**Fix Needed**:
- Follow redirects (Bright Data should handle this, but verify)
- Normalize final URLs

---

### 19. **No Handling of Pagination**
**Problem**: Listing pages might have pagination.

**Issues**:
- "Next page" links not followed
- Only get first page of results

**Impact**: Missing content

**Fix Needed**:
- Detect pagination
- Optionally fetch multiple pages
- Add `max_pages` parameter

---

### 20. **No Handling of Different Languages**
**Problem**: Content might be in different languages.

**Issues**:
- Date formats differ by locale
- Content extraction might fail on non-English
- Topic matching might not work

**Impact**: Poor results for international sites

**Fix Needed**:
- Detect language
- Use language-specific date parsers
- Consider language in topic matching

---

## Architecture Issues

### 21. **No Sub-Agents for Complex Cases**
**Problem**: Some cases need multi-step reasoning.

**Examples**:
- Need to navigate through multiple pages
- Need to handle complex site structures
- Need to combine information from multiple sources

**Impact**: Can't handle complex use cases

**Fix Needed**:
- Add sub-agents for complex reasoning
- Allow agents to call other agents
- Add planning phase for complex requests

---

### 22. **No Tool Chaining**
**Problem**: Tools are isolated, can't build on each other.

**Example**:
- Can't use extracted links to inform content extraction
- Can't use date from link to validate content date

**Impact**: Less efficient, redundant processing

**Fix Needed**:
- Allow tools to pass context to each other
- Cache intermediate results
- Build tool chains

---

## Recommendations

### Must Fix Before Production:
1. ✅ Add retry logic and error recovery
2. ✅ Add concurrent fetching (with rate limiting)
3. ✅ Add rate limiting and cost control
4. ✅ Improve JSON parsing robustness
5. ✅ Add URL validation
6. ✅ Add timeout handling
7. ✅ Add progress feedback (SSE)

### Should Fix Soon:
8. ✅ Improve date parsing
9. ✅ Add deduplication
10. ✅ Handle lazy-loaded content
11. ✅ Add caching
12. ✅ Detect paywalls

### Nice to Have:
13. ✅ Add monitoring/logging
14. ✅ Handle pagination
15. ✅ Add sub-agents for complex cases

