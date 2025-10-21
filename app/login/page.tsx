"use client"

import type React from "react"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCircle, Loader2 } from "lucide-react"

export default function LoginPage() {
  const router = useRouter()
  const { login, signup } = useAuth()
  const [isSignup, setIsSignup] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsLoading(true)

    try {
      if (isSignup) {
        if (!name.trim()) {
          setError("Name is required")
          setIsLoading(false)
          return
        }
        await signup(email, password, name)
      } else {
        await login(email, password)
      }
      router.push("/dashboard/create")
    } catch (err) {
      setError("Authentication failed. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted flex items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-lg hover:shadow-xl transition-shadow duration-300 animate-in fade-in scale-in duration-300">
        <CardHeader className="space-y-2 text-center">
          <div className="flex justify-center mb-4 animate-in scale-in duration-300">
            <div className="w-12 h-12 bg-primary rounded-lg flex items-center justify-center hover:scale-110 transition-transform duration-300">
              <span className="text-primary-foreground font-bold text-xl">📰</span>
            </div>
          </div>
          <CardTitle className="text-2xl">Daily News Summarizer</CardTitle>
          <CardDescription>{isSignup ? "Create your account" : "Sign in to your account"}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex gap-2 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive animate-in fade-in slide-in-from-top duration-200">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {isSignup && (
              <div className="space-y-2 animate-in fade-in slide-in-from-top duration-300">
                <label className="text-sm font-medium">Full Name</label>
                <Input
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isLoading}
                  className="transition-all duration-200"
                />
              </div>
            )}

            <div
              className="space-y-2 animate-in fade-in slide-in-from-top duration-300"
              style={{ animationDelay: isSignup ? "50ms" : "0ms" }}
            >
              <label className="text-sm font-medium">Email</label>
              <Input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                required
                className="transition-all duration-200"
              />
            </div>

            <div
              className="space-y-2 animate-in fade-in slide-in-from-top duration-300"
              style={{ animationDelay: isSignup ? "100ms" : "50ms" }}
            >
              <label className="text-sm font-medium">Password</label>
              <Input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                required
                className="transition-all duration-200"
              />
            </div>

            <Button type="submit" className="w-full transition-all duration-200 hover:shadow-md" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Loading...
                </>
              ) : isSignup ? (
                "Create Account"
              ) : (
                "Sign In"
              )}
            </Button>
          </form>

          <div className="mt-6 space-y-3 text-center text-sm">
            <button
              onClick={() => {
                setIsSignup(!isSignup)
                setError("")
              }}
              className="text-primary hover:underline transition-all duration-200"
            >
              {isSignup ? "Already have an account? Sign in" : "Don't have an account? Sign up"}
            </button>
            <div className="text-muted-foreground">
              <button className="text-primary hover:underline transition-all duration-200">Forgot password?</button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
