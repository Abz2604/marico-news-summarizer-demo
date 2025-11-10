"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ExternalLink } from "lucide-react"
import { AgentProgress } from "@/components/agent-progress"
import { AgentTimeline } from "@/components/agent-timeline"

interface BriefingData {
  url: string
  prompt: string
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

    const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

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

    // Connect to SSE endpoint
    const eventSource = new EventSource(
      `${API_BASE}/agent/run/stream?` +
        new URLSearchParams({
          prompt: briefingData.prompt,
          seed_links: JSON.stringify([briefingData.url]),
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
  }, [briefingData])

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
                      <div
                        key={bulletIndex}
                        className="flex gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors"
                      >
                        <span className="text-primary font-semibold flex-shrink-0 text-sm">•</span>
                        <p className="text-sm text-foreground">{bullet}</p>
                      </div>
                    ))
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
