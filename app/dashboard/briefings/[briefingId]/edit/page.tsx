"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertCircle, Loader2, Plus, Trash2, ArrowLeft } from "lucide-react"
import { apiClient, type Briefing } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"

export default function EditBriefingPage() {
  const router = useRouter()
  const params = useParams()
  const briefingId = params?.briefingId as string
  const { toast } = useToast()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [prompt, setPrompt] = useState("")
  const [seedLinks, setSeedLinks] = useState<string[]>([])
  const [newLink, setNewLink] = useState("")

  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (briefingId) {
      loadBriefing()
    }
  }, [briefingId])

  const loadBriefing = async () => {
    try {
      setLoading(true)
      const response = await apiClient.briefings.get(briefingId)
      const b = response.briefing
      
      setBriefing(b)
      setName(b.name)
      setDescription(b.description || "")
      setPrompt(b.prompt)
      setSeedLinks(b.seed_links)
    } catch (error) {
      console.error("Failed to load briefing:", error)
      toast({
        title: "Error loading briefing",
        description: error instanceof Error ? error.message : "Failed to fetch briefing",
        variant: "destructive",
      })
      router.push("/dashboard/briefings")
    } finally {
      setLoading(false)
    }
  }

  const validateForm = () => {
    const newErrors: Record<string, string> = {}

    if (!name.trim()) {
      newErrors.name = "Briefing name is required"
    }

    if (!prompt.trim()) {
      newErrors.prompt = "Prompt is required"
    }

    if (seedLinks.length === 0) {
      newErrors.seedLinks = "At least one seed link is required"
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleAddLink = () => {
    if (newLink.trim()) {
      try {
        new URL(newLink)
        setSeedLinks([...seedLinks, newLink.trim()])
        setNewLink("")
        setErrors({ ...errors, seedLinks: "" })
      } catch {
        setErrors({ ...errors, newLink: "Please enter a valid URL" })
      }
    }
  }

  const handleRemoveLink = (index: number) => {
    setSeedLinks(seedLinks.filter((_, i) => i !== index))
  }

  const handleSave = async () => {
    if (!validateForm()) return

    try {
      setSaving(true)

      await apiClient.briefings.update(briefingId, {
        name: name.trim(),
        description: description.trim() || undefined,
        prompt: prompt.trim(),
        seed_links: seedLinks,
      })

      toast({
        title: "Briefing updated!",
        description: `"${name}" has been updated successfully.`,
      })

      router.push("/dashboard/briefings")
    } catch (error) {
      console.error("Failed to update briefing:", error)
      toast({
        title: "Error updating briefing",
        description: error instanceof Error ? error.message : "Failed to update briefing",
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-border p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/dashboard/briefings")}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold">Edit Briefing</h1>
            <p className="text-muted-foreground mt-1">Update your briefing configuration</p>
          </div>
        </div>
        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={() => router.push("/dashboard/briefings")}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </div>
      </div>

      {/* Form */}
      <div className="flex-1 p-6 max-w-4xl mx-auto w-full">
        <div className="space-y-6">
          {/* Name */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Briefing Name *</label>
            <Input
              type="text"
              placeholder="e.g., Daily Tech News"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (errors.name) setErrors({ ...errors, name: "" })
              }}
            />
            {errors.name && (
              <div className="flex gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{errors.name}</span>
              </div>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Description (Optional)</label>
            <Textarea
              placeholder="Brief description of what this briefing covers..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>

          {/* Prompt */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Summarization Prompt *</label>
            <Textarea
              placeholder="e.g., Summarize the latest tech news with focus on AI developments..."
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                if (errors.prompt) setErrors({ ...errors, prompt: "" })
              }}
              rows={4}
            />
            {errors.prompt && (
              <div className="flex gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{errors.prompt}</span>
              </div>
            )}
          </div>

          {/* Seed Links */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Seed Links *</label>
            <p className="text-sm text-muted-foreground">
              URLs where the agent will start gathering information
            </p>
            
            {/* Existing Links */}
            <div className="space-y-2">
              {seedLinks.map((link, index) => (
                <Card key={index}>
                  <CardContent className="p-3 flex items-center justify-between gap-2">
                    <span className="text-sm truncate flex-1">{link}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveLink(index)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Add New Link */}
            <div className="flex gap-2">
              <Input
                type="url"
                placeholder="https://example.com"
                value={newLink}
                onChange={(e) => {
                  setNewLink(e.target.value)
                  if (errors.newLink) setErrors({ ...errors, newLink: "" })
                }}
                onKeyPress={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    handleAddLink()
                  }
                }}
              />
              <Button onClick={handleAddLink} variant="outline">
                <Plus className="w-4 h-4 mr-2" />
                Add
              </Button>
            </div>

            {errors.newLink && (
              <div className="flex gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{errors.newLink}</span>
              </div>
            )}

            {errors.seedLinks && (
              <div className="flex gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{errors.seedLinks}</span>
              </div>
            )}
          </div>

          {/* Status Info */}
          {briefing && (
            <Card>
              <CardContent className="p-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Status</p>
                    <Badge className="mt-1">
                      {briefing.status.charAt(0).toUpperCase() + briefing.status.slice(1)}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Last Run</p>
                    <p className="font-medium mt-1">
                      {briefing.last_run_at 
                        ? new Date(briefing.last_run_at).toLocaleString()
                        : "Never"}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

