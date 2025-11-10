"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCircle, Loader2 } from "lucide-react"
import { apiClient } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"
import { useRouter } from "next/navigation"

interface BriefingData {
  url: string
  prompt: string
}

interface CreateBriefingFormProps {
  onBriefingChange: (data: BriefingData | null) => void
  onSave: (data: BriefingData, message: string) => void
}

export function CreateBriefingForm({ onBriefingChange, onSave }: CreateBriefingFormProps) {
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [prompt, setPrompt] = useState("")
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isDemoLoading, setIsDemoLoading] = useState(false)
  const { toast } = useToast()
  const router = useRouter()

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

  const handleGenerateDemo = async () => {
    if (validateForm()) {
      setIsDemoLoading(true)
      await new Promise((resolve) => setTimeout(resolve, 500))
      const data: BriefingData = {
        url,
        prompt,
      }
      onBriefingChange(data)
      setIsDemoLoading(false)
    }
  }

  const handleSave = async () => {
    if (validateForm()) {
      setIsLoading(true)
      
      try {
        // Call the actual API to save the briefing
        const briefing = await apiClient.briefings.create({
          name: name.trim(),
          prompt: prompt.trim(),
          seed_links: [url.trim()],
          description: `Briefing for ${url.trim()}`
        })

      const data: BriefingData = {
        url,
        prompt,
      }

        const message = `✅ Briefing "${briefing.name}" saved successfully! Add it to a campaign to start sending.`
      onSave(data, message)

        // Show success toast
        toast({
          title: "Briefing created!",
          description: `"${briefing.name}" has been saved to the database.`,
        })

      // Reset form
        setName("")
      setUrl("")
      setPrompt("")
      setErrors({})
      onBriefingChange(null)

        // Redirect to briefings page after a short delay
        setTimeout(() => {
          router.push("/dashboard/briefings")
        }, 1500)

      } catch (error) {
        console.error("Failed to save briefing:", error)
        toast({
          title: "Error saving briefing",
          description: error instanceof Error ? error.message : "Failed to save briefing to database",
          variant: "destructive",
        })
      } finally {
      setIsLoading(false)
      }
    }
  }

  const isFormValid = name.trim() && url.trim() && prompt.trim()

  return (
    <Card className="h-fit shadow-sm hover:shadow-md transition-shadow duration-300">
      <CardHeader>
        <CardTitle>Create Briefing</CardTitle>
        <CardDescription>Set up a new automated daily summary</CardDescription>
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

        {/* Action Buttons */}
        <div
          className="space-y-2 pt-4 animate-in fade-in slide-in-from-top duration-300"
          style={{ animationDelay: "200ms" }}
        >
          <Button
            onClick={handleGenerateDemo}
            variant="outline"
            className="w-full bg-transparent transition-all duration-200 hover:bg-muted"
            disabled={!isFormValid || isDemoLoading}
          >
            {isDemoLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Generating...
              </>
            ) : (
              "Generate Demo Summary"
            )}
          </Button>
          <Button
            onClick={handleSave}
            className="w-full transition-all duration-200 hover:shadow-md"
            disabled={!isFormValid || isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Briefing"
            )}
          </Button>
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
  )
}
