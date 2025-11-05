# 📧 Briefing & Campaign Workflow Design

## 🎯 Current State

### What Works Now:
1. ✅ **Save Briefing** - `POST /briefings` saves config only (no agent run)
2. ✅ **Manual Run** - `POST /briefings/{id}/run` runs agent & saves to DB
3. ✅ **Campaigns Structure** - Tables exist, basic CRUD works
4. ❌ **Email Preview** - Uses mock data (not connected to real summaries)
5. ❌ **Scheduled Execution** - Not implemented yet

---

## 🔄 Complete Workflow Design

### Scenario 1: **Creating a New Briefing**
```
User Action: Create briefing with prompt + seed links
↓
Backend: Save to AI_NW_SUMM_BRIEFINGS (status='draft')
↓
Result: Briefing saved, NO agent run yet
```

**Why?** 
- User might want to edit/test the briefing first
- Agent runs cost money (OpenAI API calls)
- User controls when to run via "Run Now" button

---

### Scenario 2: **Manual "Run Now" (Testing/Preview)**
```
User Action: Click "Run Now" button in UI
↓
API Call: POST /briefings/{id}/run
↓
Backend Flow:
  1. Create agent_run record (status='running')
  2. Run agent (fetch + extract + summarize)
  3. Save summary to AI_NW_SUMM_SUMMARIES
  4. Update briefing.last_run_at
  5. Mark agent_run as 'succeeded'
↓
Result: Latest summary available for preview
```

**Current Status:** ✅ Fully implemented!

---

### Scenario 3: **Email Preview (Before Sending)**
```
User Action: View campaign → Click "Preview Email"
↓
API Call: GET /campaigns/{id}/preview
↓
Backend Flow:
  1. Get campaign → get briefing_ids
  2. For each briefing, get LATEST summary from DB
  3. Combine summaries into one email
  4. Render HTML template
  5. Return HTML for preview
↓
Result: Shows actual latest summary (or "No summary yet" message)
```

**Current Status:** ❌ Uses mock data - NEEDS IMPLEMENTATION

---

### Scenario 4: **Scheduled Execution (The Missing Piece!)**
```
Scheduler Service (Cron/APScheduler):
  Every minute: Check for campaigns due to run
↓
Query:
  SELECT * FROM AI_NW_SUMM_CAMPAIGNS
  WHERE status='active'
  AND next_run_at <= NOW()
↓
For each campaign:
  1. Get all briefings in campaign
  2. For each briefing:
     - Run agent (same as manual run)
     - Save summary to DB
  3. Combine all summaries
  4. Send email to recipients
  5. Update campaign.last_run_at
  6. Calculate & set next_run_at
```

**Current Status:** ❌ NOT IMPLEMENTED - NEEDS DESIGN

---

## 🏗️ Architecture Options for Scheduling

### Option A: **APScheduler (Simple, In-Process)**
**Pros:**
- Simple to implement
- No external dependencies
- Good for MVP/single server

**Cons:**
- Runs inside API process
- Lost if server restarts
- Not scalable to multiple servers

```python
# In main.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

async def check_and_run_campaigns():
    # Query campaigns due to run
    # Execute agent for each briefing
    # Send emails
    pass

scheduler.add_job(check_and_run_campaigns, 'interval', minutes=1)
scheduler.start()
```

---

### Option B: **Celery + Redis (Production Ready)**
**Pros:**
- Scalable
- Persistent task queue
- Retries & monitoring
- Can run on separate workers

**Cons:**
- Requires Redis
- More complex setup
- Overkill for MVP?

```python
# tasks.py
from celery import Celery

celery_app = Celery('marico', broker='redis://localhost:6379')

@celery_app.task
def run_scheduled_campaigns():
    # Same logic as above
    pass

# Schedule with Celery Beat
celery_app.conf.beat_schedule = {
    'check-campaigns': {
        'task': 'tasks.run_scheduled_campaigns',
        'schedule': 60.0,  # Every 60 seconds
    },
}
```

---

### Option C: **External Cron Job (Simplest for Now)**
**Pros:**
- Extremely simple
- System-level reliability
- Separate from API process

**Cons:**
- Requires server access
- Less flexible scheduling
- Manual setup

```bash
# crontab -e
*/5 * * * * cd /app && /app/venv/bin/python scheduler.py
```

---

## 💡 Recommended Approach for MVP

**Use Option A (APScheduler)** for now because:
1. Quick to implement (< 1 hour)
2. No new dependencies
3. Good enough for MVP with few users
4. Easy to migrate to Celery later

---

## 📊 Database Schema Additions Needed

### Add to AI_NW_SUMM_CAMPAIGNS:

