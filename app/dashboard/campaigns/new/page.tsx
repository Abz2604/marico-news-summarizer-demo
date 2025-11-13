"use client"

import { useMemo, useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { SelectBriefingRow } from "@/components/forms/select-briefing-row"
import { DeliveryTimeRow } from "@/components/forms/delivery-time-row"
import { Mail, Layers, ArrowLeft, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { apiClient, type Briefing } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"

interface BriefingSelection {
  id: string
}

interface TimeSelection {
  id: string
  time: string
}

const generateId = () => Math.random().toString(36).slice(2, 9)

export default function NewCampaignPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [name, setName] = useState("Untitled Campaign")
  const [description, setDescription] = useState("")
  const [recipientInput, setRecipientInput] = useState("")
  const [briefings, setBriefings] = useState<BriefingSelection[]>([{ id: "" }])
  const [times, setTimes] = useState<TimeSelection[]>([
    { id: generateId(), time: "09:00" },
  ])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isSaving, setIsSaving] = useState(false)
  const [loadingBriefings, setLoadingBriefings] = useState(true)
  const [availableBriefings, setAvailableBriefings] = useState<Briefing[]>([])
  const hasLoadedBriefingsRef = useRef(false)

  // Load real briefings from API - prevent duplicate calls from React StrictMode
  useEffect(() => {
    if (hasLoadedBriefingsRef.current) return
    hasLoadedBriefingsRef.current = true
    loadBriefings()
  }, [])

  const loadBriefings = async () => {
    try {
      setLoadingBriefings(true)
      const response = await apiClient.briefings.list()
      setAvailableBriefings(response.items)
      
      // Set first briefing as default if available
      if (response.items.length > 0 && !briefings[0].id) {
        setBriefings([{ id: response.items[0].id }])
      }
    } catch (error) {
      console.error("Failed to load briefings:", error)
      toast({
        title: "Error loading briefings",
        description: "Failed to fetch briefings from server",
        variant: "destructive",
      })
    } finally {
      setLoadingBriefings(false)
    }
  }

  const validate = () => {
    const newErrors: Record<string, string> = {}
    if (!name.trim()) newErrors.name = "Campaign name is required"
    const recipients = recipientInput
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean)
    if (recipients.length === 0) newErrors.recipients = "Add at least one recipient"
    if (briefings.length === 0 || briefings.some((b) => !b.id)) newErrors.briefings = "Choose at least one briefing"
    if (times.length === 0 || times.some((t) => !t.time)) newErrors.times = "Add at least one delivery time"

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = async () => {
    if (!validate()) return
    
    try {
    setIsSaving(true)
      
      // Parse recipients
      const recipients = recipientInput
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean)
      
      // Get selected briefing IDs
      const selectedBriefingIds = briefings
        .filter(b => b.id)
        .map(b => b.id)
      
      // Create schedule description from times
      const scheduleDesc = times.length > 0 
        ? `Daily at ${times.map(t => t.time).filter(Boolean).join(", ")}`
        : "Not scheduled"
      
      // Create campaign via API
      const payload = {
        name: name.trim(),
        description: description.trim() || undefined,
        briefing_ids: selectedBriefingIds,
        recipient_emails: recipients,
        schedule_description: scheduleDesc,
        status: "active"
      }
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api"}/campaigns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        throw new Error(error.detail || "Failed to create campaign")
      }
      
      toast({
        title: "Campaign created!",
        description: `"${name}" has been saved successfully.`,
      })
      
      router.push("/dashboard/campaigns")
    } catch (error) {
      console.error("Failed to save campaign:", error)
      toast({
        title: "Error saving campaign",
        description: error instanceof Error ? error.message : "Failed to save campaign",
        variant: "destructive",
      })
    } finally {
    setIsSaving(false)
    }
  }

  const handleAddBriefing = () => {
    setBriefings([...briefings, { id: "" }])
  }

  const handleUpdateBriefing = (index: number, id: string) => {
    const next = [...briefings]
    next[index] = { id }
    setBriefings(next)
  }

  const handleRemoveBriefing = (index: number) => {
    setBriefings(briefings.filter((_, idx) => idx !== index))
  }

  const handleAddTime = () => {
    setTimes([...times, { id: generateId(), time: "" }])
  }

  const handleUpdateTime = (id: string, time: string) => {
    setTimes(times.map((slot) => (slot.id === id ? { ...slot, time } : slot)))
  }

  const handleRemoveTime = (id: string) => {
    setTimes(times.filter((slot) => slot.id !== id))
  }

  return (
    <div className="flex-1 flex flex-col p-6 gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <Button variant="ghost" className="p-0 h-auto text-sm gap-2" onClick={() => router.push("/dashboard/campaigns")}> 
            <ArrowLeft className="w-4 h-4" /> Back to campaigns
          </Button>
          <h1 className="text-3xl font-semibold">Create Campaign</h1>
          <p className="text-muted-foreground text-sm">
            Bundle your saved briefings, define recipients, and choose delivery moments.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="bg-transparent" onClick={() => router.push("/dashboard/campaigns")}>Cancel</Button>
          <Button onClick={handleSave} disabled={isSaving} className="gap-2">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
            {isSaving ? "Saving" : "Save Campaign"}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle>Campaign Details</CardTitle>
            <CardDescription>Give your campaign a name and optional description.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Campaign name *</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., CXO Daily Digest" />
              {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Description</label>
              <textarea
                className="w-full px-3 py-2 border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring min-h-24 resize-none transition-all duration-200"
                placeholder="Optional context for teammates"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle>Recipients</CardTitle>
            <CardDescription>Comma separated emails that receive this campaign.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              value={recipientInput}
              onChange={(e) => setRecipientInput(e.target.value)}
              placeholder="Add recipients"
            />
            <p className="text-xs text-muted-foreground">Tip: paste from your CRM or type manually.</p>
            {errors.recipients && <p className="text-sm text-destructive">{errors.recipients}</p>}
            <div className="flex flex-wrap gap-2 pt-2">
              {recipientInput
                .split(",")
                .map((r) => r.trim())
                .filter(Boolean)
                .slice(0, 6)
                .map((recipient) => (
                  <Badge key={recipient} variant="secondary" className="capitalize">
                    {recipient}
                  </Badge>
                ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Briefings</CardTitle>
          <CardDescription>Select which saved briefings roll up into this campaign.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            {briefings.map((briefing, index) => (
              <SelectBriefingRow
                key={index}
                value={briefing.id}
                onChange={(id) => handleUpdateBriefing(index, id)}
                onRemove={() => handleRemoveBriefing(index)}
                briefs={availableBriefings}
                disableRemove={briefings.length === 1}
              />
            ))}
          </div>
          <Button variant="outline" className="bg-transparent" onClick={handleAddBriefing}>
            Add another briefing
          </Button>
          {errors.briefings && <p className="text-sm text-destructive">{errors.briefings}</p>}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Delivery times</CardTitle>
          <CardDescription>Choose when campaign emails should be sent.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            {times.map((slot) => (
              <DeliveryTimeRow
                key={slot.id}
                value={slot.time}
                onChange={(time) => handleUpdateTime(slot.id, time)}
                onRemove={() => handleRemoveTime(slot.id)}
                disableRemove={times.length === 1}
              />
            ))}
          </div>
          <Button variant="outline" className="bg-transparent" onClick={handleAddTime}>
            Add another time slot
          </Button>
          {errors.times && <p className="text-sm text-destructive">{errors.times}</p>}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Summary</CardTitle>
          <CardDescription>Quick preview of your configuration.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">Briefings included</p>
            <div className="flex flex-wrap gap-2">
              {briefings.map((briefing, index) => {
                const briefingData = availableBriefings.find((b) => b.id === briefing.id)
                if (!briefingData) return (
                  <Badge key={`briefing-${index}`} variant="outline">
                    Select briefing
                  </Badge>
                )
                return (
                  <Badge key={briefingData.id} variant="outline" className="gap-1">
                    <Layers className="w-3 h-3" />
                    {briefingData.name}
                  </Badge>
                )
              })}
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">Planned sends</p>
            <div className="flex flex-wrap gap-2">
              {times.map((slot) => (
                <Badge key={slot.id} variant="outline" className={cn(!slot.time && "opacity-50")}> 
                  {slot.time || "Select time"}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
        <CardFooter className="text-xs text-muted-foreground">
          Deliveries happen in the campaign timezone from settings. Mailer integration coming soon.
        </CardFooter>
      </Card>
    </div>
  )
}

