/**
 * Runtime configuration derived from Vite environment variables.
 *
 * Resolution rules:
 *  - `apiBaseUrl`   defaults to "/api" so the Vite dev proxy forwards to Django.
 *  - `useMocks`     is enabled when no explicit API URL is configured, unless
 *                   `VITE_USE_MOCKS` overrides it. This lets the UI run
 *                   standalone today and switch to Django by setting one var.
 */

function toBoolean(value: string | undefined): boolean | undefined {
  if (value === undefined) return undefined
  const normalised = value.trim().toLowerCase()
  if (!normalised) return undefined
  if (["1", "true", "yes", "on"].includes(normalised)) return true
  if (["0", "false", "no", "off"].includes(normalised)) return false
  return undefined
}

const rawApiUrl = (import.meta.env.VITE_API_URL ?? "").trim()
const explicitMocks = toBoolean(import.meta.env.VITE_USE_MOCKS)
const rawTimeout = Number(import.meta.env.VITE_API_TIMEOUT ?? "")

export const config = {
  /** API base URL without a trailing slash. */
  apiBaseUrl: (rawApiUrl || "/api").replace(/\/+$/, ""),
  /** True when the caller configured a concrete backend URL. */
  hasExplicitApiUrl: rawApiUrl.length > 0,
  /** Whether the in-browser mock transport should be used. */
  useMocks: explicitMocks ?? rawApiUrl.length === 0,
  /** Request timeout in milliseconds. */
  requestTimeout: Number.isFinite(rawTimeout) && rawTimeout > 0 ? rawTimeout : 20_000,
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
} as const

if (config.isDev) {
  // Helpful one-liner while wiring the Django backend.
  // eslint-disable-next-line no-console
  console.info(
    `[scla] API base: ${config.apiBaseUrl} · transport: ${config.useMocks ? "mock" : "http"}`,
  )
}
