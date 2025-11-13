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

function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("auth_token")
  }
  return null
}

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  const token = getAuthToken()
  
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  }
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  
  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new APIError(
      errorData.detail || `API request failed: ${response.statusText}`,
      response.status,
      errorData
    )
  }

  // Handle 204 No Content (e.g., DELETE responses)
  if (response.status === 204) {
    return undefined as T
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
  user_id: string
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

    delete: async (id: string): Promise<void> => {
      return fetchAPI(`/briefings/${id}`, {
        method: "DELETE",
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

    update: async (id: string, data: {
      name?: string
      description?: string
      briefing_ids?: string[]
      recipient_emails?: string[]
      schedule_description?: string
      status?: string
    }): Promise<Campaign> => {
      return fetchAPI<Campaign>(`/campaigns/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      })
    },

    delete: async (id: string): Promise<{ message: string }> => {
      return fetchAPI<{ message: string }>(`/campaigns/${id}`, {
        method: "DELETE",
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

  // Agent V2
  agentV2: {
    run: async (data: {
      url: string
      prompt: string
      page_type: string
      max_items?: number
      time_range_days?: number
    }): Promise<{
      items: Array<{
        url: string
        title: string
        content: string
        publish_date: string | null
        content_type: string
        metadata: Record<string, any>
      }>
      summary: string | null
      metadata: Record<string, any> | null
    }> => {
      return fetchAPI("/agent-v2/run", {
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

  // Auth
  auth: {
    signup: async (data: {
      email: string
      password: string
      display_name?: string
    }): Promise<{
      access_token: string
      token_type: string
      user: {
        id: string
        email: string
        display_name: string | null
        role: string
      }
    }> => {
      return fetchAPI("/auth/signup", {
        method: "POST",
        body: JSON.stringify(data),
      })
    },

    login: async (email: string, password: string): Promise<{
      access_token: string
      token_type: string
      user: {
        id: string
        email: string
        display_name: string | null
        role: string
      }
    }> => {
      // Use FormData for OAuth2PasswordRequestForm compatibility
      const formData = new FormData()
      formData.append("username", email) // OAuth2 uses 'username' field
      formData.append("password", password)
      
      // Don't set Content-Type header for FormData - browser will set it with boundary
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {}, // Empty headers - browser will set Content-Type with boundary
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new APIError(
          errorData.detail || `Login failed: ${response.statusText}`,
          response.status,
          errorData
        )
      }

      return response.json()
    },

    me: async (): Promise<{
      id: string
      email: string
      display_name: string | null
      role: string
    }> => {
      return fetchAPI("/auth/me")
    },
  },
}

export { APIError }

