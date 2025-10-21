"use client"

import { useEffect, useState } from "react"
import { Check } from "lucide-react"

interface SuccessBannerProps {
  message: string
}

export function SuccessBanner({ message }: SuccessBannerProps) {
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false)
    }, 5000)

    return () => clearTimeout(timer)
  }, [])

  if (!isVisible) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-50 animate-in slide-in-from-top duration-300">
      <div className="bg-green-50 border-b border-green-200 px-6 py-4 flex items-center gap-3 mx-auto max-w-2xl">
        <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 animate-in scale-in duration-300">
          <Check className="w-5 h-5 text-green-600" />
        </div>
        <p className="text-sm text-green-800">{message}</p>
      </div>
    </div>
  )
}
