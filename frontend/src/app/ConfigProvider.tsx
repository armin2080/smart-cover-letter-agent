import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { api } from "../services/api"
import type { PublicConfig } from "../types/api"

interface ConfigContextValue {
  /** Feature flags from the backend, or the safe default while loading. */
  config: PublicConfig
  loading: boolean
}

/**
 * Safe fallback used before the flags arrive, and if fetching them fails.
 *
 * Registration is **closed** here on purpose. Every other failure mode in this
 * app degrades toward doing less; a network hiccup must not turn an
 * invitation-only pilot into an open signup.
 */
const SAFE_DEFAULT: PublicConfig = { registrationEnabled: false }

const ConfigContext = createContext<ConfigContextValue>({
  config: SAFE_DEFAULT,
  loading: true,
})

/**
 * Fetches the public feature flags once and shares them with the tree.
 *
 * A provider rather than a hook per component, because both the landing page
 * and the auth pages need the same value and duplicate requests would be
 * wasteful. The request is unauthenticated — the login screen needs the flags
 * before any session exists.
 */
export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<PublicConfig>(SAFE_DEFAULT)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const fetched = await api.config.get()
        if (cancelled) return
        setConfig({ registrationEnabled: Boolean(fetched?.registrationEnabled) })
      } catch {
        // Keep the safe default. A failed config fetch is not worth an error
        // screen: the app is still usable, just without self-service signup.
        if (!cancelled) setConfig(SAFE_DEFAULT)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  return <ConfigContext.Provider value={{ config, loading }}>{children}</ConfigContext.Provider>
}

export function useConfig(): ConfigContextValue {
  return useContext(ConfigContext)
}
