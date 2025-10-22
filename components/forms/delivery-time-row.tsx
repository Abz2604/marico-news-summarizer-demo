"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { Clock, X } from "lucide-react"

interface DeliveryTimeRowProps {
  value: string
  onChange: (time: string) => void
  onRemove: () => void
  disableRemove?: boolean
}

export function DeliveryTimeRow({ value, onChange, onRemove, disableRemove }: DeliveryTimeRowProps) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-4">
      <div className="flex items-center gap-2 rounded-md border border-input px-3 py-2 flex-1">
        <Clock className="w-4 h-4 text-muted-foreground" />
        <input
          type="time"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="bg-transparent text-sm outline-none w-full"
        />
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onRemove}
        disabled={disableRemove}
        className={cn("self-start md:self-auto", disableRemove && "opacity-60")}
      >
        <X className="w-4 h-4" />
      </Button>
    </div>
  )
}

