import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { tokenStore } from "../lib/storage"
import { api, isMockMode } from "../services/api"
import type { AccountUpdate, LoginPayload, RegisterPayload, User } from "../types/api"

export type AuthStatus = "loading" | "authenticated" | "anonymous"

interface AuthContextValue {
  user: User | null
  status: AuthStatus
  /** True when the app runs against the mock transport. */
  isMock: boolean
  login(payload: LoginPayload): Promise<void>
  register(payload: RegisterPayload): Promise<void>
  logout(): Promise<void>
  updateAccount(payload: AccountUpdate): Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>(() =>
    tokenStore.get() ? "loading" : "anonymous",
  )

  // Restore an existing session on first paint.
  useEffect(() => {
    if (!tokenStore.get()) {
      setStatus("anonymous")
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const current = await api.auth.me()
        if (cancelled) return
        setUser(current)
        setStatus("authenticated")
      } catch {
        if (cancelled) return
        tokenStore.clear()
        setUser(null)
        setStatus("anonymous")
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  // A cleared token store (for example after a failed refresh) ends the session.
  useEffect(
    () =>
      tokenStore.subscribe((tokens) => {
        if (!tokens) {
          setUser(null)
          setStatus("anonymous")
        }
      }),
    [],
  )

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await api.auth.login(payload)
    tokenStore.set(response.tokens)
    setUser(response.user)
    setStatus("authenticated")
  }, [])

  const register = useCallback(async (payload: RegisterPayload) => {
    const response = await api.auth.register(payload)
    tokenStore.set(response.tokens)
    setUser(response.user)
    setStatus("authenticated")
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } finally {
      tokenStore.clear()
      setUser(null)
      setStatus("anonymous")
    }
  }, [])

  const updateAccount = useCallback(async (payload: AccountUpdate) => {
    const updated = await api.auth.updateAccount(payload)
    setUser(updated)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, isMock: isMockMode, login, register, logout, updateAccount }),
    [user, status, login, register, logout, updateAccount],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used inside an <AuthProvider>.")
  return context
}
