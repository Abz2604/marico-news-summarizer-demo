"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter, useParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCircle, Loader2, ArrowLeft } from "lucide-react"
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
  const [url, setUrl] = useState("")
  const [prompt, setPrompt] = useState("")
  const [errors, setErrors] = useState<Record<string, string>>({})
  const hasLoadedRef = useRef<string | null>(null)

  useEffect(() => {
    if (briefingId && hasLoadedRef.current !== briefingId) {
      hasLoadedRef.current = briefingId
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
      // Use first seed link as URL (or empty if none)
      setUrl(b.seed_links && b.seed_links.length > 0 ? b.seed_links[0] : "")
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

    if (!url.trim()) {
      newErrors.url = "URL is required"
    } else {
      try {
        new URL(url)
      } catch {
        newErrors.url = "Please enter a valid URL"
      }
    }

    if (!prompt.trim()) {
      newErrors.prompt = "Prompt is required"
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = async () => {
    if (!validateForm()) return

    try {
      setSaving(true)

      await apiClient.briefings.update(briefingId, {
        name: name.trim(),
        description: description.trim() || undefined,
        prompt: prompt.trim(),
        seed_links: [url.trim()], // Single URL as array
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

  const isFormValid = name.trim() && url.trim() && prompt.trim()

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
            disabled={!isFormValid || saving}
            className="transition-all duration-200 hover:shadow-md"
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
        <Card className="h-fit shadow-sm hover:shadow-md transition-shadow duration-300">
          <CardHeader>
            <CardTitle>Edit Briefing</CardTitle>
            <CardDescription>Update your automated daily summary</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Name Field */}
            <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300">
              <label className="text-sm font-medium">Briefing Name *</label>
              <Input
                type="text"
                placeholder="e.g., Daily Tech News"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (errors.name) setErrors({ ...errors, name: "" })
                }}
                className="transition-all duration-200 focus:ring-2"
              />
              {errors.name && (
                <div className="flex gap-2 text-sm text-destructive animate-in fade-in duration-200">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{errors.name}</span>
                </div>
              )}
            </div>

            {/* Description Field */}
            <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300" style={{ animationDelay: "25ms" }}>
              <label className="text-sm font-medium">Description (Optional)</label>
              <Input
                type="text"
                placeholder="Brief description of what this briefing covers..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="transition-all duration-200 focus:ring-2"
              />
            </div>

            {/* URL Field */}
            <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300" style={{ animationDelay: "50ms" }}>
              <label className="text-sm font-medium">Listing Page URL *</label>
              <p className="text-xs text-muted-foreground">
                Provide a listing page URL (news section, blog category, forum board, etc.) for optimal performance
              </p>
              <Input
                type="url"
                placeholder="e.g., https://company.com/news or https://blog.com/category/tech"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  if (errors.url) setErrors({ ...errors, url: "" })
                }}
                className="transition-all duration-200 focus:ring-2"
              />
              {errors.url && (
                <div className="flex gap-2 text-sm text-destructive animate-in fade-in duration-200">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{errors.url}</span>
                </div>
              )}
            </div>

            {/* Prompt Field */}
            <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300" style={{ animationDelay: "75ms" }}>
              <label className="text-sm font-medium">Insight Prompt *</label>
              <p className="text-xs text-muted-foreground">
                What insights or information are you looking for?
              </p>
              <textarea
                placeholder="e.g., Summarize discussions about the company in the last month, or Find recent product launches and market reactions"
                value={prompt}
                onChange={(e) => {
                  setPrompt(e.target.value)
                  if (errors.prompt) setErrors({ ...errors, prompt: "" })
                }}
                className="w-full px-3 py-2 border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring min-h-24 resize-none transition-all duration-200"
              />
              {errors.prompt && (
                <div className="flex gap-2 text-sm text-destructive animate-in fade-in duration-200">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{errors.prompt}</span>
                </div>
              )}
            </div>

            {/* Prompting Guide */}
            <div className="mt-6 p-4 bg-muted/50 rounded-lg border border-border space-y-3 animate-in fade-in slide-in-from-top duration-300" style={{ animationDelay: "300ms" }}>
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                💡 Tips for Writing Effective Prompts
              </h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex gap-2">
                  <span className="text-primary font-semibold flex-shrink-0">•</span>
                  <span><strong>Be specific:</strong> Mention the number of items you want (e.g., "Top 5 stories" instead of "Some stories")</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary font-semibold flex-shrink-0">•</span>
                  <span><strong>Define the format:</strong> Specify if you want bullet points, paragraphs, or a particular structure</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary font-semibold flex-shrink-0">•</span>
                  <span><strong>Set the focus:</strong> Mention specific topics, themes, or angles you're interested in</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary font-semibold flex-shrink-0">•</span>
                  <span><strong>Include context:</strong> Add details about your audience or use case for more tailored summaries</span>
                </li>
              </ul>
              
              <div className="pt-2 border-t border-border space-y-2">
                <p className="text-xs font-semibold text-foreground">Examples:</p>
                <div className="space-y-2">
                  <div className="p-2 bg-background rounded border border-border">
                    <p className="text-xs text-foreground italic">"Summarize the top 5 tech industry news stories in bullet points, focusing on AI and machine learning developments"</p>
                  </div>
                  <div className="p-2 bg-background rounded border border-border">
                    <p className="text-xs text-foreground italic">"Create a brief 3-point summary of recent market updates relevant to retail investors, with emphasis on stock movements"</p>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
