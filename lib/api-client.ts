/**
 * API Client for Marico News Summarizer Backend
 * Connects Next.js frontend to FastAPI backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api"

class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: any
  ) {
    super(message)
    this.name = "APIError"
  }
}

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new APIError(
      errorData.detail || `API request failed: ${response.statusText}`,
      response.status,
      errorData
    )
  }

  return response.json()
}

// Types
export interface Briefing {
  id: string
  name: string
  description: string | null
  status: string
  prompt: string
  seed_links: string[]
  created_at: string
  updated_at: string
  last_run_at: string | null
}

export interface BriefingListResponse {
  items: Briefing[]
  nextCursor: string | null
}

export interface Campaign {
  id: string
  name: string
  status: string
  description: string | null
  briefing_ids: string[]
  recipient_emails: string[]
  schedule_description: string | null
  created_at: string
  updated_at: string
}

export interface CampaignListResponse {
  items: Campaign[]
}

export interface CampaignPreviewResponse {
  status: "ready" | "partial" | "not_ready"
  html: string | null
  campaign: {
    id: string
    name: string
    subject: string
  }
  briefings: Array<{
    id: string
    name: string
    summary_exists: boolean
    last_run_at: string | null
    summary_age_hours: number | null
  }>
  message: string | null
  missing_briefing_ids: string[]
  actions: {
    run_missing_url: string
    run_individual_urls: Record<string, string>
  }
}

export interface AgentRunResponse {
  summary_markdown: string
  bullet_points: string[]
  citations: Array<{
    url: string
    label?: string
  }>
  model: string
}

// API Client
export const apiClient = {
  // Briefings
  briefings: {
    list: async (status?: string, limit: number = 20): Promise<BriefingListResponse> => {
      const params = new URLSearchParams()
      if (status) params.append("status", status)
      params.append("limit", limit.toString())
      
      return fetchAPI<BriefingListResponse>(`/briefings?${params}`)
    },

    get: async (id: string): Promise<{ briefing: Briefing; latest_summary: any }> => {
      return fetchAPI(`/briefings/${id}`)
    },

    create: async (data: {
      name: string
      prompt: string
      seed_links: string[]
      description?: string
    }): Promise<Briefing> => {
      return fetchAPI<Briefing>("/briefings", {
        method: "POST",
        body: JSON.stringify(data),
      })
    },

    update: async (
      id: string,
      data: Partial<Pick<Briefing, "name" | "description" | "status" | "prompt" | "seed_links">>
    ): Promise<Briefing> => {
      return fetchAPI<Briefing>(`/briefings/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      })
    },

    run: async (id: string): Promise<AgentRunResponse> => {
      return fetchAPI<AgentRunResponse>(`/briefings/${id}/run`, {
        method: "POST",
      })
    },

    getRuns: async (id: string): Promise<{ items: any[] }> => {
      return fetchAPI(`/briefings/${id}/runs`)
    },

    getSummaries: async (id: string): Promise<{ items: any[] }> => {
      return fetchAPI(`/briefings/${id}/summaries`)
    },
  },

  // Campaigns
  campaigns: {
    list: async (): Promise<CampaignListResponse> => {
      return fetchAPI<CampaignListResponse>("/campaigns")
    },

    get: async (id: string): Promise<Campaign> => {
      return fetchAPI<Campaign>(`/campaigns/${id}`)
    },

    preview: async (id: string): Promise<CampaignPreviewResponse> => {
      return fetchAPI<CampaignPreviewResponse>(`/campaigns/${id}/preview`)
    },

    runMissing: async (id: string): Promise<{
      message: string
      run_ids: string[]
      briefing_ids: string[]
      estimated_completion_seconds: number
    }> => {
      return fetchAPI(`/campaigns/${id}/run-missing`, {
        method: "POST",
      })
    },

    send: async (id: string): Promise<{
      message: string
      recipients: string[]
      subject: string
      briefings_included: number
      briefings_missing: number
    }> => {
      return fetchAPI(`/campaigns/${id}/send`, {
        method: "POST",
      })
    },
  },

  // Agent
  agent: {
    run: async (data: {
      prompt: string
      seed_links: string[]
      max_articles?: number
    }): Promise<AgentRunResponse> => {
      return fetchAPI<AgentRunResponse>("/agent/run", {
        method: "POST",
        body: JSON.stringify(data),
      })
    },
  },

  // Health
  health: {
    check: async (): Promise<{ status: string; app: string; env: string }> => {
      return fetchAPI("/healthz")
    },

    diagnostics: async (): Promise<any> => {
      return fetchAPI("/healthz/diagnostics")
    },
  },
}

export { APIError }

