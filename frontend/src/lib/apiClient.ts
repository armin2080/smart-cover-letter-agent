import { config } from "./config"
import { ApiError, type FieldErrors, normalizeError } from "./errors"
import { tokenStore } from "./storage"

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"

export type QueryValue = string | number | boolean | undefined | null

export interface RequestOptions {
  method?: HttpMethod
  /** JSON body. `FormData` is passed through untouched (file uploads). */
  body?: unknown
  query?: Record<string, QueryValue | QueryValue[]>
  signal?: AbortSignal
  headers?: Record<string, string>
  /** Omit the Authorization header and skip the refresh cycle. */
  anonymous?: boolean
}

const REFRESH_PATH = "/auth/refresh/"

/* -------------------------------------------------------------------------- */
/* URL + error helpers                                                        */
/* -------------------------------------------------------------------------- */

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const isAbsolute = /^https?:\/\//i.test(path)
  const url = isAbsolute
    ? path
    : `${config.apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`

  if (!query) return url

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item))
    } else {
      params.append(key, String(value))
    }
  }
  const qs = params.toString()
  if (!qs) return url
  return `${url}${url.includes("?") ? "&" : "?"}${qs}`
}

function defaultMessage(status: number): string {
  if (status === 400) return "The submitted data was not valid."
  if (status === 401) return "Authentication is required."
  if (status === 403) return "You do not have permission to do that."
  if (status === 404) return "Not found."
  if (status === 429) return "Too many requests. Please slow down."
  if (status >= 500) return "The server encountered an error."
  return `Request failed with status ${status}.`
}

const RESERVED_KEYS = new Set(["detail", "message", "error", "errors", "field_errors", "non_field_errors"])

/** Pull DRF-style field errors out of a response body. */
function collectFieldErrors(body: Record<string, unknown>): FieldErrors | undefined {
  const nested = (body.errors ?? body.field_errors) as unknown
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    return nested as FieldErrors
  }

  const collected: FieldErrors = {}
  for (const [key, value] of Object.entries(body)) {
    if (RESERVED_KEYS.has(key)) continue
    if (Array.isArray(value) && value.every((entry) => typeof entry === "string")) {
      collected[key] = value as string[]
    } else if (typeof value === "string") {
      collected[key] = [value]
    }
  }
  return Object.keys(collected).length ? collected : undefined
}

function firstMessage(errors: FieldErrors | undefined): string | undefined {
  if (!errors) return undefined
  for (const messages of Object.values(errors)) {
    if (messages?.length) return messages[0]
  }
  return undefined
}

function toApiError(status: number, body: unknown): ApiError {
  if (typeof body === "string" && body.trim()) {
    return new ApiError(body.trim(), { status, payload: body })
  }
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const record = body as Record<string, unknown>
    const nestedErrors =
      (record.errors && typeof record.errors === "object" ? (record.errors as FieldErrors) : undefined) ??
      (record.field_errors as FieldErrors | undefined)
    const fieldErrors = nestedErrors ?? collectFieldErrors(record)
    const nonField = Array.isArray(record.non_field_errors)
      ? (record.non_field_errors[0] as string)
      : undefined
    const explicit = [record.detail, record.message, record.error].find(
      (value): value is string => typeof value === "string" && value.length > 0,
    )
    const message = explicit ?? nonField ?? firstMessage(fieldErrors) ?? defaultMessage(status)
    return new ApiError(message, { status, payload: body, fieldErrors })
  }

  return new ApiError(defaultMessage(status), { status, payload: body })
}

/* -------------------------------------------------------------------------- */
/* Timeout handling                                                           */
/* -------------------------------------------------------------------------- */

interface TimeoutContext {
  signal: AbortSignal
  cleanup: () => void
  timedOut: () => boolean
}

function createTimeoutSignal(external: AbortSignal | undefined, ms: number): TimeoutContext {
  const controller = new AbortController()
  let timedOut = false

  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, ms)

  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener("abort", onExternalAbort, { once: true })
  }

  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    cleanup: () => {
      window.clearTimeout(timer)
      external?.removeEventListener("abort", onExternalAbort)
    },
  }
}

/* -------------------------------------------------------------------------- */
/* Token refresh (single-flight)                                              */
/* -------------------------------------------------------------------------- */

let refreshInFlight: Promise<string> | null = null

