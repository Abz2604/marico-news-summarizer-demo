# 📧 Campaign Preview UX Design

## 🎯 The Challenge

**User Journey:**
1. User creates a campaign with briefings
2. User clicks "Preview Email" 
3. **Problem:** Briefings haven't been run yet → No summaries exist!

**Question:** Where/how do we show the CTA to run briefings?

---

## 💡 Recommended Solution: Smart Preview Endpoint

### API Design: `/campaigns/{id}/preview`

The endpoint should return **structured data** indicating the state, not just HTML or an error.

#### Response Type 1: ✅ **Ready to Preview** (All summaries exist)
```json
{
  "status": "ready",
  "html": "<html>...rendered email with summaries...</html>",
  "briefings": [
    {
      "id": "briefing_123",
      "name": "Tech News",
      "summary_exists": true,
      "last_run_at": "2025-11-06T09:00:00Z"
    }
  ],
  "warning": null
}
```

#### Response Type 2: ⚠️ **Partial** (Some briefings have summaries, some don't)
```json
{
  "status": "partial",
  "html": "<html>...rendered with available summaries + placeholders...</html>",
  "briefings": [
    {
      "id": "briefing_123",
      "name": "Tech News",
      "summary_exists": true,
      "last_run_at": "2025-11-06T09:00:00Z"
    },
    {
      "id": "briefing_456",
      "name": "Market Updates",
      "summary_exists": false,
      "last_run_at": null
    }
  ],
  "warning": "Some briefings haven't been run yet",
  "missing_briefing_ids": ["briefing_456"]
}
```

#### Response Type 3: ❌ **Not Ready** (No summaries at all)
```json
{
  "status": "not_ready",
  "html": null,
  "briefings": [
    {
      "id": "briefing_123",
      "name": "Tech News",
      "summary_exists": false,
      "last_run_at": null
    },
    {
      "id": "briefing_456",
      "name": "Market Updates",
      "summary_exists": false,
      "last_run_at": null
    }
  ],
  "message": "No briefings have been run yet. Run briefings to generate preview.",
  "missing_briefing_ids": ["briefing_123", "briefing_456"]
}
```

---

## 🎨 Frontend UX Options

### Option A: **Inline Warning in Preview Modal** (Recommended)

```
┌─────────────────────────────────────────────┐
│ Preview Email: Daily Tech Digest            │
├─────────────────────────────────────────────┤
│                                             │
│  ⚠️  Some briefings need to be run first   │
│                                             │
│  Missing Summaries:                         │
│  • Tech News                  [Run Now →]  │
│  • Market Updates             [Run Now →]  │
│                                             │
│  [Run All Missing] [Cancel]                │
│                                             │
└─────────────────────────────────────────────┘
```

**Flow:**
1. User clicks "Preview Email"
2. Frontend calls `GET /campaigns/{id}/preview`
3. If status = "not_ready":
   - Show modal with warning
   - List briefings with individual "Run Now" buttons
   - Offer "Run All Missing" button
4. When user clicks "Run Now":
   - Call `POST /briefings/{id}/run` for that briefing
   - Show loading spinner
   - When complete, refresh preview

---

### Option B: **Pre-Check Before Preview** (Proactive)

```
┌─────────────────────────────────────────────┐
│ Campaign: Daily Tech Digest                 │
│ Status: Active                              │
│ Next Run: Tomorrow 9:00 AM                  │
├─────────────────────────────────────────────┤
│                                             │
│ Briefings:                                  │
│ ✅ Tech News         Last run: 2h ago      │
│ ❌ Market Updates    Never run  [Run Now]  │
│                                             │
│ [Preview Email] [Send Now] [Edit]          │
│                                             │
└─────────────────────────────────────────────┘
```

**Flow:**
1. Campaigns list page shows status of each briefing
2. User can run individual briefings before previewing
3. "Preview Email" button shows badge if summaries missing
4. Clicking preview still works (shows partial preview)

---

### Option C: **Auto-Run on Preview Click** (Aggressive)

```
┌─────────────────────────────────────────────┐
│ Generating Preview...                       │
├─────────────────────────────────────────────┤
│                                             │
│ Running briefings:                          │
│ ✅ Tech News         Complete               │
│ ⏳ Market Updates    Running... (30s)       │
│                                             │
│ This may take up to 2 minutes.             │
│                                             │
└─────────────────────────────────────────────┘
```

**Flow:**
1. User clicks "Preview Email"
2. Backend checks for missing summaries
3. If missing, auto-trigger agent runs
4. Frontend shows progress
5. When all complete, show preview

**⚠️ Risk:** Slow UX, user might not want to run (costs money)

---

