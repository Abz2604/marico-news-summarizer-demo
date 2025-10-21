"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCircle, Loader2 } from "lucide-react"

interface BriefingData {
  url: string
  prompt: string
  recipientEmails: string[]
  deliveryTime: string
}

interface CreateBriefingFormProps {
  onBriefingChange: (data: BriefingData | null) => void
  onSave: (data: BriefingData, message: string) => void
}

export function CreateBriefingForm({ onBriefingChange, onSave }: CreateBriefingFormProps) {
  const [url, setUrl] = useState("")
  const [prompt, setPrompt] = useState("")
  const [emails, setEmails] = useState("")
  const [deliveryTime, setDeliveryTime] = useState("09:00")
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isDemoLoading, setIsDemoLoading] = useState(false)

  const validateForm = () => {
    const newErrors: Record<string, string> = {}

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

    if (!emails.trim()) {
      newErrors.emails = "At least one email is required"
    } else {
      const emailList = emails.split(",").map((e) => e.trim())
      const invalidEmails = emailList.filter((e) => !e.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/))
      if (invalidEmails.length > 0) {
        newErrors.emails = "One or more emails are invalid"
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleGenerateDemo = async () => {
    if (validateForm()) {
      setIsDemoLoading(true)
      await new Promise((resolve) => setTimeout(resolve, 500))
      const emailList = emails.split(",").map((e) => e.trim())
      const data: BriefingData = {
        url,
        prompt,
        recipientEmails: emailList,
        deliveryTime,
      }
      onBriefingChange(data)
      setIsDemoLoading(false)
    }
  }

  const handleSave = async () => {
    if (validateForm()) {
      setIsLoading(true)
      const emailList = emails.split(",").map((e) => e.trim())
      const data: BriefingData = {
        url,
        prompt,
        recipientEmails: emailList,
        deliveryTime,
      }

      // Simulate API call
      await new Promise((resolve) => setTimeout(resolve, 1000))

      const message = `✅ Daily email scheduled for ${deliveryTime} IST to ${emailList.join(", ")}. First send: ${new Date().toLocaleString()}.`
      onSave(data, message)

      // Reset form
      setUrl("")
      setPrompt("")
      setEmails("")
      setDeliveryTime("09:00")
      setErrors({})
      onBriefingChange(null)

      setIsLoading(false)
    }
  }

  const isFormValid = url.trim() && prompt.trim() && emails.trim()

  return (
    <Card className="h-fit shadow-sm hover:shadow-md transition-shadow duration-300">
      <CardHeader>
        <CardTitle>Create Briefing</CardTitle>
        <CardDescription>Set up a new automated daily summary</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* URL Field */}
        <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300">
          <label className="text-sm font-medium">News Source URL *</label>
          <Input
            type="url"
            placeholder="https://example.com/news"
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
        <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300" style={{ animationDelay: "50ms" }}>
          <label className="text-sm font-medium">Summary Prompt *</label>
          <textarea
            placeholder="e.g., Summarize the top 5 tech news stories in bullet points"
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

        {/* Recipient Emails */}
        <div
          className="space-y-2 animate-in fade-in slide-in-from-top duration-300"
          style={{ animationDelay: "100ms" }}
        >
          <label className="text-sm font-medium">Recipient Email(s) *</label>
          <Input
            type="text"
            placeholder="email@example.com, another@example.com"
            value={emails}
            onChange={(e) => {
              setEmails(e.target.value)
              if (errors.emails) setErrors({ ...errors, emails: "" })
            }}
            className="transition-all duration-200 focus:ring-2"
          />
          <p className="text-xs text-muted-foreground">Separate multiple emails with commas</p>
          {errors.emails && (
            <div className="flex gap-2 text-sm text-destructive animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{errors.emails}</span>
            </div>
          )}
        </div>

        {/* Delivery Time */}
        <div
          className="space-y-2 animate-in fade-in slide-in-from-top duration-300"
          style={{ animationDelay: "150ms" }}
        >
          <label className="text-sm font-medium">Delivery Time (IST)</label>
          <Input
            type="time"
            value={deliveryTime}
            onChange={(e) => setDeliveryTime(e.target.value)}
            className="transition-all duration-200 focus:ring-2"
          />
          <p className="text-xs text-muted-foreground">Default: 09:00 IST</p>
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
      </CardContent>
    </Card>
  )
}
