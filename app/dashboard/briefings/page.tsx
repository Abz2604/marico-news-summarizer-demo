"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Pause, Play, Trash2, Eye, Edit2 } from "lucide-react"

interface Briefing {
  id: string
  name: string
  recipients: string[]
  schedule: string
  lastSent: string
  status: "active" | "paused" | "error"
}

const DEMO_BRIEFINGS: Briefing[] = [
  {
    id: "1",
    name: "TechCrunch Daily",
    recipients: ["john@example.com"],
    schedule: "09:00 IST",
    lastSent: "2025-10-22 09:15",
    status: "active",
  },
  {
    id: "2",
    name: "The Verge News",
    recipients: ["john@example.com", "jane@example.com"],
    schedule: "14:00 IST",
    lastSent: "2025-10-21 14:05",
    status: "active",
  },
  {
    id: "3",
    name: "Hacker News Digest",
    recipients: ["john@example.com"],
    schedule: "18:00 IST",
    lastSent: "2025-10-20 18:30",
    status: "paused",
  },
]

export default function MyBriefingsPage() {
  const [briefings, setBriefings] = useState<Briefing[]>(DEMO_BRIEFINGS)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const toggleStatus = (id: string) => {
    setBriefings(
      briefings.map((b) => (b.id === id ? { ...b, status: b.status === "active" ? "paused" : "active" } : b)),
    )
  }

  const deleteBriefing = (id: string) => {
    setDeletingId(id)
    setTimeout(() => {
      setBriefings(briefings.filter((b) => b.id !== id))
      setDeletingId(null)
    }, 300)
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "bg-green-100 text-green-800"
      case "paused":
        return "bg-yellow-100 text-yellow-800"
      case "error":
        return "bg-red-100 text-red-800"
      default:
        return "bg-gray-100 text-gray-800"
    }
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-border p-6 flex items-center justify-between animate-in fade-in slide-in-from-top duration-300">
        <div>
          <h1 className="text-3xl font-bold">My Briefings</h1>
          <p className="text-muted-foreground mt-1">Manage your automated daily summaries</p>
        </div>
        <Button
          onClick={() => (window.location.href = "/dashboard/create")}
          className="transition-all duration-200 hover:shadow-md"
        >
          + Create New Briefing
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 p-6">
        {briefings.length === 0 ? (
          <Card className="border-dashed animate-in fade-in duration-300">
            <CardContent className="flex flex-col items-center justify-center py-12">
              <div className="text-6xl mb-4 animate-in scale-in duration-300">📋</div>
              <h3 className="text-lg font-semibold mb-2">No briefings yet</h3>
              <p className="text-muted-foreground mb-6">Create your first daily summary to get started</p>
              <Button onClick={() => (window.location.href = "/dashboard/create")}>Create Your First Briefing</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {briefings.map((briefing, index) => (
              <Card
                key={briefing.id}
                className={`hover:shadow-md transition-all duration-300 animate-in fade-in slide-in-from-top ${
                  deletingId === briefing.id ? "opacity-0 scale-95" : ""
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold text-lg">{briefing.name}</h3>
                        <Badge className={`${getStatusColor(briefing.status)} transition-all duration-200`}>
                          {briefing.status.charAt(0).toUpperCase() + briefing.status.slice(1)}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Recipients</p>
                          <p className="font-medium">{briefing.recipients.length}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Schedule</p>
                          <p className="font-medium">{briefing.schedule}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Last Sent</p>
                          <p className="font-medium">{briefing.lastSent}</p>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        title="View"
                        className="transition-all duration-200 hover:bg-muted bg-transparent"
                      >
                        <Eye className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        title="Edit"
                        className="transition-all duration-200 hover:bg-muted bg-transparent"
                      >
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleStatus(briefing.id)}
                        title={briefing.status === "active" ? "Pause" : "Resume"}
                        className="transition-all duration-200 hover:bg-muted"
                      >
                        {briefing.status === "active" ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => deleteBriefing(briefing.id)}
                        title="Delete"
                        className="text-destructive hover:text-destructive transition-all duration-200 hover:bg-destructive/10"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
