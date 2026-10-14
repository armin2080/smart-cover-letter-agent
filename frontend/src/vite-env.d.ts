/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Django REST API. Empty = use the dev proxy. */
  readonly VITE_API_URL?: string
  /** "true" | "false" — force the mock transport on or off. */
  readonly VITE_USE_MOCKS?: string
  /** Request timeout in milliseconds. */
  readonly VITE_API_TIMEOUT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
