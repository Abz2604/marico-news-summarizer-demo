# UX Improvement Plan

## 🎯 Objectives

1. **Real-time Progress Updates**: Show agent's current step/action instead of generic loader
2. **Rich Output Display**: Support varied output formats (executive summary, detailed, etc.)
3. **Better Information Architecture**: Display dates, confidence scores, and metadata
4. **Progressive Enhancement**: Maintain backward compatibility

---

## 📊 Current State Analysis

### Backend
- Agent emits events via `_emit()` but frontend doesn't see them
- Single endpoint `/api/agent/run` returns complete result at end
- No streaming capability

### Frontend
- Simple loader with bouncing dots
- Basic bullet list display
- No differentiation between output formats
- No metadata display (dates, confidence)

---

## 🔧 Implementation Plan

### **Phase 1: Backend - SSE Streaming** (Priority: HIGH)

#### 1.1 Create SSE Endpoint
**File:** `api/routers/agent.py`

```python
from fastapi.responses import StreamingResponse
import asyncio
import json

@router.post("/run/stream")
async def run_agent_stream(payload: AgentRunRequest):
    """
    Stream agent progress in real-time using Server-Sent Events (SSE)
    """
    
    async def event_generator():
        # Store events in a queue
        event_queue = asyncio.Queue()
        
        # Override _emit to push to queue
        original_emit = graph._emit
        
        def custom_emit(state, event_data):
            event_queue.put_nowait(event_data)
            original_emit(state, event_data)
        
        # Monkey patch temporarily
        graph._emit = custom_emit
        
        # Run agent in background task
        async def run_in_background():
            try:
                result = await run_agent(...)
                await event_queue.put({"event": "complete", "data": result})
            except Exception as e:
                await event_queue.put({"event": "error", "error": str(e)})
            finally:
                await event_queue.put(None)  # Sentinel
        
        task = asyncio.create_task(run_in_background())
        
        # Stream events
        while True:
            event = await event_queue.get()
            if event is None:
                break
            
            yield f"data: {json.dumps(event)}\n\n"
        
        # Restore original emit
        graph._emit = original_emit
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

**Event Types to Stream:**
- `init` - Agent starting
- `nav:context_extracted` - Found company/topic
- `nav:analyzing` - Analyzing page
- `nav:extracting_links` - Finding articles
- `fetch:start` - Fetching article
- `date:extracted` - Got publish date
- `quality:validated` - Content quality check
- `dedup:start` - Deduplicating
- `summarize:start` - Generating summary
- `complete` - Final result ready

#### 1.2 Modify `_emit()` Function
**File:** `api/agent/graph.py`

Make `_emit()` return events to caller instead of just logging:

```python
# Add to run_agent()
async def run_agent(prompt, seed_links, max_articles, event_callback=None):
    # ...
    
    def _emit_with_callback(state, data):
        _emit(state, data)  # Original logging
        if event_callback:
            event_callback(data)  # Send to SSE stream
```

---

### **Phase 2: Frontend - Progress Display** (Priority: HIGH)

#### 2.1 Create Progress Component
**File:** `components/agent-progress.tsx`

```typescript
interface AgentProgressProps {
  currentStep: string
  progress: number  // 0-100
  details?: string
}

export function AgentProgress({ currentStep, progress, details }: AgentProgressProps) {
  const stepIcons = {
    init: "🚀",
    analyzing: "🔍",
    fetching: "📡",
    validating: "✅",
    summarizing: "📝",
    complete: "🎉"
  }
  
  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="w-full bg-muted rounded-full h-2">
        <div 
          className="bg-primary h-2 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      
      {/* Current step */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">{stepIcons[currentStep]}</span>
        <div>
          <p className="font-medium">{currentStep}</p>
          {details && <p className="text-sm text-muted-foreground">{details}</p>}
        </div>
      </div>
    </div>
  )
}
```

#### 2.2 Create Step Timeline Component
**File:** `components/agent-timeline.tsx`

```typescript
interface TimelineStep {
  name: string
  status: 'pending' | 'active' | 'complete'
  timestamp?: string
  details?: string
}

