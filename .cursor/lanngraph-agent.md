# LangGraph Agent Requirements

## Overview

Build AgentV2 using LangGraph with a focus on LLM intelligence and system prompts. The agent should be goal-oriented, tool-based, and extensible.

## Core Requirements

### 1. Agent Loop Pattern
- Agent loops until goal is reached or abort conditions are met
- Goal: Extract and summarize content based on user prompt
- Abort conditions:
  - Max iterations reached (20)
  - Consecutive failures > 5
  - No progress for 10 iterations
  - No links found after trying

### 2. State Management
- Use TypedDict for state schema
- State should include:
  - Goal (target_items, topic, time_range_days, quality_threshold)
  - Seed URL and user prompt
  - Extracted items (articles/content)
  - Links found
  - Listing HTML (if fetched)
  - Current iteration
  - Quality score
  - Error state
  - History of actions

### 3. Graph Structure
- Simple graph with conditional edges for agent loop
- Nodes:
  - `fetch_listing`: Fetch the seed URL
  - `extract_links`: Extract article links from listing
  - `fetch_article`: Fetch and extract individual article
  - `check_goal`: Evaluate if goal is reached
  - `summarize`: Create final summary
- Conditional routing:
  - After `check_goal`: continue → fetch_article, done → summarize, abort → END

### 4. LLM Intelligence
- Use LLM for decision-making (not just rule-based)
- System prompt should guide agent behavior
- Mini models (gpt-4o-mini) for:
  - Date parsing
  - Topic filtering
  - Relevance checking
- Smart model (gpt-4o) for:
  - Goal evaluation
  - Summarization
  - Complex decision-making

### 5. Tool Integration
- Tools should be callable from nodes
- Current tools:
  - `web_fetcher`: Fetch pages (Bright Data)
  - `link_extractor`: Extract links (BS4 + LLM)
  - `content_extractor`: Extract content (readability + LLM)
- Tools can be algorithmic or LLM-based
- Agent decides which tool to use

### 6. Error Handling
- Graceful degradation
- Continue on tool failures (try next)
- Log errors in state
- Abort if too many failures

### 7. Extensibility
- Easy to add new tools
- Easy to add new nodes
- Easy to modify routing logic
- Foundation for future tools (email, calendar, etc.)

## Technical Requirements

### Dependencies
- `langgraph>=0.2`
- `langchain-core`
- Azure OpenAI (via ai_factory)

### State Schema
```python
class AgentState(TypedDict):
    goal: dict
    seed_url: str
    prompt: str
    extracted_items: list
    links_found: list
    listing_html: Optional[str]
    current_link_index: int
    iteration: int
    quality_score: float
    error: Optional[str]
    should_abort: bool
    history: list
```

### Graph Flow
```
START
  ↓
fetch_listing
  ↓
extract_links
  ↓
check_goal ──(conditional)──┐
  ↓                         │
fetch_article                │
  ↓                         │
check_goal ─────────────────┘
  ↓
summarize
  ↓
END
```

### Decision Points
1. After `extract_links`: Do we have links? (yes → continue, no → abort)
2. After `check_goal`: Goal reached? (continue → fetch_article, done → summarize, abort → END)

## Success Criteria

1. Agent successfully extracts articles from blog listing
2. Agent loops until goal is reached (target_items)
3. Agent aborts gracefully when conditions are met
4. Agent creates summary based on user prompt
5. State is maintained throughout execution
6. Tools are properly integrated
7. LLM intelligence guides decisions

## Future Enhancements (Out of Scope for MVP)

- Checkpointing (state persistence)
- Human-in-the-loop (interrupts)
- Tool nodes (LangGraph ToolNode)
- More complex routing (multiple decision points)
- Learning/adaptation (remember what works)
- Visualization (graph visualization)

## Implementation Notes

- Start simple: Basic graph with one conditional edge
- Rely on LLM intelligence for decision-making
- Use system prompts to guide agent behavior
- Keep tools separate from graph (call from nodes)
- Focus on blog listing use case first
- Make it extensible for future tools
