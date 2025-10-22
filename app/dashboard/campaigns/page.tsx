"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { DEMO_CAMPAIGNS } from "@/lib/demo-data"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Layers, Mail, Users2, Clock, Filter } from "lucide-react"

const STATUS_COLOR: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  draft: "bg-blue-100 text-blue-800",
  paused: "bg-yellow-100 text-yellow-800",
}

const CAMPAIGN_FILTERS = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Draft", value: "draft" },
  { label: "Paused", value: "paused" },
]

export default function CampaignsPage() {
  const [filter, setFilter] = useState("all")
  const router = useRouter()

  const campaigns = useMemo(() => {
    if (filter === "all") return DEMO_CAMPAIGNS
    return DEMO_CAMPAIGNS.filter((campaign) => campaign.status === filter)
  }, [filter])

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-border p-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold">Campaigns</h1>
          <p className="text-muted-foreground mt-1">Bundle briefings into scheduled email sends</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground border border-border rounded-md px-4 py-2">
            <Filter className="w-4 h-4" />
            <div className="flex gap-2">
              {CAMPAIGN_FILTERS.map((item) => (
                <button
                  key={item.value}
                  onClick={() => setFilter(item.value)}
                  className={`transition-colors ${filter === item.value ? "text-foreground font-medium" : "hover:text-foreground"}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <Button className="gap-2" onClick={() => router.push("/dashboard/campaigns/new")}>New Campaign</Button>
        </div>
      </div>

      <div className="flex-1 p-6">
        {campaigns.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center gap-3">
              <Layers className="w-12 h-12 text-muted-foreground" />
              <h3 className="text-lg font-semibold">No campaigns yet</h3>
              <p className="text-muted-foreground max-w-sm">
                Combine briefings and schedule delivery times to keep your stakeholders informed on a single stream.
              </p>
              <Button onClick={() => router.push("/dashboard/campaigns/new")}>Create your first campaign</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {campaigns.map((campaign, index) => (
              <Card
                key={campaign.id}
                className="hover:shadow-md transition-all duration-300 animate-in fade-in slide-in-from-top"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="p-6 flex flex-col h-full gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold">{campaign.name}</h3>
                      <p className="text-xs text-muted-foreground mt-1">Last sent {campaign.lastSent}</p>
                    </div>
                    <Badge className={`${STATUS_COLOR[campaign.status]} capitalize`}>{campaign.status}</Badge>
                  </div>

                  <div className="space-y-3 text-sm">
                    <div className="flex items-start gap-3">
                      <Layers className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Briefings</p>
                        <p className="text-muted-foreground leading-relaxed">
                          {campaign.briefings.length > 0 ? campaign.briefings.join(", ") : "No briefings selected"}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <Users2 className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Recipients</p>
                        <p className="text-muted-foreground leading-relaxed">
                          {campaign.recipients.length > 0 ? campaign.recipients.join(", ") : "Add recipients to start sending"}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <Clock className="w-4 h-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium">Delivery times</p>
                        <p className="text-muted-foreground leading-relaxed">
                          {campaign.deliveryTimes.length > 0 ? campaign.deliveryTimes.join(", ") : "No delivery times configured"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-auto flex items-center justify-between pt-4 border-t border-border">
                    <Button variant="outline" className="bg-transparent gap-2" size="sm">
                      <Mail className="w-4 h-4" />
                      Preview Email
                    </Button>
                    <Button variant="ghost" size="sm" className="hover:bg-muted">Manage</Button>
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