export function AgentTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <div className="space-y-2">
      {steps.map((step, i) => (
        <div key={i} className="flex items-start gap-3">
          {/* Status indicator */}
          <div className={`
            w-3 h-3 rounded-full mt-1
            ${step.status === 'complete' && 'bg-green-500'}
            ${step.status === 'active' && 'bg-blue-500 animate-pulse'}
            ${step.status === 'pending' && 'bg-gray-300'}
          `} />
          
          {/* Step info */}
          <div className="flex-1">
            <p className="text-sm font-medium">{step.name}</p>
            {step.details && (
              <p className="text-xs text-muted-foreground">{step.details}</p>
            )}
            {step.timestamp && (
              <p className="text-xs text-muted-foreground">{step.timestamp}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
```

#### 2.3 Update DemoSummary Component
**File:** `components/demo-summary.tsx`

Add SSE connection:

```typescript
useEffect(() => {
  if (!briefingData) return
  
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
  const eventSource = new EventSource(
    `${API_BASE}/api/agent/run/stream?prompt=${encodeURIComponent(briefingData.prompt)}`
  )
  
  const timeline: TimelineStep[] = []
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    // Update progress based on event
    switch (data.event) {
      case 'init':
        setProgress(5)
        addTimelineStep('Starting agent', 'active')
        break
      case 'nav:analyzing':
        setProgress(20)
        addTimelineStep('Analyzing page', 'active')
        break
      case 'fetch:start':
        setProgress(40)
        addTimelineStep(`Fetching: ${data.url}`, 'active')
        break
      case 'summarize:start':
        setProgress(80)
        addTimelineStep('Generating summary', 'active')
        break
      case 'complete':
        setProgress(100)
        setResult(data.data)
        addTimelineStep('Complete', 'complete')
        eventSource.close()
        break
    }
  }
  
  return () => eventSource.close()
}, [briefingData])
```

---

### **Phase 3: Rich Output Display** (Priority: MEDIUM)

#### 3.1 Create Format-Aware Display Components

**File:** `components/summary-display/executive-summary.tsx`
```typescript
export function ExecutiveSummaryDisplay({ content, sources }) {
  return (
    <Card>
      <CardHeader>
        <Badge variant="secondary">Executive Summary</Badge>
        <CardTitle>High-Level Overview</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="prose prose-sm">
          <p className="text-lg leading-relaxed">{content}</p>
        </div>
        <SourcesList sources={sources} />
      </CardContent>
    </Card>
  )
}
```

**File:** `components/summary-display/bullet-list.tsx`
```typescript
export function BulletListDisplay({ bullets, categories, sources }) {
  return (
    <Card>
      <CardHeader>
        <Badge variant="secondary">Detailed Analysis</Badge>
        <CardTitle>Key Insights</CardTitle>
      </CardHeader>
      <CardContent>
        {Object.entries(categories).map(([category, categoryBullets]) => (
          <div key={category} className="mb-6">
            <h3 className="font-semibold text-lg mb-3">{category}</h3>
            <ul className="space-y-2">
              {categoryBullets.map((bullet, i) => (
                <li key={i} className="flex gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-primary">•</span>
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <SourcesList sources={sources} />
      </CardContent>
    </Card>
  )
}
```

#### 3.2 Enhanced Sources Display
**File:** `components/summary-display/sources-list.tsx`

```typescript
interface Source {
  url: string
  title: string
  date?: string
  age_days?: number
  date_confidence?: number
}

export function SourcesList({ sources }: { sources: Source[] }) {
  return (
    <div className="pt-4 border-t">
      <p className="text-xs font-semibold text-muted-foreground mb-3">
        SOURCES ({sources.length})
      </p>
      <div className="space-y-2">
        {sources.map((source, i) => (
          <a 
            key={i}
            href={source.url}
            target="_blank"
            className="flex items-center justify-between p-3 hover:bg-muted rounded-lg group"
          >
            <div className="flex-1">
              <p className="text-sm font-medium">{source.title}</p>
              <div className="flex gap-2 items-center mt-1">
                {source.date && (
                  <Badge variant="outline" className="text-xs">
                    📅 {source.date}
                  </Badge>
                )}
                {source.age_days !== undefined && (
                  <span className="text-xs text-muted-foreground">
                    ({source.age_days} days ago)
                  </span>
                )}
              </div>
            </div>
            <ExternalLink className="w-4 h-4" />
          </a>
        ))}
      </div>
    </div>
  )
}
```

---

### **Phase 4: Smart Layout Selection** (Priority: MEDIUM)

#### 4.1 Auto-detect Output Format
**File:** `components/demo-summary.tsx`

```typescript
// Detect format from intent or result structure
const detectFormat = (result: AgentSummaryResponse, intent?: UserIntent) => {
  if (intent?.output_format === 'executive_summary') {
    return 'executive'
  }
  
  if (result.bullet_points.length <= 5 && result.bullet_points.length > 0) {
    return 'concise'
  }
  
  if (result.summary_markdown.includes('##')) {
    return 'categorized'
  }
  
  return 'bullets'
}

// Render appropriate component
const renderSummary = () => {
  const format = detectFormat(result, intent)
  
  switch (format) {
    case 'executive':
      return <ExecutiveSummaryDisplay {...} />
    case 'categorized':
      return <CategorizedBulletDisplay {...} />
    case 'concise':
      return <ConciseDisplay {...} />
    default:
      return <BulletListDisplay {...} />
  }
}
```

---

### **Phase 5: Quality Indicators** (Priority: LOW)

#### 5.1 Add Confidence Badges
```typescript
<Badge variant={
  confidence > 0.8 ? 'default' : 
  confidence > 0.6 ? 'secondary' : 
  'outline'
}>
  {confidence > 0.8 ? '✓ High Confidence' : 
   confidence > 0.6 ? '~ Medium Confidence' : 
   '? Low Confidence'}
</Badge>
```

#### 5.2 Show Extraction Method
```typescript
{source.date_extraction_method === 'llm' && (
  <Tooltip>
    <TooltipTrigger>
      <Badge variant="outline" className="text-xs">
        🤖 AI-extracted
      </Badge>
    </TooltipTrigger>
    <TooltipContent>
      Date extracted using AI analysis
    </TooltipContent>
  </Tooltip>
)}
```

---

## 🗂️ File Structure

```
api/
├── routers/
│   └── agent.py                 # Add /run/stream endpoint
components/
├── agent-progress.tsx           # NEW: Progress indicator
├── agent-timeline.tsx           # NEW: Step timeline
├── demo-summary.tsx             # UPDATE: Add SSE support
└── summary-display/             # NEW FOLDER
    ├── executive-summary.tsx    # Executive format
    ├── bullet-list.tsx           # Bullet format
    ├── categorized-display.tsx   # Categorized format
    └── sources-list.tsx          # Enhanced sources
```

---

## 📋 Implementation Checklist

### Backend (SSE)
- [ ] Create `/api/agent/run/stream` endpoint
- [ ] Modify `_emit()` to support callbacks
- [ ] Test SSE connection with curl/Postman
- [ ] Add error handling for SSE disconnection
- [ ] Add keep-alive pings (every 30s)

### Frontend (Progress)
- [ ] Create `AgentProgress` component
- [ ] Create `AgentTimeline` component
- [ ] Update `DemoSummary` to connect to SSE
- [ ] Map events to progress percentage
- [ ] Add reconnection logic

### Frontend (Rich Display)
- [ ] Create `ExecutiveSummaryDisplay` component
- [ ] Create `CategorizedBulletDisplay` component
- [ ] Create enhanced `SourcesList` component
- [ ] Add format auto-detection
- [ ] Add smooth transitions between states

### Polish
- [ ] Add loading skeletons
- [ ] Add error states with retry
- [ ] Add animations/transitions
- [ ] Mobile responsiveness
- [ ] Accessibility (ARIA labels)

---

## 🎨 UI Mockup (Text Description)

### Before (Current):
```
[Card: Demo Summary]
  • Bouncing dots (loading...)
  
  After load:
  • Bullet 1 (animated in)
  • Bullet 2 (animated in)
  • Bullet 3 (animated in)
  
  Sources:
  - moneycontrol.com →
  - bloomberg.com →
```

### After (Improved):
```
[Card: Live Progress]
  Progress: ████████░░ 80%
  
  Timeline:
  ✓ Started (2s ago)
  ✓ Found 5 articles (5s ago)
  ⊙ Analyzing content... (now)
  ○ Generating summary
  ○ Complete
  
[Card: Summary - Executive Format]
  Badge: Executive Summary | High Confidence
  
  "Marico reported strong Q2 growth with 30% YoY revenue 
  increase driven by pricing and volume gains..."
  
  Sources (3 articles):
  📄 Marico Q2 Results
     📅 Oct 13, 2025 (17 days ago) | 🤖 AI-extracted
     moneycontrol.com →
  
  📄 Marico Business Update
     📅 Oct 3, 2025 (27 days ago) | ⚡ Metadata
     moneycontrol.com →
```

---

## 🚀 Rollout Strategy

### Week 1: MVP (SSE + Basic Progress)
- Backend SSE endpoint
- Basic progress bar
- Simple timeline
**Goal:** Show live progress instead of static loader

### Week 2: Rich Display
- Format-specific components
- Enhanced sources with dates
- Auto-detection
**Goal:** Better visual hierarchy for different outputs

### Week 3: Polish & Testing
- Animations
- Error handling
- Mobile optimization
**Goal:** Production-ready UX

---

## 🧪 Testing Plan

### Backend
1. Test SSE connection stays alive
2. Test concurrent requests
3. Test error propagation
4. Load test (multiple simultaneous streams)

### Frontend
1. Test SSE reconnection on disconnect
2. Test progress updates render correctly
3. Test all format variants
4. Test mobile responsiveness
5. Test accessibility (screen readers)

---

## 💡 Future Enhancements (Post-MVP)

1. **Pause/Resume**: Allow users to pause agent execution
2. **Edit Intent**: Change output format mid-stream
3. **Export Options**: PDF, JSON, plain text
4. **Share Links**: Shareable summary URLs
5. **History**: View previous summaries
6. **Compare**: Side-by-side comparison of runs
7. **Notifications**: Browser notifications when complete

---

## 🎯 Success Metrics

- **User Engagement**: Time spent watching progress vs loader
- **Perceived Speed**: User survey (feels faster?)
- **Error Recovery**: Fewer abandoned requests
- **Format Usage**: Which formats get used most
- **Satisfaction**: NPS score before/after

---

**Estimated Effort:**
- Backend SSE: 1-2 days
- Frontend Progress: 2-3 days  
- Rich Display: 2-3 days
- Polish & Testing: 1-2 days
**Total: 6-10 days for full implementation**

