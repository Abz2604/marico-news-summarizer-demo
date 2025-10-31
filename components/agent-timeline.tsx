"use client"

interface TimelineStep {
  name: string
  status: "pending" | "active" | "complete" | "error"
  timestamp?: string
  details?: string
}

interface AgentTimelineProps {
  steps: TimelineStep[]
}

export function AgentTimeline({ steps }: AgentTimelineProps) {
  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <div key={i} className="flex items-start gap-3 group animate-in fade-in slide-in-from-left-2 duration-300" style={{ animationDelay: `${i * 50}ms` }}>
          {/* Status indicator */}
          <div className="relative">
            <div
              className={`
              w-4 h-4 rounded-full mt-0.5 transition-all duration-300
              ${step.status === "complete" && "bg-green-500 scale-110"}
              ${step.status === "active" && "bg-blue-500 animate-pulse shadow-lg shadow-blue-500/50"}
              ${step.status === "pending" && "bg-gray-300 dark:bg-gray-700"}
              ${step.status === "error" && "bg-red-500 scale-110"}
            `}
            />
            {step.status === "active" && (
              <div className="absolute inset-0 w-4 h-4 rounded-full bg-blue-500 animate-ping opacity-75" />
            )}
          </div>

          {/* Connecting line (except for last item) */}
          {i < steps.length - 1 && (
            <div
              className={`
              absolute left-[7px] top-6 w-0.5 h-6 transition-colors duration-300
              ${step.status === "complete" ? "bg-green-500/30" : "bg-gray-300 dark:bg-gray-700"}
            `}
            />
          )}

          {/* Step info */}
          <div className="flex-1 pb-1">
            <p
              className={`
              text-sm font-medium transition-colors duration-300
              ${step.status === "active" && "text-blue-600 dark:text-blue-400"}
              ${step.status === "complete" && "text-green-600 dark:text-green-400"}
              ${step.status === "error" && "text-red-600 dark:text-red-400"}
              ${step.status === "pending" && "text-muted-foreground"}
            `}
            >
              {step.name}
            </p>

            {step.details && (
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{step.details}</p>
            )}

            {step.timestamp && (
              <p className="text-xs text-muted-foreground/70 mt-0.5">{step.timestamp}</p>
            )}
          </div>

          {/* Status icon */}
          {step.status === "complete" && <span className="text-green-500 text-sm">✓</span>}
          {step.status === "error" && <span className="text-red-500 text-sm">✗</span>}
        </div>
      ))}
    </div>
  )
}