async function performRefresh(): Promise<string> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) throw new ApiError("No refresh token available.", { status: 401 })

  const timeout = createTimeoutSignal(undefined, config.requestTimeout)
  try {
    const response = await fetch(buildUrl(REFRESH_PATH), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh }),
      signal: timeout.signal,
    })

    const text = await response.text()
    const data = text ? (JSON.parse(text) as { access?: string; refresh?: string }) : {}

    if (!response.ok) {
      tokenStore.clear()
      throw toApiError(response.status, data)
    }
    if (!data.access) {
      tokenStore.clear()
      throw new ApiError("Refresh response did not include an access token.", { status: 401 })
    }

    tokenStore.set({ access: data.access, refresh: data.refresh ?? refresh })
    return data.access
  } finally {
    timeout.cleanup()
  }
}

/** Refresh the access token, coalescing concurrent callers into one request. */
export function refreshAccessToken(): Promise<string> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

/* -------------------------------------------------------------------------- */
/* Core request                                                               */
/* -------------------------------------------------------------------------- */

interface RawRequest extends RequestOptions {
  /** Internal: prevents an infinite refresh/retry loop. */
  retried?: boolean
}

async function requestRaw<T>(path: string, options: RawRequest = {}): Promise<T> {
  const { method = "GET", body, query, signal, headers = {}, anonymous = false } = options

  const finalHeaders: Record<string, string> = { Accept: "application/json", ...headers }
  let payload: BodyInit | undefined

  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    payload = JSON.stringify(body)
    finalHeaders["Content-Type"] = "application/json"
  }

  if (!anonymous) {
    const access = tokenStore.getAccess()
    if (access) finalHeaders.Authorization = `Bearer ${access}`
  }

  const timeout = createTimeoutSignal(signal, config.requestTimeout)

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: finalHeaders,
      body: payload,
      signal: timeout.signal,
    })
  } catch (error) {
    if (timeout.timedOut()) {
      throw new ApiError(`Request timed out after ${config.requestTimeout}ms.`, {
        status: 408,
        code: "timeout",
        cause: error,
      })
    }
    throw normalizeError(error)
  } finally {
    timeout.cleanup()
  }

  // Expired access token → refresh once, then replay the request.
  if (response.status === 401 && !anonymous && !options.retried && tokenStore.getRefresh()) {
    try {
      await refreshAccessToken()
    } catch {
      throw new ApiError("Your session has expired. Please sign in again.", { status: 401 })
    }
    return requestRaw<T>(path, { ...options, retried: true })
  }

  const text = await response.text()
  let data: unknown = undefined
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!response.ok) throw toApiError(response.status, data)
  return data as T
}

/* -------------------------------------------------------------------------- */
/* Public client                                                              */
/* -------------------------------------------------------------------------- */

export const apiClient = {
  request: requestRaw,

  get<T>(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return requestRaw<T>(path, { ...options, method: "GET" })
  },

  post<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return requestRaw<T>(path, { ...options, method: "POST", body })
  },

  put<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return requestRaw<T>(path, { ...options, method: "PUT", body })
  },

  patch<T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return requestRaw<T>(path, { ...options, method: "PATCH", body })
  },

  delete<T = void>(path: string, options?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return requestRaw<T>(path, { ...options, method: "DELETE" })
  },

  /** Download a binary response (cover letter PDFs). */
  async getBlob(path: string, options?: RequestOptions): Promise<Blob> {
    const { method = "GET", query, signal, headers = {}, anonymous = false } = options ?? {}
    const finalHeaders: Record<string, string> = { ...headers }
    if (!anonymous) {
      const access = tokenStore.getAccess()
      if (access) finalHeaders.Authorization = `Bearer ${access}`
    }

    const timeout = createTimeoutSignal(signal, config.requestTimeout)
    let response: Response
    try {
      response = await fetch(buildUrl(path, query), { method, headers: finalHeaders, signal: timeout.signal })
    } catch (error) {
      if (timeout.timedOut()) {
        throw new ApiError("The download timed out.", { status: 408, code: "timeout", cause: error })
      }
      throw normalizeError(error)
    } finally {
      timeout.cleanup()
    }

    if (!response.ok) {
      const text = await response.text()
      let data: unknown = text
      try {
        data = text ? JSON.parse(text) : undefined
      } catch {
        /* keep raw text */
      }
      throw toApiError(response.status, data)
    }
    return response.blob()
  },

  /** Absolute URL for a media/API path, e.g. an uploaded CV preview. */
  url(path: string): string {
    return buildUrl(path)
  },
}

/** True when the app is pointed at the in-browser mock transport. */
export const usingMocks = config.useMocks
