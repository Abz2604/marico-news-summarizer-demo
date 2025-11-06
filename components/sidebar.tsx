"use client"

import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { FileText, Settings, LogOut, Plus, Layers } from "lucide-react"

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { logout, user } = useAuth()

  const isActive = (path: string) => pathname === path

  const handleLogout = () => {
    logout()
    router.push("/login")
  }

  return (
    <aside className="w-64 border-r border-border bg-sidebar flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-sidebar-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-sidebar-primary rounded-lg flex items-center justify-center">
            <span className="text-sidebar-primary-foreground font-bold">📰</span>
          </div>
          <div>
            <h1 className="font-semibold text-sidebar-foreground">Content Summarizer</h1>
            <p className="text-xs text-sidebar-accent-foreground">Daily Briefings</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2">
        <Button
          variant={isActive("/dashboard/create") ? "default" : "ghost"}
          className="w-full justify-start gap-3"
          onClick={() => router.push("/dashboard/create")}
        >
          <Plus className="w-4 h-4" />
          Create Briefing
        </Button>

        <Button
          variant={isActive("/dashboard/campaigns") ? "default" : "ghost"}
          className="w-full justify-start gap-3"
          onClick={() => router.push("/dashboard/campaigns")}
        >
          <Layers className="w-4 h-4" />
          Campaigns
        </Button>

        <Button
          variant={isActive("/dashboard/briefings") ? "default" : "ghost"}
          className="w-full justify-start gap-3"
          onClick={() => router.push("/dashboard/briefings")}
        >
          <FileText className="w-4 h-4" />
          My Briefings
        </Button>

        <Button
          variant={isActive("/dashboard/settings") ? "default" : "ghost"}
          className="w-full justify-start gap-3"
          onClick={() => router.push("/dashboard/settings")}
        >
          <Settings className="w-4 h-4" />
          Settings
        </Button>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-sidebar-border space-y-3">
        <div className="text-sm">
          <p className="text-sidebar-accent-foreground text-xs">Signed in as</p>
          <p className="font-medium text-sidebar-foreground truncate">{user?.email}</p>
        </div>
        <Button variant="outline" className="w-full justify-start gap-3 bg-transparent" onClick={handleLogout}>
          <LogOut className="w-4 h-4" />
          Sign Out
        </Button>
      </div>
    </aside>
  )
}