## 🏆 Recommended Approach: **Hybrid of A + B**

### Campaign Page (Proactive Warning):
```typescript
// Show status before preview
<div className="campaign-card">
  <h3>Daily Tech Digest</h3>
  
  {/* Briefings Status */}
  <div className="briefings-status">
    <BriefingStatusBadge 
      briefing={techNews} 
      status="ready" 
      lastRun="2h ago"
    />
    <BriefingStatusBadge 
      briefing={marketUpdates} 
      status="never_run"
      onRun={() => runBriefing(marketUpdates.id)}
    />
  </div>
  
  {/* Actions */}
  <div className="actions">
    <Button 
      onClick={handlePreview}
      disabled={allBriefingsNeverRun}
    >
      Preview Email
      {hasMissingSummaries && <Badge>⚠️</Badge>}
    </Button>
  </div>
</div>
```

### Preview Modal (Graceful Handling):
```typescript
// When preview is clicked
const handlePreview = async () => {
  const response = await fetch(`/api/campaigns/${id}/preview`);
  const data = await response.json();
  
  if (data.status === 'not_ready') {
    // Show warning modal
    setShowWarningModal(true);
    setMissingBriefings(data.briefings.filter(b => !b.summary_exists));
  } else if (data.status === 'partial') {
    // Show preview with warning banner
    setPreviewHtml(data.html);
    setShowPartialWarning(true);
    setMissingBriefings(data.missing_briefing_ids);
  } else {
    // Show full preview
    setPreviewHtml(data.html);
  }
};
```

---

## 📝 Detailed API Contract

### Endpoint: `GET /api/campaigns/{campaign_id}/preview`

**Path Parameters:**
- `campaign_id` (string, required)

**Query Parameters:**
- `force_refresh` (boolean, optional) - Ignore cached summaries, trigger new runs
- `max_age_hours` (integer, optional) - Only use summaries newer than X hours

**Response Schema:**
```typescript
interface CampaignPreviewResponse {
  status: 'ready' | 'partial' | 'not_ready';
  html: string | null;  // Rendered email HTML (null if not_ready)
  campaign: {
    id: string;
    name: string;
    subject: string;  // Email subject line
  };
  briefings: Array<{
    id: string;
    name: string;
    summary_exists: boolean;
    last_run_at: string | null;  // ISO 8601
    summary_age_hours: number | null;
  }>;
  message: string | null;  // User-friendly message
  missing_briefing_ids: string[];  // IDs that need to be run
  actions: {
    run_missing_url: string;  // POST endpoint to run all missing
    run_individual_urls: Record<string, string>;  // Map briefing_id -> run URL
  };
}
```

**Example Response (not_ready):**
```json
{
  "status": "not_ready",
  "html": null,
  "campaign": {
    "id": "camp_123",
    "name": "Daily Tech Digest",
    "subject": "Your Daily Tech News - {{date}}"
  },
  "briefings": [
    {
      "id": "brief_123",
      "name": "Tech News",
      "summary_exists": false,
      "last_run_at": null,
      "summary_age_hours": null
    },
    {
      "id": "brief_456",
      "name": "Market Updates",
      "summary_exists": false,
      "last_run_at": null,
      "summary_age_hours": null
    }
  ],
  "message": "No summaries available yet. Please run the briefings to generate content.",
  "missing_briefing_ids": ["brief_123", "brief_456"],
  "actions": {
    "run_missing_url": "/api/campaigns/camp_123/run-missing",
    "run_individual_urls": {
      "brief_123": "/api/briefings/brief_123/run",
      "brief_456": "/api/briefings/brief_456/run"
    }
  }
}
```

---

## 🎯 Helper Endpoint: Run All Missing

### Endpoint: `POST /api/campaigns/{campaign_id}/run-missing`

Convenience endpoint to trigger all missing briefings at once.

**Request:**
```json
{
  "run_in_background": true  // Optional: return immediately vs wait for completion
}
```

**Response (background mode):**
```json
{
  "message": "Started 2 agent runs",
  "run_ids": ["run_789", "run_790"],
  "briefing_ids": ["brief_123", "brief_456"],
  "estimated_completion_seconds": 120
}
```

**Response (synchronous mode):**
```json
{
  "message": "Completed 2 agent runs",
  "results": [
    {
      "briefing_id": "brief_123",
      "run_id": "run_789",
      "status": "succeeded",
      "summary_id": "sum_999"
    },
    {
      "briefing_id": "brief_456",
      "run_id": "run_790",
      "status": "succeeded",
      "summary_id": "sum_998"
    }
  ]
}
```

---

## 🎨 Complete Frontend Flow

