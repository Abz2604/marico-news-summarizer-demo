# AgentV2 Architecture

## Design Philosophy

**True Agentic Architecture:**
- Main agent is a lightweight orchestrator (minimal text, clear decisions)
- Tools do the heavy lifting (specialized, optimized)
- Sub-agents handle complex multi-step reasoning
- Data processors optimize input for LLM (readability, markdown, cleaning)

**User-Driven:**
- User specifies page type upfront (blog_listing, forum_thread, etc.)
- Agent selects appropriate tools based on page type
- Clear success/failure modes

**Optimized LLM Usage:**
- Clean, structured data only
- Minimal tokens
- Clear prompts
- No redundant information

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                    API Endpoint                          │
│              /api/agent-v2/run                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Main Agent (Orchestrator)                    │
│  - Understands user intent                               │
│  - Selects tools based on page type                       │
│  - Coordinates execution                                  │
│  - Minimal text, clear decisions                         │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐         ┌──────────────┐
│    Tools     │         │  Sub-Agents  │
│              │         │              │
│ - WebFetcher │         │ - Link       │
│ - LinkExtr   │         │   Analyzer   │
│ - ContentExt │         │ - Content    │
│ - DateFilter │         │   Validator  │
│ - TopicFilter│         │              │
└──────┬───────┘         └──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│            Data Processors                               │
│  - HTML Cleaner (readability, markdown)                  │
│  - Content Optimizer                                     │
│  - Structure Preserver                                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│            AI Factory (Azure OpenAI)                     │
│  - Centralized API routing                               │
│  - Model selection (gpt-4o, gpt-4o-mini)                │
│  - Configuration management                              │
└─────────────────────────────────────────────────────────┘
```

## Component Details

### 1. AI Factory (`ai_factory.py`)
- Single source of truth for all AI API calls
- Azure OpenAI integration
- Model selection (smart vs fast)
- Configuration from environment

### 2. Data Processors (`data_processors/`)
- `html_cleaner.py`: Removes noise, preserves structure
- `readability.py`: Extracts main content using readability
- `markdown_converter.py`: Converts HTML to clean markdown
- `content_optimizer.py`: Optimizes content for LLM (token reduction)

### 3. Tools (`tools/`)
- `web_fetcher.py`: Bright Data integration for fetching
- `link_extractor.py`: Extract links from listing pages
- `content_extractor.py`: Extract content from individual pages
- `date_filter.py`: Filter by date range
- `topic_filter.py`: Filter by topic relevance

### 4. Sub-Agents (`agents/`)
- `link_analyzer.py`: Complex link analysis (when simple extraction isn't enough)
- `content_validator.py`: Validate content quality and relevance

### 5. Main Agent (`agent_v2.py`)
- Lightweight orchestrator
- Tool selection based on page type
- Execution coordination
- Result aggregation

## Page Types

### Current:
- `blog_listing`: Blog/news listing pages with article links
- `forum_thread`: Forum thread pages with posts

### Future (to be added):
- `press_releases`: Press release listings
- `product_pages`: Product listing pages
- `research_reports`: Research report listings

## Flow Example: Blog Listing

```
User Input:
  - URL: https://example.com/news
  - Prompt: "Articles about AI in last week"
  - Page Type: blog_listing

Main Agent:
  1. Understand intent: AI articles, last 7 days
  2. Select tools: WebFetcher → LinkExtractor → DateFilter → ContentExtractor
  3. Execute:
     a. Fetch page (Bright Data)
     b. Clean HTML (Data Processor)
     c. Extract links (LinkExtractor tool)
     d. Filter by date (DateFilter tool)
     e. Filter by topic (TopicFilter tool)
     f. Fetch articles (WebFetcher tool)
     g. Extract content (ContentExtractor tool)
  4. Aggregate results
  5. Return to user
```

## Benefits

1. **Reliability**: Specialized tools = higher success rate
2. **Efficiency**: Fewer LLM calls, optimized data
3. **Maintainability**: Clear separation of concerns
4. **Extensibility**: Easy to add new page types and tools
5. **Predictability**: Known behavior for known patterns

