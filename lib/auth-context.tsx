"use client"

import type React from "react"
import { createContext, useContext, useState, useEffect } from "react"
import { apiClient } from "@/lib/api-client"

interface User {
  id: string
  email: string
  name: string
  role: string
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  signup: (email: string, password: string, name: string) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Check if we have a token and try to fetch user info
    const token = localStorage.getItem("auth_token")
    if (token) {
      // Try to fetch current user info
      apiClient.auth
        .me()
        .then((userData) => {
          setUser({
            id: userData.id,
            email: userData.email,
            name: userData.display_name || userData.email.split("@")[0],
            role: userData.role,
          })
        })
        .catch((error) => {
          // Token is invalid, clear it
          console.error("Failed to fetch user info:", error)
          localStorage.removeItem("auth_token")
          localStorage.removeItem("user")
        })
        .finally(() => {
          setIsLoading(false)
        })
    } else {
      setIsLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    try {
      const response = await apiClient.auth.login(email, password)
      
      // Store token
      localStorage.setItem("auth_token", response.access_token)
      
      // Store user info
      const userData: User = {
        id: response.user.id,
        email: response.user.email,
        name: response.user.display_name || response.user.email.split("@")[0],
        role: response.user.role,
      }
      setUser(userData)
      localStorage.setItem("user", JSON.stringify(userData))
    } catch (error) {
      console.error("Login failed:", error)
      throw error
    }
  }

  const logout = () => {
    setUser(null)
    localStorage.removeItem("auth_token")
    localStorage.removeItem("user")
  }

  const signup = async (email: string, password: string, name: string) => {
    try {
      const response = await apiClient.auth.signup({
        email,
        password,
        display_name: name,
      })
      
      // Store token
      localStorage.setItem("auth_token", response.access_token)
      
      // Store user info
      const userData: User = {
        id: response.user.id,
        email: response.user.email,
        name: response.user.display_name || response.user.email.split("@")[0],
        role: response.user.role,
      }
      setUser(userData)
      localStorage.setItem("user", JSON.stringify(userData))
    } catch (error) {
      console.error("Signup failed:", error)
      throw error
    }
  }

  return <AuthContext.Provider value={{ user, isLoading, login, logout, signup }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return context
}
