"use client"

import { useMemo, useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { apiClient, type Campaign } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Layers, Mail, Users2, Clock, Filter, Loader2, RefreshCw } from "lucide-react"
import { useToast } from "@/hooks/use-toast"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"

const STATUS_COLOR: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  draft: "bg-blue-100 text-blue-800",
  paused: "bg-yellow-100 text-yellow-800",
}

const CAMPAIGN_FILTERS = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Draft", value: "draft" },
  { label: "Paused", value: "paused" },
]

export default function CampaignsPage() {
  const [filter, setFilter] = useState("all")
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [previewEmail, setPreviewEmail] = useState("")
  const [sending, setSending] = useState(false)
  const router = useRouter()
  const { toast } = useToast()

  // Fetch campaigns from API
  useEffect(() => {
    loadCampaigns()
  }, [])

  const loadCampaigns = async () => {
    try {
      setLoading(true)
      const response = await apiClient.campaigns.list()
      setCampaigns(response.items)
    } catch (error) {
      console.error("Failed to load campaigns:", error)
      toast({
        title: "Error loading campaigns",
        description: error instanceof Error ? error.message : "Failed to fetch campaigns from server",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  const handlePreview = async (campaign: Campaign) => {
    try {
      setSelectedCampaign(campaign)
      setPreviewOpen(true)
      setPreviewLoading(true)
      setPreviewHtml(null)

      const preview = await apiClient.campaigns.preview(campaign.id)

      if (preview.status === "not_ready") {
        toast({
          title: "Preview Not Available",
          description: preview.message || "Run the briefings first to generate content",
          variant: "destructive",
        })
        setPreviewOpen(false)
      } else {
        setPreviewHtml(preview.html)
        if (preview.status === "partial") {
          toast({
            title: "Partial Preview",
            description: preview.message || "Some briefings are missing summaries",
          })
        }
      }
    } catch (error) {
      console.error("Failed to preview campaign:", error)
      toast({
        title: "Preview Error",
        description: error instanceof Error ? error.message : "Failed to generate preview",
        variant: "destructive",
      })
      setPreviewOpen(false)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSendPreview = async () => {
    if (!previewEmail.trim()) {
      toast({
        title: "Email required",
        description: "Please enter an email address",
        variant: "destructive",
      })
      return
    }

    if (!selectedCampaign) return

    try {
      setSending(true)
      
      // Send preview to the specified email
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/campaigns/${selectedCampaign.id}/send-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_email: previewEmail.trim() }),
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        throw new Error(error.detail || "Failed to send preview")
      }

      toast({
        title: "Preview sent!",
        description: `Email sent to ${previewEmail}`,
      })

      setPreviewEmail("")
    } catch (error) {
      console.error("Failed to send preview:", error)
      toast({
        title: "Send failed",
        description: error instanceof Error ? error.message : "Failed to send preview email",
        variant: "destructive",
      })
    } finally {
      setSending(false)
    }
  }

  const filteredCampaigns = useMemo(() => {
    if (filter === "all") return campaigns
    return campaigns.filter((campaign) => campaign.status === filter)
  }, [campaigns, filter])

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Never"
    const date = new Date(dateString)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000)
    
    if (diffDays < 1) return "Today"
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-border p-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold">Campaigns</h1>
          <p className="text-muted-foreground mt-1">Bundle briefings into scheduled email sends</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground border border-border rounded-md px-4 py-2">
            <Filter className="w-4 h-4" />
            <div className="flex gap-2">
              {CAMPAIGN_FILTERS.map((item) => (
                <button
                  key={item.value}
                  onClick={() => setFilter(item.value)}
                  className={`transition-colors ${filter === item.value ? "text-foreground font-medium" : "hover:text-foreground"}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <Button className="gap-2" onClick={() => router.push("/dashboard/campaigns/new")}>New Campaign</Button>
        </div>
      </div>

      <div className="flex-1 p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center gap-3">
              <Layers className="w-12 h-12 text-muted-foreground" />
              <h3 className="text-lg font-semibold">No campaigns yet</h3>
              <p className="text-muted-foreground max-w-sm">
                Combine briefings and schedule delivery times to keep your stakeholders informed on a single stream.
              </p>
              <Button onClick={() => router.push("/dashboard/campaigns/new")}>Create your first campaign</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredCampaigns.map((campaign, index) => (
              <Card
                key={campaign.id}
                className="hover:shadow-md transition-all duration-300 animate-in fade-in slide-in-from-top"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="p-6 flex flex-col h-full gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold">{campaign.name}</h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        {campaign.description || "No description"}
                      </p>
                    </div>
                    <Badge className={`${STATUS_COLOR[campaign.status]} capitalize`}>{campaign.status}</Badge>
                  </div>

                  <div className="space-y-3 text-sm">
                    <div className="flex items-start gap-3">
                      <Layers className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Briefings</p>
                        <p className="text-muted-foreground leading-relaxed">
                          {campaign.briefing_ids.length > 0 
                            ? `${campaign.briefing_ids.length} briefing(s)` 
                            : "No briefings selected"}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <Users2 className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Recipients</p>
                        <p className="text-muted-foreground leading-relaxed truncate">
                          {campaign.recipient_emails.length > 0 
                            ? campaign.recipient_emails.slice(0, 2).join(", ") + 
                              (campaign.recipient_emails.length > 2 ? "..." : "")
                            : "Add recipients to start sending"}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <Clock className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Schedule</p>
                        <p className="text-muted-foreground leading-relaxed">
                          {campaign.schedule_description || "Not scheduled"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-auto flex items-center justify-between pt-4 border-t border-border">
                    <Button 
                      variant="outline" 
                      className="bg-transparent gap-2" 
                      size="sm"
                      onClick={() => handlePreview(campaign)}
                    >
                      <Mail className="w-4 h-4" />
                      Preview Email
                    </Button>
                    <Button variant="ghost" size="sm" className="hover:bg-muted">Manage</Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="!max-w-6xl !h-[90vh] !flex !flex-col !p-0 !bg-background !overflow-hidden">
          <DialogHeader className="px-6 pt-6 pb-4 border-b border-border flex-shrink-0 bg-background">
            <DialogTitle className="text-foreground">{selectedCampaign?.name} - Email Preview</DialogTitle>
            <DialogDescription>
              Review how your email will look to recipients
            </DialogDescription>
          </DialogHeader>

          {previewLoading ? (
            <div className="flex flex-col items-center justify-center py-12 flex-1 bg-background">
              <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
              <p className="text-sm text-foreground font-medium">Loading preview...</p>
              <p className="text-xs text-muted-foreground mt-1">Please wait</p>
            </div>
          ) : previewHtml ? (
            <div style={{ flex: '1 1 0px', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
              {/* Scrollable Content Area */}
              <div style={{ flex: '1 1 0px', overflowY: 'scroll', minHeight: '550px' }} className="px-6 py-4">
                {/* HTML Preview */}
                <div className="border-2 border-border rounded-lg shadow-sm mb-4">
                  <div 
                    className="p-6 bg-white dark:bg-gray-50"
                    style={{ 
                      fontFamily: 'system-ui, -apple-system, sans-serif',
                      color: '#000000'
                    }}
                    dangerouslySetInnerHTML={{ __html: previewHtml }}
                  />
                </div>
              </div>

              {/* Send Preview Section - Fixed at bottom */}
              <div className="flex-shrink-0 px-6 py-4 border-t border-border bg-background">
                <label className="text-sm font-medium text-foreground block mb-2">Send test email to:</label>
                <div className="flex gap-2">
                  <Input
                    type="email"
                    placeholder="your.email@example.com"
                    value={previewEmail}
                    onChange={(e) => setPreviewEmail(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === "Enter") {
                        handleSendPreview()
                      }
                    }}
                    className="bg-background"
                  />
                  <Button 
                    onClick={handleSendPreview}
                    disabled={sending || !previewEmail.trim()}
                    className="gap-2 shrink-0"
                  >
                    {sending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Sending...
                      </>
                    ) : (
                      <>
                        <Mail className="w-4 h-4" />
                        Send Preview
                      </>
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Send a test email to verify how it looks in your inbox
                </p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center bg-background">
              <div className="text-center py-12 text-muted-foreground">
                <Mail className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No preview available</p>
              </div>
            </div>
          )}

          <DialogFooter className="px-6 py-4 border-t border-border flex-shrink-0 bg-background">
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

