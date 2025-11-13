"use client"

import { useState } from "react"
import { CreateBriefingForm } from "@/components/create-briefing-form"
import { DemoSummary } from "@/components/demo-summary"
import { SuccessBanner } from "@/components/success-banner"

interface BriefingData {
  url: string
  prompt: string
  useAgentV2?: boolean
}

export default function CreateBriefingPage() {
  const [briefingData, setBriefingData] = useState<BriefingData | null>(null)
  const [showSuccess, setShowSuccess] = useState(false)
  const [successMessage, setSuccessMessage] = useState("")

  const handleSave = (data: BriefingData, message: string) => {
    setSuccessMessage(message)
    setShowSuccess(true)
    setTimeout(() => setShowSuccess(false), 5000)
  }

  return (
    <div className="flex-1 flex flex-col">
      {showSuccess && <SuccessBanner message={successMessage} />}

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
        <CreateBriefingForm onBriefingChange={setBriefingData} onSave={handleSave} />
        <DemoSummary briefingData={briefingData} />
      </div>
    </div>
  )
}