```sql
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN schedule_type VARCHAR; -- 'daily', 'weekly', 'monthly', 'custom'
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN schedule_time TIME; -- e.g., '09:00:00' for 9 AM
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN schedule_days VARCHAR; -- JSON: ['monday', 'wednesday', 'friday']
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN schedule_timezone VARCHAR DEFAULT 'Asia/Kolkata';
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN last_run_at TIMESTAMP_TZ;
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN next_run_at TIMESTAMP_TZ;
ALTER TABLE AI_NW_SUMM_CAMPAIGNS ADD COLUMN enabled BOOLEAN DEFAULT true;
```

---

## 🔄 Complete Flow: From Creation to Scheduled Send

### Step 1: User Creates Campaign
```json
POST /campaigns
{
  "name": "Daily Tech Digest",
  "briefing_ids": ["briefing_123", "briefing_456"],
  "recipient_emails": ["ceo@marico.com", "cto@marico.com"],
  "schedule_type": "daily",
  "schedule_time": "09:00:00",
  "schedule_timezone": "Asia/Kolkata"
}
```
**Action:** Save to DB, calculate `next_run_at`

---

### Step 2: User Tests with "Preview"
```
GET /campaigns/{id}/preview
```
**Action:** 
- Get latest summaries for all briefings in campaign
- If no summaries exist, show "Run briefings first" message
- Render HTML email template
- Return for browser display

---

### Step 3: User Triggers Manual Run (Optional)
```
POST /briefings/123/run
POST /briefings/456/run
```
**Action:** Run agent for each briefing, save summaries

---

### Step 4: Scheduler Runs (Automated)
```
Every 1 minute:
  1. Check: SELECT * FROM campaigns WHERE enabled=true AND next_run_at <= NOW()
  2. For each campaign:
     a. Run agents for all briefings
     b. Collect all summaries
     c. Render email HTML
     d. Send via email_service
     e. Update last_run_at, calculate next_run_at
```

---

## 🎨 UI Flow Implications

### Briefings Page:
- ✅ "Create Briefing" → Saves config only
- ✅ "Run Now" button → Triggers agent, shows progress
- ✅ Shows `last_run_at` timestamp
- ✅ Shows latest summary (if exists)

### Campaigns Page:
- ✅ "Create Campaign" → Saves config + schedule
- ✅ "Preview Email" → Shows latest summaries (or "not run yet")
- ✅ "Send Now" → Manual send (uses latest summaries)
- ✅ "Edit Schedule" → Updates schedule_time, next_run_at
- ✅ Shows `last_run_at` and `next_run_at`

---

## 🚀 Implementation Priority

### Phase 1 (Now - Critical):
1. ✅ Fix email preview to use real summaries from DB
2. ✅ Add `get_latest_summary(briefing_id)` function
3. ✅ Connect campaigns to actual briefings

### Phase 2 (Soon - Important):
1. Add schedule fields to campaigns table
2. Implement APScheduler in main.py
3. Create scheduler service module
4. Test scheduled runs

### Phase 3 (Later - Nice to Have):
1. Add email templates (pretty HTML)
2. Add email tracking (open rates, clicks)
3. Add retry logic for failed sends
4. Migrate to Celery if needed

---

## 📝 Key Questions Answered

### Q1: "When we save a briefing, does it run the agent?"
**A:** No. Saving a briefing only stores the configuration. The agent runs when:
- User clicks "Run Now" manually
- Scheduler triggers it based on campaign schedule

### Q2: "How do we preview email?"
**A:** Preview fetches the LATEST summary from the database for each briefing in the campaign. If no summary exists yet, we show a message like "No summary available - run briefings first".

### Q3: "How does scheduled execution work?"
**A:** We'll implement a scheduler (APScheduler) that runs every minute, checks which campaigns are due, runs the agent for their briefings, and sends emails automatically.

---

## 💾 Data Flow Diagram

```
┌─────────────┐
│   Briefing  │  (Config: prompt, links, status)
└──────┬──────┘
       │
       │ trigger_run()
       ▼
┌─────────────┐
│ Agent Run   │  (Execution: running → succeeded/failed)
└──────┬──────┘
       │
       │ generates
       ▼
┌─────────────┐
│   Summary   │  (Output: markdown, bullets, citations)
└──────┬──────┘
       │
       │ used_by
       ▼
┌─────────────┐
│  Campaign   │  (Schedule: time, recipients)
└──────┬──────┘
       │
       │ triggers
       ▼
┌─────────────┐
│    Email    │  (Delivery: HTML, recipients, timestamp)
└─────────────┘
```

---

## 🎯 Next Steps

1. **Implement `get_latest_summary()` in agent_service.py**
2. **Fix `/campaigns/{id}/preview` to use real data**
3. **Design scheduler module**
4. **Add schedule fields to campaigns**
5. **Test complete flow end-to-end**

---

**Ready to implement these fixes?** Let's start with fixing the email preview to use real summaries! 🚀

