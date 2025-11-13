# AgentV2 Implementation Summary

## What Was Built

A complete, clean AgentV2 architecture from scratch with:

### 1. Core Architecture
- **AI Factory** (`api/agent_v2/ai_factory.py`): Centralized Azure OpenAI routing
- **Data Processors** (`api/agent_v2/data_processors/`): HTML cleaning and optimization
- **Tools** (`api/agent_v2/tools/`): Specialized functions (WebFetcher, LinkExtractor, ContentExtractor)
- **Main Agent** (`api/agent_v2/agent_v2.py`): Lightweight orchestrator
- **Types** (`api/agent_v2/types.py`): Type definitions

### 2. API Endpoint
- **Router** (`api/routers/agent_v2.py`): New `/api/agent-v2/run` endpoint
- **Page Types Endpoint**: `/api/agent-v2/page-types` to list available types
- **Integrated** into main FastAPI app

### 3. Features
- User specifies page type upfront (blog_listing, forum_thread)
- Tool-based architecture (specialized tools, not overthinking)
- Optimized LLM usage (clean data, minimal tokens)
- Bright Data integration (web unlocking)
- Azure OpenAI with factory pattern

## File Structure

```
api/agent_v2/
├── __init__.py
├── ARCHITECTURE.md          # Architecture documentation
├── README.md                # Usage guide
├── ai_factory.py            # Centralized AI API routing
├── agent_v2.py              # Main orchestrator
├── types.py                 # Type definitions
├── data_processors/
│   ├── __init__.py
│   └── html_cleaner.py      # HTML cleaning and optimization
└── tools/
    ├── __init__.py
    ├── web_fetcher.py       # Bright Data integration
    ├── link_extractor.py    # LLM-powered link extraction
    └── content_extractor.py # LLM-powered content extraction

api/routers/
└── agent_v2.py              # API endpoint
```

## Key Design Decisions

### 1. Tool-Based Architecture
- Main agent is lightweight (just orchestrates)
- Tools do the heavy lifting (specialized, optimized)
- No overthinking or complex decision trees

### 2. User-Driven Page Types
- User specifies page type upfront
- Agent routes to appropriate handler
- Clear, predictable behavior

### 3. Optimized LLM Usage
- HTML cleaned before sending to LLM
- Structure preserved (headings, lists, paragraphs)
- Minimal tokens, clear prompts

### 4. Centralized AI Factory
- Single source of truth for all AI calls
- Azure OpenAI with OpenAI fallback
- Easy to configure and maintain

## Current Page Types

1. **blog_listing**: Blog/news listing pages
   - Extracts article links
   - Filters by date/topic
   - Fetches and extracts article content

2. **forum_thread**: Forum thread pages
   - Extracts all posts from thread
   - Preserves chronological order
   - Includes usernames and dates

## API Usage

### Run AgentV2

```bash
POST /api/agent-v2/run
Content-Type: application/json

{
  "url": "https://example.com/news",
  "prompt": "Articles about AI in last week",
  "page_type": "blog_listing",
  "max_items": 10,
  "time_range_days": 7
}
```

### Get Page Types

```bash
GET /api/agent-v2/page-types
```

## Next Steps

### Immediate
1. Test with real URLs (blog listings and forum threads)
2. Add error handling and retries
3. Add logging and monitoring

### Short Term
1. Add more page types (press_releases, product_pages)
2. Integrate readability library for better content extraction
3. Add markdown conversion for cleaner output
4. Explore other Bright Data APIs (SERP, etc.)

### Long Term
1. Add sub-agents for complex multi-step reasoning
2. Add caching layer for fetched content
3. Add rate limiting and cost tracking
4. Add streaming responses for long-running tasks

## Differences from AgentV1

| Aspect | AgentV1 | AgentV2 |
|--------|---------|---------|
| Architecture | Complex decision tree | Tool-based, clean |
| Page Type | Auto-detected (unreliable) | User-specified (reliable) |
| LLM Usage | Multiple calls, overthinking | Optimized, focused |
| Maintainability | Hard to extend | Easy to extend |
| Predictability | Unpredictable | Predictable |

## Testing

To test AgentV2:

```python
from agent_v2 import AgentV2, AgentV2Request, PageType

agent = AgentV2()
request = AgentV2Request(
    url="https://example.com/news",
    prompt="Articles about AI",
    page_type=PageType.BLOG_LISTING,
    max_items=10,
    time_range_days=7
)

response = await agent.run(request)
print(f"Extracted {len(response.items)} items")
```

## Configuration

Required environment variables:
- `AZURE_OPENAI_KEY`: Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Azure endpoint
- `AZURE_OPENAI_API_VERSION`: API version
- `BRIGHTDATA_API_KEY`: Bright Data API key
- `BRIGHTDATA_ZONE`: Bright Data zone name

## Notes

- AgentV2 is completely separate from AgentV1 (no interference)
- Can be used alongside AgentV1 (toggle in UI)
- Built for extensibility (easy to add new page types)
- Optimized for reliability and efficiency

