"use client"

interface AgentProgressProps {
  currentStep: string
  progress: number // 0-100
  details?: string
}

const STEP_ICONS: Record<string, string> = {
  init: "🚀",
  analyzing: "🔍",
  navigating: "🗺️",
  fetching: "📡",
  validating: "✅",
  extracting: "📄",
  deduplicating: "🔄",
  summarizing: "📝",
  complete: "🎉",
  error: "❌",
}

const STEP_LABELS: Record<string, string> = {
  init: "Starting Agent",
  analyzing: "Analyzing Page",
  navigating: "Finding Articles",
  fetching: "Fetching Content",
  validating: "Checking Quality",
  extracting: "Extracting Dates",
  deduplicating: "Removing Duplicates",
  summarizing: "Generating Summary",
  complete: "Complete",
  error: "Error",
}

export function AgentProgress({ currentStep, progress, details }: AgentProgressProps) {
  const icon = STEP_ICONS[currentStep] || "⏳"
  const label = STEP_LABELS[currentStep] || currentStep

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
        <div
          className="bg-primary h-2 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>

      {/* Current step */}
      <div className="flex items-center gap-3 animate-in fade-in duration-300">
        <span className="text-3xl animate-pulse">{icon}</span>
        <div className="flex-1">
          <p className="font-semibold text-foreground">{label}</p>
          {details && <p className="text-sm text-muted-foreground mt-1">{details}</p>}
        </div>
        <span className="text-sm font-medium text-muted-foreground">{progress}%</span>
      </div>
    </div>
  )
}

