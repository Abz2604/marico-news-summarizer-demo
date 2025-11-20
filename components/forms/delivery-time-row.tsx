"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Trash2, ChevronDown } from "lucide-react"
import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"

interface DeliveryTimeRowProps {
  value: string
  onChange: (value: string) => void
  onRemove: () => void
  disableRemove?: boolean
}

export function DeliveryTimeRow({ value, onChange, onRemove, disableRemove }: DeliveryTimeRowProps) {
  // Parse initial value
  // Formats: "09:00" (Daily), "Weekly on Mon 09:00", "Weekly on Mon,Wed 09:00", "Weekdays at 09:00"
  const parseValue = (val: string) => {
    if (!val) return { type: "daily", days: ["mon"], time: "" }
    
    const lowerVal = val.toLowerCase()
    
    if (lowerVal.includes("weekly on")) {
        // "Weekly on Mon, Wed 09:00" or "Weekly on Mon, Wed at 09:00"
        const clean = lowerVal.replace("weekly on", "").trim()
        
        let time = ""
        let daysStr = ""
        
        if (clean.includes(" at ")) {
            const parts = clean.split(" at ")
            daysStr = parts[0].trim()
            time = parts[1].trim()
        } else {
            // Fallback: assume last part is time
            const parts = clean.split(" ")
            time = parts[parts.length - 1]
            daysStr = clean.substring(0, clean.lastIndexOf(" ")).trim()
        }
        
        const days = daysStr.split(",").map(d => d.trim().substring(0, 3)) // Normalize to mon, tue etc
        return { type: "weekly", days, time }
    } else if (lowerVal.includes("weekdays")) {
        // "Weekdays at 09:00"
        let time = ""
        if (lowerVal.includes(" at ")) {
            time = lowerVal.split(" at ")[1].trim()
        } else {
            time = lowerVal.replace("weekdays", "").trim()
        }
        return { type: "weekdays", days: ["mon", "tue", "wed", "thu", "fri"], time }
    } else if (lowerVal.includes("daily")) {
         let time = ""
         if (lowerVal.includes(" at ")) {
             time = lowerVal.split(" at ")[1].trim()
         } else {
             time = lowerVal.replace("daily", "").trim()
         }
         return { type: "daily", days: ["mon"], time }
    } else {
        // "09:00" or empty -> treat as daily for backward compat, or just time
        // If it looks like just a time "HH:MM", treat as Daily
        return { type: "daily", days: ["mon"], time: val.replace("Daily at ", "").replace("Daily ", "") }
    }
  }

  const [state, setState] = useState(parseValue(value))
  
  // Sync local state when prop changes (if different)
  useEffect(() => {
    const parsed = parseValue(value)
    // Simple equality check to avoid infinite loops
    if (parsed.time !== state.time || parsed.type !== state.type || JSON.stringify(parsed.days) !== JSON.stringify(state.days)) {
        setState(parsed)
    }
  }, [value])

  const updateValue = (newState: typeof state) => {
    setState(newState)
    
    if (!newState.time) {
        onChange("") // Incomplete
        return
    }

    if (newState.type === "daily") {
        onChange(`Daily at ${newState.time}`)
    } else if (newState.type === "weekdays") {
        onChange(`Weekdays at ${newState.time}`)
    } else {
        // Weekly
        // Capitalize days
        const daysStr = newState.days.map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(", ")
        onChange(`Weekly on ${daysStr} at ${newState.time}`)
    }
  }

  const handleTypeChange = (type: string) => {
    // Reset days if switching to weekly
    let newDays = state.days
    if (type === "weekly" && state.type !== "weekly") {
        newDays = ["mon"]
    }
    updateValue({ ...state, type, days: newDays })
  }

  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateValue({ ...state, time: e.target.value })
  }

  const toggleDay = (day: string) => {
    let newDays = [...state.days]
    if (newDays.includes(day)) {
        if (newDays.length > 1) {
            newDays = newDays.filter(d => d !== day)
        }
    } else {
        newDays.push(day)
    }
    
    // Sort days for consistency (Mon=0..Sun=6)
    const dayOrder = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    newDays.sort((a, b) => dayOrder.indexOf(a) - dayOrder.indexOf(b))
    
    updateValue({ ...state, days: newDays })
  }

  const days = [
    { id: "mon", label: "M" },
    { id: "tue", label: "T" },
    { id: "wed", label: "W" },
    { id: "thu", label: "T" },
    { id: "fri", label: "F" },
    { id: "sat", label: "S" },
    { id: "sun", label: "S" },
  ]

  return (
    <div className="flex flex-col gap-2 p-3 border border-border rounded-md bg-card/50">
      <div className="flex items-center gap-3">
        <div className="relative w-[140px]">
          <select
            value={state.type}
            onChange={(e) => handleTypeChange(e.target.value)}
            className={cn(
              "flex h-10 w-full appearance-none items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
              "bg-white dark:bg-zinc-950" // Force background opacity
            )}
          >
            <option value="daily">Daily</option>
            <option value="weekdays">Weekdays</option>
            <option value="weekly">Weekly</option>
          </select>
          {/* <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 opacity-50 pointer-events-none" /> */}
        </div>

        <Input
            type="time"
            value={state.time}
            onChange={handleTimeChange}
            className="w-[140px] bg-white dark:bg-zinc-950"
        />

        <Button
            variant="ghost"
            size="icon"
            onClick={onRemove}
            disabled={disableRemove}
            className="ml-auto text-muted-foreground hover:text-destructive"
        >
            <Trash2 className="w-4 h-4" />
        </Button>
      </div>

      {state.type === "weekly" && (
        <div className="flex gap-1 mt-1">
            {days.map((day) => (
                <button
                    key={day.id}
                    type="button"
                    onClick={() => toggleDay(day.id)}
                    className={`
                        w-8 h-8 rounded-full text-xs font-medium transition-colors
                        ${state.days.includes(day.id) 
                            ? "bg-primary text-primary-foreground" 
                            : "bg-muted text-muted-foreground hover:bg-muted/80"}
                    `}
                    title={day.id}
                >
                    {day.label}
                </button>
            ))}
        </div>
      )}
    </div>
  )
}
