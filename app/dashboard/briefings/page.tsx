"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Pause, Play, Trash2, Eye, Edit2, Layers, RefreshCw, Loader2, X } from "lucide-react"
import { apiClient, type Briefing } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"
import { useRouter } from "next/navigation"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface SummaryPreview {
  id: string
  summary_markdown: string
  bullet_points: string[]
  citations: Array<{ url: string; title?: string; label?: string }>
  created_at: string
}

export default function MyBriefingsPage() {
  const [briefings, setBriefings] = useState<Briefing[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [selectedBriefing, setSelectedBriefing] = useState<Briefing | null>(null)
  const [summaryPreview, setSummaryPreview] = useState<SummaryPreview | null>(null)
  const { toast } = useToast()
  const router = useRouter()

  // Fetch briefings from API
  useEffect(() => {
    loadBriefings()
  }, [])

  const loadBriefings = async () => {
    try {
      setLoading(true)
      const response = await apiClient.briefings.list()
      setBriefings(response.items)
    } catch (error) {
      console.error("Failed to load briefings:", error)
      toast({
        title: "Error loading briefings",
        description: error instanceof Error ? error.message : "Failed to fetch briefings from server",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  const toggleStatus = async (id: string, currentStatus: string) => {
    try {
      const newStatus = currentStatus === "active" ? "paused" : "active"
      await apiClient.briefings.update(id, { status: newStatus })
      
      // Update local state
      setBriefings(briefings.map((b) => (b.id === id ? { ...b, status: newStatus } : b)))
      
      toast({
        title: "Status updated",
        description: `Briefing ${newStatus === "active" ? "activated" : "paused"}`,
      })
    } catch (error) {
      console.error("Failed to toggle status:", error)
      toast({
        title: "Error",
        description: "Failed to update briefing status",
        variant: "destructive",
      })
    }
  }

  const runBriefing = async (id: string, name: string) => {
    try {
      setRunningId(id)
      toast({
        title: "Running agent...",
        description: `Starting agent run for "${name}". This may take 1-2 minutes.`,
      })
      
      await apiClient.briefings.run(id)
      
      // Refresh briefings list to update last_run_at
      await loadBriefings()
      
      toast({
        title: "Agent run complete!",
        description: `Successfully generated summary for "${name}"`,
      })
    } catch (error) {
      console.error("Failed to run briefing:", error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to run agent",
        variant: "destructive",
      })
    } finally {
      setRunningId(null)
    }
  }

  const deleteBriefing = (id: string) => {
    // TODO: Implement actual delete API call
    setDeletingId(id)
    setTimeout(() => {
      setBriefings(briefings.filter((b) => b.id !== id))
      setDeletingId(null)
      toast({
        title: "Briefing deleted",
        description: "The briefing has been removed",
      })
    }, 300)
  }

  const viewBriefingSummary = async (briefing: Briefing) => {
    try {
      setSelectedBriefing(briefing)
      setPreviewOpen(true)
      setPreviewLoading(true)
      setSummaryPreview(null)

      // Fetch the briefing details including latest summary
      const response = await apiClient.briefings.get(briefing.id)
      
      if (!response.latest_summary) {
        toast({
          title: "No summary available",
          description: "This briefing hasn't been run yet. Click 'Run Now' to generate a summary.",
          variant: "destructive",
        })
        setPreviewOpen(false)
        return
      }

      setSummaryPreview(response.latest_summary)
    } catch (error) {
      console.error("Failed to load summary:", error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load summary",
        variant: "destructive",
      })
      setPreviewOpen(false)
    } finally {
      setPreviewLoading(false)
    }
  }

  const editBriefing = (briefingId: string) => {
    router.push(`/dashboard/briefings/${briefingId}/edit`)
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Never"
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return "Just now"
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "bg-green-100 text-green-800"
      case "paused":
        return "bg-yellow-100 text-yellow-800"
      case "error":
        return "bg-red-100 text-red-800"
      default:
        return "bg-gray-100 text-gray-800"
    }
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-border p-6 flex items-center justify-between animate-in fade-in slide-in-from-top duration-300">
        <div>
          <h1 className="text-3xl font-bold">My Briefings</h1>
          <p className="text-muted-foreground mt-1">Manage your summarization logic before assigning them to campaigns</p>
        </div>
        <Button
          onClick={() => (window.location.href = "/dashboard/create")}
          className="transition-all duration-200 hover:shadow-md"
        >
          + Create New Briefing
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : briefings.length === 0 ? (
          <Card className="border-dashed animate-in fade-in duration-300">
            <CardContent className="flex flex-col items-center justify-center py-12">
              <div className="text-6xl mb-4 animate-in scale-in duration-300">📋</div>
              <h3 className="text-lg font-semibold mb-2">No briefings yet</h3>
              <p className="text-muted-foreground mb-6">Create your first briefing to start assembling campaigns</p>
              <Button onClick={() => (window.location.href = "/dashboard/create")}>Create Your First Briefing</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {briefings.map((briefing, index) => (
              <Card
                key={briefing.id}
                className={`hover:shadow-md transition-all duration-300 animate-in fade-in slide-in-from-top ${
                  deletingId === briefing.id ? "opacity-0 scale-95" : ""
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold text-lg">{briefing.name}</h3>
                        <Badge className={`${getStatusColor(briefing.status)} transition-all duration-200`}>
                          {briefing.status.charAt(0).toUpperCase() + briefing.status.slice(1)}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
                        {briefing.description || briefing.prompt.slice(0, 100) + "..."}
                      </p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Primary Source</p>
                          <p className="font-medium truncate">{briefing.seed_links[0] || "No sources"}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Last Run</p>
                          <p className="font-medium">{formatDate(briefing.last_run_at)}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-muted-foreground">Sources</p>
                          <p className="font-medium">{briefing.seed_links.length} link(s)</p>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => runBriefing(briefing.id, briefing.name)}
                        disabled={runningId === briefing.id}
                        title="Run Now"
                        className="transition-all duration-200 hover:bg-muted"
                      >
                        {runningId === briefing.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RefreshCw className="w-4 h-4" />
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => viewBriefingSummary(briefing)}
                        title="View Summary"
                        className="transition-all duration-200 hover:bg-muted bg-transparent"
                      >
                        <Eye className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => editBriefing(briefing.id)}
                        title="Edit"
                        className="transition-all duration-200 hover:bg-muted bg-transparent"
                      >
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleStatus(briefing.id, briefing.status)}
                        title={briefing.status === "active" ? "Pause" : "Resume"}
                        className="transition-all duration-200 hover:bg-muted"
                      >
                        {briefing.status === "active" ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => deleteBriefing(briefing.id)}
                        title="Delete"
                        className="text-destructive hover:text-destructive transition-all duration-200 hover:bg-destructive/10"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>{selectedBriefing?.name} - Summary Preview</span>
            </DialogTitle>
            <DialogDescription>
              {summaryPreview && (
                <span className="text-xs">
                  Generated on {new Date(summaryPreview.created_at).toLocaleString()}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {previewLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          ) : summaryPreview ? (
            <div className="space-y-6 text-foreground">
              {/* Bullet Points */}
              <div className="bg-card p-4 rounded-lg border border-border">
                <h3 className="font-semibold text-lg mb-3 text-foreground">Key Points</h3>
                <ul className="space-y-2">
                  {summaryPreview.bullet_points.map((point, index) => (
                    <li key={index} className="flex gap-2">
                      <span className="text-muted-foreground">•</span>
                      <span className="flex-1 text-sm text-foreground">{point}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Full Summary */}
              <div className="bg-card p-4 rounded-lg border border-border">
                <h3 className="font-semibold text-lg mb-3 text-foreground">Full Summary</h3>
                <div 
                  className="prose prose-sm max-w-none text-foreground"
                  dangerouslySetInnerHTML={{ 
                    __html: summaryPreview.summary_markdown
                      .replace(/\n/g, '<br />')
                      .replace(/## (.*?)(<br \/>|$)/g, '<h3 class="font-semibold mt-4 mb-2 text-foreground">$1</h3>')
                      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                      .replace(/\[(.*?)\]/g, '<sup class="text-blue-600">$1</sup>')
                  }}
                />
              </div>

              {/* Citations */}
              {summaryPreview.citations && summaryPreview.citations.length > 0 && (
                <div className="bg-card p-4 rounded-lg border border-border">
                  <h3 className="font-semibold text-lg mb-3 text-foreground">Citations</h3>
                  <div className="space-y-2">
                    {summaryPreview.citations.map((citation, index) => (
                      <div key={index} className="text-sm text-foreground">
                        <span className="text-blue-600 font-medium">{citation.label || `[${index + 1}]`}</span>
                        {" "}
                        {citation.title && <span className="font-medium">{citation.title}</span>}
                        {" - "}
                        <a 
                          href={citation.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline break-all"
                        >
                          {citation.url}
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              No summary available
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
