"use client"

import { useMemo } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { ChevronsUpDown, Search, X } from "lucide-react"
import type { Briefing } from "@/lib/api-client"

interface SelectBriefingRowProps {
  value: string
  onChange: (id: string) => void
  onRemove: () => void
  disableRemove?: boolean
  briefs: Briefing[]
}

export function SelectBriefingRow({ value, onChange, onRemove, disableRemove, briefs }: SelectBriefingRowProps) {
  const selected = useMemo(() => briefs.find((brief) => brief.id === value), [briefs, value])

  return (
    <Card className="p-4 flex flex-col gap-3 border-dashed">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3 flex-1">
          <Badge variant="outline" className="gap-1">
            {selected ? (selected.seed_links.length > 0 ? new URL(selected.seed_links[0]).hostname : "Web") : "Select"}
          </Badge>
          <div className="space-y-1 flex-1">
            <p className="text-sm font-medium">
              {selected ? selected.name : "Choose briefing"}
            </p>
            <p className="text-xs text-muted-foreground truncate">
              {selected ? (selected.description || selected.prompt.slice(0, 60) + "...") : "Pick from your saved briefings"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="bg-transparent gap-2"
            onClick={() => {
              const next = briefs.find((brief) => brief.id !== value)
              if (next) onChange(next.id)
            }}
          >
            <ChevronsUpDown className="w-4 h-4" /> Switch
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onRemove} disabled={disableRemove}>
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
        <div className="flex items-center gap-2 rounded-md border border-input px-3 py-2">
          <Search className="w-4 h-4 text-muted-foreground" />
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="w-full bg-transparent text-sm outline-none"
          >
            <option value="">Select briefing</option>
            {briefs.map((briefing) => (
              <option key={briefing.id} value={briefing.id}>
                {briefing.name}
              </option>
            ))}
          </select>
        </div>
        <Input
          readOnly
          value={selected?.status === "active" ? "Active" : selected?.status === "draft" ? "Draft" : "Not in campaigns"}
          className="text-sm capitalize"
        />
      </div>
    </Card>
  )
}

