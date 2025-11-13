"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ExternalLink, ChevronDown, ChevronUp } from "lucide-react"
import { AgentProgress } from "@/components/agent-progress"
import { AgentTimeline } from "@/components/agent-timeline"
import { apiClient } from "@/lib/api-client"

interface BriefingData {
  url: string
  prompt: string
  useAgentV2?: boolean
}

interface DemoSummaryProps {
  briefingData: BriefingData | null
}

interface AgentSummaryResponse {
  summary_markdown: string
  bullet_points: string[]
  citations: { url: string; label: string; title?: string; date?: string; age_days?: number }[]
  model: string
}

interface SourceWithBullets {
  title: string
  domain: string
  url: string
  date?: string
  age_days?: number
  bullets: string[]
  label: string
  fullContent?: string  // Full article content for expansion
}

interface TimelineStep {
  name: string
  status: "pending" | "active" | "complete" | "error"
  timestamp?: string
  details?: string
}

export function DemoSummary({ briefingData }: DemoSummaryProps) {
  const [isStreaming, setIsStreaming] = useState(false)
  const [summaryMd, setSummaryMd] = useState<string>("")
  const [sourcesWithBullets, setSourcesWithBullets] = useState<SourceWithBullets[]>([])
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState("init")
  const [stepDetails, setStepDetails] = useState<string>()
  const [timeline, setTimeline] = useState<TimelineStep[]>([])
  const [displayedSourcesCount, setDisplayedSourcesCount] = useState(0)
  const [fetchCount, setFetchCount] = useState(0)
  const [totalFetch, setTotalFetch] = useState(0)

  useEffect(() => {
    if (!briefingData) {
      setSummaryMd("")
      setSourcesWithBullets([])
      setIsStreaming(false)
      setProgress(0)
      setCurrentStep("init")
      setTimeline([])
      setDisplayedSourcesCount(0)
      setFetchCount(0)
      setTotalFetch(0)
      return
    }

    // Reset state
    setSummaryMd("")
    setSourcesWithBullets([])
    setProgress(0)
    setCurrentStep("init")
    setTimeline([])
    setDisplayedSourcesCount(0)
    setFetchCount(0)
    setTotalFetch(0)
    setIsStreaming(true)

    // Use Agent V2 if toggled
    if (briefingData.useAgentV2) {
      handleAgentV2()
      return
    }

    // Otherwise use Agent V1 (SSE)
    handleAgentV1()
  }, [briefingData])

  const handleAgentV2 = () => {
    if (!briefingData) return

    const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
    const startTime = Date.now()

    const addTimelineStep = (name: string, status: TimelineStep["status"], details?: string) => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      const timestamp = `${elapsed}s`

      setTimeline((prev) => {
        const existing = prev.findIndex((s) => s.name === name)
        if (existing >= 0) {
          const updated = [...prev]
          updated[existing] = { ...updated[existing], status, details, timestamp }
          return updated
        } else {
          return [...prev, { name, status, details, timestamp }]
        }
      })
    }

    // Extract time range from prompt if mentioned (e.g., "past 7 days")
    const timeRangeMatch = briefingData.prompt.match(/(\d+)\s*days?/i)
    const timeRangeDays = timeRangeMatch ? parseInt(timeRangeMatch[1]) : undefined

    // Build SSE URL
    const params = new URLSearchParams({
      url: briefingData.url,
      prompt: briefingData.prompt,
      page_type: "blog_listing",
      max_items: "10",
    })
    if (timeRangeDays) {
      params.append("time_range_days", timeRangeDays.toString())
    }

    // Connect to SSE endpoint
    const eventSource = new EventSource(
      `${API_BASE}/agent-v2/run/stream?${params}`
    )

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const eventType = data.event

        // Handle different event types
        switch (eventType) {
          case "init":
            addTimelineStep("Agent V2 Started", "active", `Processing ${data.url}`)
            setCurrentStep("init")
            setProgress(5)
            break

          case "fetch_listing:start":
            addTimelineStep("Fetching Listing Page", "active", data.url)
            setCurrentStep("fetching")
            setProgress(10)
            break

          case "fetch_listing:complete":
            addTimelineStep("Fetching Listing Page", "complete", `${data.html_size_kb} KB fetched`)
            setProgress(20)
            break

          case "extract_links:start":
            addTimelineStep("Extracting Links", "active", `Analyzing ${data.html_length} chars`)
            setProgress(25)
            break

          case "extract_links:analyzing":
            addTimelineStep("Extracting Links", "active", `Found ${data.total_links_found} potential links`)
            break

          case "extract_links:stage1:start":
            addTimelineStep("Classifying Links", "active", `Processing ${data.total_links} links in ${data.batch_count} batches`)
            setProgress(30)
            break

          case "extract_links:stage1:batch":
            addTimelineStep("Classifying Links", "active", `Batch ${data.batch_num}: Found ${data.articles_found} articles`)
            break

          case "extract_links:stage1:complete":
            addTimelineStep("Classifying Links", "complete", `Found ${data.total_articles_found} article links`)
            setProgress(50)
            break

          case "extract_links:stage2:start":
            addTimelineStep("Filtering by Topic", "active", `Filtering ${data.article_links_count} articles`)
            setProgress(55)
            break

          case "extract_links:stage2:filtered":
            addTimelineStep("Filtering by Topic", "active", `${data.relevant_links} relevant articles found`)
            break

          case "extract_links:complete":
            addTimelineStep("Extracting Links", "complete", `Found ${data.links_found} relevant links`)
            setProgress(60)
            break

          case "fetch_article:start":
            addTimelineStep(`Fetching Article ${data.article_num}/${data.total_links}`, "active", data.title || data.url)
            setCurrentStep("fetching")
            setProgress(60 + (data.article_num / data.total_links) * 20)
            break

          case "fetch_article:extracting":
            addTimelineStep(`Fetching Article ${data.article_num}/${data.total_links}`, "active", "Extracting content...")
            break

          case "fetch_article:complete":
            addTimelineStep(`Fetching Article ${data.article_num}/${data.total_links}`, "complete", data.title)
            setProgress(60 + (data.article_num / data.total_links) * 20)
            break

          case "fetch_article:skipped":
            addTimelineStep(`Article ${data.article_num} Skipped`, "error", `${data.reason}: ${data.title}`)
            break

          case "check_goal:start":
            addTimelineStep("Evaluating Progress", "active", `${data.extracted_items}/${data.target_items} items extracted`)
            setProgress(85)
            break

          case "check_goal:decision":
            addTimelineStep("Evaluating Progress", "active", data.reasoning || `Quality: ${(data.quality_score * 100).toFixed(0)}%`)
            break

          case "check_goal:done":
            addTimelineStep("Evaluating Progress", "complete", `Goal reached! Quality: ${(data.quality_score * 100).toFixed(0)}%`)
            setProgress(90)
            break

          case "summarize:start":
            addTimelineStep("Generating Summary", "active", `Summarizing ${data.items_count} articles`)
            setCurrentStep("summarizing")
            setProgress(92)
            break

          case "summarize:complete":
            addTimelineStep("Generating Summary", "complete", `${data.summary_length} chars generated`)
            setProgress(98)
            break

          case "complete":
            // Mark all timeline steps as complete
            setTimeline((prev) => 
              prev.map((step) => ({
                ...step,
                status: step.status === "error" ? "error" : "complete" as TimelineStep["status"]
              }))
            )
            
            addTimelineStep("Complete", "complete")
            setCurrentStep("complete")
            setProgress(100)

            // Transform v2 response to match expected format
            const transformed = transformV2Response(data.data, briefingData.prompt)

            setSummaryMd(transformed.summary_markdown || "")

            // Process sources and bullets
            const sourceMap = new Map<string, SourceWithBullets>()

            // Store full content mapping from items
            const contentMap = new Map<string, string>()
            data.data.items.forEach((item: any, index: number) => {
              const label = `[${index + 1}]`
              contentMap.set(label, item.content || "")
            })

            transformed.citations.forEach((citation, index) => {
              try {
                const u = new URL(citation.url)
                const domain = u.hostname.replace("www.", "")
                sourceMap.set(citation.label, {
                  title: citation.title || domain,
                  domain,
                  url: citation.url,
                  date: citation.date,
                  age_days: citation.age_days,
                  bullets: [],
                  label: citation.label,
                  fullContent: contentMap.get(citation.label),
                })
              } catch {
                sourceMap.set(citation.label, {
                  title: citation.url,
                  domain: citation.url,
                  url: citation.url,
                  date: citation.date,
                  age_days: citation.age_days,
                  bullets: [],
                  label: citation.label,
                  fullContent: contentMap.get(citation.label),
                })
              }
            })

            // Assign bullets to sources
            transformed.bullet_points.forEach((bullet) => {
              const citations = extractCitations(bullet)
              if (citations.length > 0) {
                citations.forEach((label) => {
                  const source = sourceMap.get(label)
                  if (source) {
                    source.bullets.push(bullet)
                  }
                })
              }
            })

            const sourcesArray = Array.from(sourceMap.values())

            // Stream sources into view with animation
            sourcesArray.forEach((source, index) => {
              setTimeout(() => {
                setDisplayedSourcesCount(index + 1)
              }, index * 200)
            })

            setSourcesWithBullets(sourcesArray)
            setTimeout(() => setIsStreaming(false), sourcesArray.length * 200 + 500)
            eventSource.close()
            break

          case "error":
            console.error("Agent V2 error:", data.error)
            setCurrentStep("error")
            addTimelineStep("Error", "error", data.error || "Unknown error")
            setSummaryMd(`Error: ${data.error || "Failed to generate summary"}`)
            setIsStreaming(false)
            eventSource.close()
            break

          default:
            // Log unknown events for debugging
            console.log("Unknown event:", eventType, data)
        }
      } catch (error) {
        console.error("Error parsing SSE event:", error, event.data)
      }
    }

    eventSource.onerror = (error) => {
      console.error("SSE connection error:", error)
      setCurrentStep("error")
      addTimelineStep("Connection Error", "error", "Lost connection to server")
      setIsStreaming(false)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }

  const handleAgentV1 = () => {
    const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

    // Connect to SSE endpoint
    const eventSource = new EventSource(
      `${API_BASE}/agent/run/stream?` +
        new URLSearchParams({
          prompt: briefingData!.prompt,
          seed_links: JSON.stringify([briefingData!.url]),
          max_articles: "10",
        })
    )

    const startTime = Date.now()

    const addTimelineStep = (name: string, status: TimelineStep["status"], details?: string) => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      const timestamp = `${elapsed}s`

      setTimeline((prev) => {
        const existing = prev.findIndex((s) => s.name === name)
        if (existing >= 0) {
          // Update existing step
          const updated = [...prev]
          updated[existing] = { ...updated[existing], status, details, timestamp }
          return updated
        } else {
          // Add new step
          return [...prev, { name, status, details, timestamp }]
        }
      })
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // Map events to progress and steps
        switch (data.event) {
          case "init":
            setProgress(5)
            setCurrentStep("init")
            addTimelineStep("Starting agent", "active")
            break

          case "nav:analyzing":
            setProgress(15)
            setCurrentStep("analyzing")
            addTimelineStep("Starting agent", "complete")
            addTimelineStep("Analyzing page", "active", data.url)
            break

          case "nav:extracting_links":
            setProgress(25)
            setCurrentStep("navigating")
            addTimelineStep("Analyzing page", "complete")
            addTimelineStep("Finding articles", "active")
            break

          case "nav:extraction_success":
            setProgress(35)
            addTimelineStep("Finding articles", "complete", `Found ${data.found} articles`)
            break

          case "fetch:phase_start":
            setProgress(40)
            setCurrentStep("fetching")
            setFetchCount(0)
            setTotalFetch(data.total_urls)
            addTimelineStep("Fetching articles", "active", `0 of ${data.total_urls}`)
            break

          case "fetch:start":
            setProgress(Math.min(progress + 5, 70))
            setCurrentStep("fetching")
            setStepDetails(new URL(data.url).hostname)
            setFetchCount((prev) => {
              const newCount = prev + 1
              // Update timeline with current count
              const timelineIndex = timeline.findIndex((s) => s.name === "Fetching articles")
              if (timelineIndex >= 0 && totalFetch > 0) {
                setTimeline((prevTimeline) => {
                  const updated = [...prevTimeline]
                  updated[timelineIndex] = {
                    ...updated[timelineIndex],
                    details: `${newCount} of ${totalFetch}`,
                  }
                  return updated
                })
              } else if (!timeline.find((s) => s.name === "Fetching articles")) {
                addTimelineStep("Fetching articles", "active")
              }
              return newCount
            })
            break

          case "date:extracted":
            setCurrentStep("extracting")
            if (!timeline.find((s) => s.name === "Extracting dates")) {
              addTimelineStep("Extracting dates", "active")
            }
            break

          case "dedup:start":
            setProgress(75)
            setCurrentStep("deduplicating")
            addTimelineStep("Fetching articles", "complete")
            addTimelineStep("Removing duplicates", "active")
            break

          case "dedup:complete":
            addTimelineStep("Removing duplicates", "complete", `${data.unique_count} unique`)
            break

          case "summarize:start":
            setProgress(85)
            setCurrentStep("summarizing")
            addTimelineStep("Generating summary", "active")
            break

          case "complete":
            // Mark all timeline steps as complete
            setTimeline((prev) => 
              prev.map((step) => ({
                ...step,
                status: step.status === "error" ? "error" : "complete" as TimelineStep["status"]
              }))
            )
            
            setProgress(100)
            setCurrentStep("complete")
            addTimelineStep("Generating summary", "complete")
            addTimelineStep("Complete", "complete")

            // Process result
            const result: AgentSummaryResponse = data.data

            setSummaryMd(result.summary_markdown || "")

            // Helper to extract citation markers like [1], [2] from bullet text
            const extractCitations = (bullet: string): string[] => {
              const matches = bullet.match(/\[(\d+)\]/g)
              return matches ? matches.map((m) => m) : []
            }

            // Group bullets by citation
            const sourceMap = new Map<string, SourceWithBullets>()
            
            // Initialize sources from citations
            // Note: For V1, we don't have full content available, so fullContent will be undefined
            result.citations.forEach((citation) => {
              try {
                const u = new URL(citation.url)
                const domain = u.hostname.replace("www.", "")
                sourceMap.set(citation.label, {
                  title: citation.title || domain,
                  domain,
                  url: citation.url,
                  date: citation.date,
                  age_days: citation.age_days,
                  bullets: [],
                  label: citation.label,
                  fullContent: undefined, // V1 doesn't provide full content
                })
              } catch {
                sourceMap.set(citation.label, {
                  title: citation.url,
                  domain: citation.url,
                  url: citation.url,
                  date: citation.date,
                  age_days: citation.age_days,
                  bullets: [],
                  label: citation.label,
                  fullContent: undefined, // V1 doesn't provide full content
                })
              }
            })

            // Assign bullets to sources
            result.bullet_points.forEach((bullet) => {
              const citations = extractCitations(bullet)
              
              if (citations.length > 0) {
                // Add bullet to each cited source
                citations.forEach((label) => {
                  const source = sourceMap.get(label)
                  if (source) {
                    source.bullets.push(bullet)
                  }
                })
              }
            })

            // Convert to array - show ALL sources (even if no specific bullets cite them)
            // This helps users see all articles that were analyzed
            const sourcesArray = Array.from(sourceMap.values())

            // Stream sources into view with animation
            sourcesArray.forEach((source, index) => {
              setTimeout(() => {
                setDisplayedSourcesCount(index + 1)
              }, index * 200)
            })

            setSourcesWithBullets(sourcesArray)

            setTimeout(() => setIsStreaming(false), sourcesArray.length * 200 + 500)
            eventSource.close()
            break

          case "error":
            setCurrentStep("error")
            addTimelineStep("Error", "error", data.error)
            setSummaryMd(`Error: ${data.error}`)
            setIsStreaming(false)
            eventSource.close()
            break
        }
      } catch (err) {
        console.error("Failed to parse SSE event:", err)
      }
    }

    eventSource.onerror = () => {
      console.error("SSE connection error")
      setCurrentStep("error")
      setSummaryMd("Connection error. Please try again.")
      setIsStreaming(false)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }

  // Helper functions
  const extractCitations = (bullet: string): string[] => {
    const matches = bullet.match(/\[(\d+)\]/g)
    return matches ? matches.map((m) => m) : []
  }

  const transformV2Response = (
    response: {
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
    },
    prompt: string
  ): AgentSummaryResponse => {
    // Create citations from items
    const citations = response.items.map((item, index) => {
      const label = `[${index + 1}]`
      let date: string | undefined
      let age_days: number | undefined

      if (item.publish_date) {
        try {
          const pubDate = new Date(item.publish_date)
          date = pubDate.toLocaleDateString()
          const now = new Date()
          const diffTime = Math.abs(now.getTime() - pubDate.getTime())
          age_days = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
        } catch {
          // Invalid date, skip
        }
      }

      return {
        url: item.url,
        label,
        title: item.title,
        date,
        age_days,
      }
    })

    // Generate bullet points from items
    // For now, create simple bullets from titles and content snippets
    // In the future, this could be enhanced with LLM summarization
    const bullet_points = response.items.map((item, index) => {
      const label = `[${index + 1}]`
      const contentSnippet = item.content.substring(0, 200).trim()
      return `${item.title} ${label}${contentSnippet ? ` - ${contentSnippet}...` : ""}`
    })

    // Use provided summary or generate one
    const summary_markdown = response.summary || `Summary of ${response.items.length} articles based on: ${prompt}`

    return {
      summary_markdown,
      bullet_points,
      citations,
      model: "agent-v2",
    }
  }

  // Collapsible Log Component
  const CollapsibleLog = ({ title, steps }: { title: string; steps: TimelineStep[] }) => {
    const [isOpen, setIsOpen] = useState(false)

    return (
      <div className="border border-border rounded-lg overflow-hidden">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full flex items-center justify-between p-4 bg-muted/30 hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{title}</span>
            <span className="text-xs text-muted-foreground">({steps.length} steps)</span>
          </div>
          {isOpen ? (
            <ChevronUp className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          )}
        </button>
        {isOpen && (
          <div className="p-4 bg-muted/20">
            <AgentTimeline steps={steps} />
          </div>
        )}
      </div>
    )
  }

  // Expandable Bullet Component
  const ExpandableBullet = ({ 
    bullet, 
    fullContent 
  }: { 
    bullet: string
    fullContent?: string 
  }) => {
    const [isExpanded, setIsExpanded] = useState(false)
    const TRUNCATE_LENGTH = 200

    // If no full content, just show the bullet as-is (may be truncated)
    if (!fullContent) {
      const shouldTruncate = bullet.length > TRUNCATE_LENGTH
      const truncatedBullet = shouldTruncate 
        ? bullet.substring(0, TRUNCATE_LENGTH) + "..."
        : bullet

      return (
        <div className="flex gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors">
          <span className="text-primary font-semibold flex-shrink-0 text-sm">•</span>
          <div className="flex-1">
            <p className="text-sm text-foreground">{truncatedBullet}</p>
          </div>
        </div>
      )
    }

    // If full content exists and is short, show it all
    if (fullContent.length <= TRUNCATE_LENGTH) {
      return (
        <div className="flex gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors">
          <span className="text-primary font-semibold flex-shrink-0 text-sm">•</span>
          <p className="text-sm text-foreground">{bullet}</p>
        </div>
      )
    }

    // Full content exists and is long - show expandable version
    const truncatedBullet = bullet.length > TRUNCATE_LENGTH 
      ? bullet.substring(0, TRUNCATE_LENGTH) + "..."
      : bullet

    return (
      <div className="flex gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors">
        <span className="text-primary font-semibold flex-shrink-0 text-sm">•</span>
        <div className="flex-1 space-y-2">
          <div className="text-sm text-foreground">
            {isExpanded ? (
              <div className="space-y-2">
                <p className="font-medium mb-2">{bullet.split(' - ')[0] || bullet}</p>
                <p className="whitespace-pre-wrap text-foreground/90 leading-relaxed">
                  {fullContent}
                </p>
              </div>
            ) : (
              <>
                {truncatedBullet}
                {bullet.length > TRUNCATE_LENGTH && (
                  <span className="text-muted-foreground">...</span>
                )}
              </>
            )}
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-primary hover:text-primary/80 font-medium transition-colors underline"
          >
            {isExpanded ? "Read less" : "Read more"}
          </button>
        </div>
      </div>
    )
  }

  if (!briefingData) {
    return (
      <Card className="h-fit shadow-sm">
        <CardHeader>
          <CardTitle>Demo Summary</CardTitle>
          <CardDescription>Generate a demo to preview your briefing</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64 text-muted-foreground animate-pulse">
            <p>Fill in the form and click "Generate Demo Summary" to see a preview</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const domain = new URL(briefingData.url).hostname.replace("www.", "")

  return (
    <Card className="h-fit shadow-sm hover:shadow-md transition-shadow duration-300">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2 animate-in fade-in duration-300">
              <Badge variant="secondary" className="animate-in scale-in duration-300">
                Auto
              </Badge>
              <span className="text-sm text-muted-foreground">{domain}</span>
            </div>
            <CardTitle className="text-lg">Summary Preview</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Live Progress (shown while streaming) */}
        {isStreaming && sourcesWithBullets.length === 0 && (
          <div className="space-y-6">
            <AgentProgress currentStep={currentStep} progress={progress} details={stepDetails} />

            {timeline.length > 0 && (
              <div className="p-4 bg-muted/50 rounded-lg">
                <p className="text-xs font-semibold text-muted-foreground mb-3">PROGRESS TIMELINE</p>
                <AgentTimeline steps={timeline} />
              </div>
            )}
          </div>
        )}

        {/* Collapsible Timeline Log (shown after completion) */}
        {!isStreaming && timeline.length > 0 && sourcesWithBullets.length > 0 && (
          <CollapsibleLog title="Agent Execution Log" steps={timeline} />
        )}

        {/* Source Cards with Bullets */}
        {sourcesWithBullets.length > 0 && (
          <div className="space-y-4">
            {sourcesWithBullets.slice(0, displayedSourcesCount).map((source, sourceIndex) => (
              <div
                key={sourceIndex}
                className="border border-border rounded-lg p-4 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300 hover:border-primary/50 transition-all"
                style={{ animationDelay: `${sourceIndex * 50}ms` }}
              >
                {/* Source Header */}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start justify-between gap-3 group"
                >
                  <div className="flex-1">
                    <div className="mb-1">
                      <span className="text-xs font-bold text-primary mr-2">{source.label}</span>
                      <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                        {source.title}
                      </span>
                    </div>
                    <div className="flex gap-2 items-center">
                      <p className="text-xs text-muted-foreground">{source.domain}</p>
                      {source.date && (
                        <>
                          <span className="text-xs text-muted-foreground">•</span>
                          <p className="text-xs text-muted-foreground">
                            📅 {source.date}
                            {source.age_days !== undefined && ` (${source.age_days}d ago)`}
                          </p>
                        </>
                      )}
                    </div>
                  </div>
                  <ExternalLink className="w-4 h-4 text-muted-foreground group-hover:text-primary flex-shrink-0 transition-all duration-200 group-hover:translate-x-0.5" />
                </a>

                {/* Bullets for this Source */}
                <div className="space-y-2 pl-2">
                  {source.bullets.length > 0 ? (
                    source.bullets.map((bullet, bulletIndex) => (
                      <ExpandableBullet
                        key={bulletIndex}
                        bullet={bullet}
                        fullContent={source.fullContent}
                      />
                    ))
                  ) : source.fullContent ? (
                    <ExpandableBullet
                      bullet={`${source.title} - Summary`}
                      fullContent={source.fullContent}
                    />
                  ) : (
                    <div className="p-2 text-xs text-muted-foreground italic">
                      Article analyzed - key points may be synthesized in other bullets
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Summary markdown fallback (for errors or non-bullet responses) */}
        {sourcesWithBullets.length === 0 && !isStreaming && summaryMd && (
          <div className="space-y-2">
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-sm whitespace-pre-wrap">{summaryMd}</div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