### Step 1: Campaign Card Component
```jsx
function CampaignCard({ campaign }) {
  const { briefings, missing_count } = useCampaignStatus(campaign.id);
  
  return (
    <Card>
      <h3>{campaign.name}</h3>
      
      {/* Briefings Status Section */}
      <div className="briefings-grid">
        {briefings.map(b => (
          <BriefingChip
            key={b.id}
            name={b.name}
            hasRun={b.summary_exists}
            lastRun={b.last_run_at}
            onRun={() => runBriefing(b.id)}
          />
        ))}
      </div>
      
      {/* Warning if never run */}
      {missing_count === briefings.length && (
        <Alert severity="warning">
          No briefings have been run yet. 
          <Button onClick={runAllMissing}>Run All Now</Button>
        </Alert>
      )}
      
      {/* Action Buttons */}
      <ButtonGroup>
        <Button 
          onClick={handlePreview}
          disabled={missing_count === briefings.length}
        >
          Preview Email
          {missing_count > 0 && <Badge>{missing_count} missing</Badge>}
        </Button>
        <Button onClick={handleSendNow}>Send Now</Button>
      </ButtonGroup>
    </Card>
  );
}
```

### Step 2: Preview Modal Component
```jsx
function PreviewModal({ campaignId, open, onClose }) {
  const [previewData, setPreviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    if (open) loadPreview();
  }, [open, campaignId]);
  
  const loadPreview = async () => {
    setLoading(true);
    const data = await fetchCampaignPreview(campaignId);
    setPreviewData(data);
    setLoading(false);
  };
  
  if (loading) return <LoadingSpinner />;
  
  // Case 1: Not ready at all
  if (previewData?.status === 'not_ready') {
    return (
      <Modal open={open} onClose={onClose}>
        <ModalHeader>
          <Icon>⚠️</Icon>
          <h2>Preview Not Available</h2>
        </ModalHeader>
        
        <ModalBody>
          <p>These briefings need to be run first:</p>
          <BriefingsList>
            {previewData.briefings.map(b => (
              <BriefingRow key={b.id}>
                <span>{b.name}</span>
                <Button 
                  size="sm"
                  onClick={() => runBriefing(b.id)}
                >
                  Run Now →
                </Button>
              </BriefingRow>
            ))}
          </BriefingsList>
        </ModalBody>
        
        <ModalFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button 
            variant="primary"
            onClick={async () => {
              await runAllMissing(campaignId);
              await loadPreview(); // Refresh
            }}
          >
            Run All & Preview
          </Button>
        </ModalFooter>
      </Modal>
    );
  }
  
  // Case 2: Partial or ready - show preview with optional warning
  return (
    <Modal open={open} onClose={onClose} size="large">
      <ModalHeader>
        <h2>Email Preview: {previewData.campaign.name}</h2>
      </ModalHeader>
      
      {previewData.status === 'partial' && (
        <Alert severity="info">
          Some briefings are missing. Preview shows available content only.
          <Button onClick={runMissing}>Run Missing</Button>
        </Alert>
      )}
      
      <ModalBody>
        {/* Render HTML preview */}
        <EmailPreviewFrame html={previewData.html} />
      </ModalBody>
      
      <ModalFooter>
        <Button onClick={onClose}>Close</Button>
        <Button onClick={handleSend}>Send to Recipients</Button>
      </ModalFooter>
    </Modal>
  );
}
```

---

## 🎯 Summary: Where CTAs Appear

### 1. **Campaign List Page** (Proactive)
- Badge on each briefing showing run status
- "Run Now" button next to briefings that haven't run
- Warning if campaign has never been run

### 2. **Preview Button** (Warning)
- Disabled if no briefings have ever run
- Shows badge with missing count if some haven't run
- Enabled but shows warning modal if partial

### 3. **Preview Modal** (Actionable)
- If not_ready: Shows list of briefings with individual "Run Now" buttons
- Offers "Run All & Preview" button to trigger all at once
- If partial: Shows preview + banner with "Run Missing" button

### 4. **Helper Endpoint** (Convenient)
- `POST /campaigns/{id}/run-missing` runs all missing briefings
- Can be called from any of the above CTAs

---

## ✅ Implementation Checklist

- [ ] Add `get_latest_summary(briefing_id)` to agent_service
- [ ] Implement smart `/campaigns/{id}/preview` endpoint
- [ ] Add `/campaigns/{id}/run-missing` helper endpoint
- [ ] Update frontend to show briefing status on campaign cards
- [ ] Implement preview modal with warning states
- [ ] Add loading/progress indicators for runs
- [ ] Test all three scenarios: ready, partial, not_ready

---

**This gives users clear, actionable CTAs at every step!** 🚀

