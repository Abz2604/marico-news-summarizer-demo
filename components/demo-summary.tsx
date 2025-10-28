"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ExternalLink } from "lucide-react"

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
  citations: { url: string; label: string }[]
  model: string
}

export function DemoSummary({ briefingData }: DemoSummaryProps) {
  const [bullets, setBullets] = useState<string[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [summaryMd, setSummaryMd] = useState<string>("")
  const [sources, setSources] = useState<{ title: string; domain: string; url: string }[]>([])

  useEffect(() => {
    if (!briefingData) {
      setBullets([])
      setSummaryMd("")
      setSources([])
      setIsStreaming(false)
      return
    }

    const controller = new AbortController()
    const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

    async function runAgent() {
      setBullets([])
      setSummaryMd("")
      setSources([])
      setIsStreaming(true)
      try {
        const response = await fetch(`${API_BASE}/api/agent/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: briefingData.prompt,
            seed_links: [briefingData.url],
            max_articles: 3,
          }),
          signal: controller.signal,
        })
        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`)
        }
        const data: AgentSummaryResponse = await response.json()

        // Stream bullets into view
        data.bullet_points.forEach((bullet, index) => {
          setTimeout(() => {
            setBullets((prev) => [...prev, bullet])
          }, index * 250)
        })

        // If no bullets returned, try to parse bullets from markdown
        if ((!data.bullet_points || data.bullet_points.length === 0) && data.summary_markdown) {
          const lines = data.summary_markdown.split("\n").map((l) => l.trim())
          const mdBullets = lines.filter((l) => l.startsWith("-") || l.startsWith("*") || l.startsWith("•"))
          mdBullets.forEach((b, index) => {
            const normalized = b.startsWith("-") ? b : `- ${b}`
            setTimeout(() => setBullets((prev) => [...prev, normalized]), index * 200)
          })
        }

        setSummaryMd(data.summary_markdown || "")

        // Map citations to sources list (derive domain from URL)
        const mapped = data.citations.map((c) => {
          try {
            const u = new URL(c.url)
            const domain = u.hostname.replace("www.", "")
            return { title: domain, domain, url: c.url }
          } catch {
            return { title: c.url, domain: c.url, url: c.url }
          }
        })
        setSources(mapped)

        const bulletCount = data.bullet_points.length
        const mdCount = summaryMd ? summaryMd.split("\n").filter((l) => l.trim().startsWith("-") || l.trim().startsWith("*") || l.trim().startsWith("•")).length : 0
        const delay = Math.max(bulletCount * 250, mdCount * 200)
        setTimeout(() => setIsStreaming(false), delay)
      } catch (err) {
        setBullets(["Failed to generate summary. Please try again."])
        setIsStreaming(false)
      }
    }

    runAgent()
    return () => controller.abort()
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
        {/* Summary Bullets */}
        <div className="space-y-2">
          {bullets.map((bullet, index) => (
            <div
              key={index}
              className="flex gap-3 p-3 bg-muted rounded-lg animate-in fade-in slide-in-from-left-2 duration-300 hover:bg-muted/80 transition-colors"
            >
              <span className="text-primary font-semibold flex-shrink-0">•</span>
              <p className="text-sm text-foreground">{bullet}</p>
            </div>
          ))}
          {isStreaming && (
            <div className="flex gap-3 p-3 bg-muted rounded-lg animate-in fade-in duration-300">
              <span className="text-primary font-semibold flex-shrink-0">•</span>
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-primary rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: "0.1s" }} />
                <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: "0.2s" }} />
              </div>
            </div>
          )}
        </div>

        {/* Summary markdown fallback */}
        {bullets.length === 0 && !isStreaming && summaryMd && (
          <div className="space-y-2">
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-sm whitespace-pre-wrap">{summaryMd}</div>
            </div>
          </div>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <div className="pt-4 border-t border-border animate-in fade-in slide-in-from-bottom-2 duration-300">
            <p className="text-xs font-semibold text-muted-foreground mb-3">SOURCES</p>
            <div className="space-y-2">
              {sources.map((source, index) => (
                <a
                  key={index}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between p-2 hover:bg-muted rounded-lg transition-all duration-200 group animate-in fade-in slide-in-from-left-2"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
                      {source.title}
                    </p>
                    <p className="text-xs text-muted-foreground">{source.domain}</p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-muted-foreground group-hover:text-primary flex-shrink-0 ml-2 transition-all duration-200 group-hover:translate-x-0.5" />
                </a>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
