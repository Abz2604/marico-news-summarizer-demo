export interface DemoBriefing {
  id: string
  name: string
  source: string
  promptSummary: string
  lastUpdated: string
  status: "active" | "paused" | "error"
  associatedCampaigns: string[]
}

export interface DemoCampaign {
  id: string
  name: string
  briefings: string[]
  recipients: string[]
  deliveryTimes: string[]
  lastSent: string
  status: "active" | "draft" | "paused"
}

export const DEMO_CAMPAIGN_RECIPIENTS = [
  "ceo@example.com",
  "cmo@example.com",
  "cto@example.com",
  "head-of-eng@example.com",
  "investor-relations@example.com",
  "strategy@example.com",
]

export const DEMO_BRIEFINGS: DemoBriefing[] = [
  {
    id: "1",
    name: "Tech Headlines Digest",
    source: "techcrunch.com",
    promptSummary: "Top 5 technology stories in concise bullet points",
    lastUpdated: "2025-10-22 08:45",
    status: "active",
    associatedCampaigns: ["Daily CXO Briefing"],
  },
  {
    id: "2",
    name: "Regulation Watch",
    source: "theverge.com",
    promptSummary: "Summarize policy and regulation news affecting digital media",
    lastUpdated: "2025-10-21 13:10",
    status: "active",
    associatedCampaigns: ["Daily CXO Briefing", "Market Pulse"],
  },
  {
    id: "3",
    name: "Developer Insights",
    source: "news.ycombinator.com",
    promptSummary: "Highlight trending developer discussions with key takeaways",
    lastUpdated: "2025-10-20 18:30",
    status: "paused",
    associatedCampaigns: ["Engineering Weekly"],
  },
]

export const DEMO_CAMPAIGNS: DemoCampaign[] = [
  {
    id: "c1",
    name: "Daily CXO Briefing",
    briefings: ["Tech Headlines Digest", "Regulation Watch"],
    recipients: ["ceo@example.com", "cmo@example.com"],
    deliveryTimes: ["09:00", "17:00"],
    lastSent: "2025-10-22 09:05",
    status: "active",
  },
  {
    id: "c2",
    name: "Market Pulse",
    briefings: ["Regulation Watch"],
    recipients: ["investor-relations@example.com"],
    deliveryTimes: ["12:00"],
    lastSent: "2025-10-21 12:10",
    status: "draft",
  },
  {
    id: "c3",
    name: "Engineering Weekly",
    briefings: ["Developer Insights"],
    recipients: ["cto@example.com", "head-of-eng@example.com"],
    deliveryTimes: ["Friday 10:00"],
    lastSent: "2025-10-18 10:00",
    status: "paused",
  },
]

