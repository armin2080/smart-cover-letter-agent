import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"
import { Icon } from "../components/ui/Icon"
import type { IconName } from "../types"

export type ToastTone = "success" | "error" | "info"

interface ToastItem {
  id: number
  message: string
  tone: ToastTone
}

interface ToastContextValue {
  push(message: string, tone?: ToastTone): void
  success(message: string): void
  error(message: string): void
  info(message: string): void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const TONE_ICON: Record<ToastTone, IconName> = {
  success: "check",
  error: "close",
  info: "bell",
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const push = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now() + Math.random()
    setItems((previous) => [...previous.slice(-2), { id, message, tone }])
    window.setTimeout(() => {
      setItems((previous) => previous.filter((item) => item.id !== id))
    }, 3400)
  }, [])

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (message) => push(message, "success"),
      error: (message) => push(message, "error"),
      info: (message) => push(message, "info"),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
        {items.map((item) => (
          <div className={`toast toast-${item.tone}`} key={item.id}>
            <Icon name={TONE_ICON[item.tone]} size={15} />
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) throw new Error("useToast must be used inside a <ToastProvider>.")
  return context
}
