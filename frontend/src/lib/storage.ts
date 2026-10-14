/**
 * Token + session persistence.
 *
 * Tokens are stored in `localStorage` so a page reload keeps the session.
 * Swap this module for an httpOnly-cookie strategy without touching callers:
 * the rest of the app only reads/writes through `tokenStore`.
 */

const ACCESS_KEY = "scla.access"
const REFRESH_KEY = "scla.refresh"

export interface AuthTokens {
  access: string
  refresh: string
}

type Listener = (tokens: AuthTokens | null) => void

const listeners = new Set<Listener>()

function notify(): void {
  const current = tokenStore.get()
  for (const listener of listeners) listener(current)
}

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable (private mode) — session stays in memory only */
  }
}

function safeRemove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export const tokenStore = {
  get(): AuthTokens | null {
    const access = safeGet(ACCESS_KEY)
    const refresh = safeGet(REFRESH_KEY)
    if (!access && !refresh) return null
    return { access: access ?? "", refresh: refresh ?? "" }
  },

  getAccess(): string | null {
    return safeGet(ACCESS_KEY)
  },

  getRefresh(): string | null {
    return safeGet(REFRESH_KEY)
  },

  set(tokens: Partial<AuthTokens>): void {
    if (tokens.access !== undefined) safeSet(ACCESS_KEY, tokens.access)
    if (tokens.refresh !== undefined) safeSet(REFRESH_KEY, tokens.refresh)
    notify()
  },

  clear(): void {
    safeRemove(ACCESS_KEY)
    safeRemove(REFRESH_KEY)
    notify()
  },

  /** Subscribe to token changes (used to force logout on refresh failure). */
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}
