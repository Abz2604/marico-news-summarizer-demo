# AgentV2 - True Agentic Architecture

## Overview

AgentV2 is a clean, tool-based agent system designed for reliability and efficiency. It replaces the complex, rigid AgentV1 with a truly agentic architecture.

## Key Features

- **Tool-Based Architecture**: Specialized tools do the work, main agent orchestrates
- **User-Driven**: User specifies page type upfront (blog_listing, forum_thread, etc.)
- **Optimized LLM Usage**: Clean data, minimal tokens, clear prompts
- **Centralized AI Factory**: Single source of truth for all AI API calls (Azure OpenAI)
- **Bright Data Integration**: Professional web fetching with anti-bot bypass

## Architecture

```
Main Agent (Orchestrator)
    ↓
Tools (Specialized Functions)
    ↓
Data Processors (HTML Cleaning, Optimization)
    ↓
AI Factory (Azure OpenAI)
```

## Page Types

Currently supported:
- `blog_listing`: Blog/news listing pages with article links
- `forum_thread`: Forum thread pages with posts

More types can be added incrementally.

## Usage

### API Endpoint

```bash
POST /api/agent-v2/run
```

### Request

```json
{
  "url": "https://example.com/news",
  "prompt": "Articles about AI in last week",
  "page_type": "blog_listing",
  "max_items": 10,
  "time_range_days": 7
}
```

### Response

```json
{
  "items": [
    {
      "url": "https://example.com/article/123",
      "title": "Article Title",
      "content": "Full article content...",
      "publish_date": "2024-11-15T00:00:00",
      "content_type": "article",
      "metadata": {
        "word_count": 500,
        "has_quotes": true
      }
    }
  ],
  "summary": null,
  "metadata": {
    "total_links_found": 15,
    "articles_extracted": 10,
    "page_type": "blog_listing"
  }
}
```

### Get Available Page Types

```bash
GET /api/agent-v2/page-types
```

## Components

### 1. AI Factory (`ai_factory.py`)
- Centralized AI API routing
- Azure OpenAI integration with OpenAI fallback
- Model selection (gpt-4o for complex, gpt-4o-mini for simple)

### 2. Data Processors (`data_processors/`)
- `html_cleaner.py`: Removes noise, preserves structure
- Optimizes content for LLM (token reduction)

### 3. Tools (`tools/`)
- `web_fetcher.py`: Bright Data integration for fetching
- `link_extractor.py`: Extract links from listing pages (LLM-powered)
- `content_extractor.py`: Extract content from individual pages (LLM-powered)

### 4. Main Agent (`agent_v2.py`)
- Lightweight orchestrator
- Routes to appropriate handler based on page type
- Coordinates tool execution

## Flow Example: Blog Listing

1. User requests: "Articles about AI in last week" from blog listing page
2. Main Agent: Routes to `_handle_blog_listing()`
3. Tools execute:
   - `fetch_page()`: Fetch listing page (Bright Data)
   - `extract_links()`: Extract article links (LLM filters by topic/date)
   - `fetch_page()`: Fetch each article
   - `extract_content()`: Extract article content (LLM)
4. Results aggregated and returned

## Benefits Over AgentV1

1. **Reliability**: Specialized tools = higher success rate
2. **Efficiency**: Fewer LLM calls, optimized data
3. **Maintainability**: Clear separation of concerns
4. **Extensibility**: Easy to add new page types and tools
5. **Predictability**: Known behavior for known patterns

## Adding New Page Types

1. Add enum value to `PageType` in `types.py`
2. Add handler method in `agent_v2.py` (e.g., `_handle_press_releases()`)
3. Update router description in `agent_v2.py`
4. Test with real URLs

## Configuration

Requires:
- `AZURE_OPENAI_KEY`: Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Azure endpoint (default: https://milazdalle.openai.azure.com/)
- `AZURE_OPENAI_API_VERSION`: API version (default: 2024-12-01-preview)
- `BRIGHTDATA_API_KEY`: Bright Data API key
- `BRIGHTDATA_ZONE`: Bright Data zone name

## Future Enhancements

- Add more page types (press_releases, product_pages, etc.)
- Add sub-agents for complex multi-step reasoning
- Add readability library integration for better content extraction
- Add markdown conversion for cleaner output
- Explore other Bright Data APIs (e.g., SERP API for search)

