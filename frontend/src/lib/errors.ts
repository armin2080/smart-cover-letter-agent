/** Field-level validation errors keyed by field name. */
export interface FieldErrors {
  [field: string]: string[]
}

interface ApiErrorOptions {
  status?: number
  code?: string
  fieldErrors?: FieldErrors
  payload?: unknown
  cause?: unknown
}

/**
 * Normalised error shape for every failed request, regardless of whether the
 * failure came from the network, the transport, or Django REST Framework.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | undefined
  readonly fieldErrors: FieldErrors | undefined
  readonly payload: unknown

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message)
    this.name = "ApiError"
    this.status = options.status ?? 0
    this.code = options.code
    this.fieldErrors = options.fieldErrors
    this.payload = options.payload
    if (options.cause !== undefined) {
      ;(this as { cause?: unknown }).cause = options.cause
    }
  }

  /** No HTTP response was received (offline, DNS, timeout, CORS). */
  get isNetworkError(): boolean {
    return this.status === 0
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }

  get isForbidden(): boolean {
    return this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }

  get isConflict(): boolean {
    return this.status === 409
  }

  get isValidation(): boolean {
    return this.status === 400 || this.status === 422
  }

  /**
   * True when the server refused the request for hitting a rate limit.
   *
   * Worth its own branch: the credential endpoints are limited deliberately,
   * so a user who mistypes their password a few times will meet this, and the
   * raw backend detail ("Expected available in 60 seconds") is not something to
   * put in front of them.
   */
  get isRateLimited(): boolean {
    return this.status === 429
  }

  get isServerError(): boolean {
    return this.status >= 500
  }

  /** True when retrying the request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.isNetworkError || this.status === 408 || this.status === 429 || this.isServerError
  }

  /** Human-readable message safe to render in the UI. */
  get displayMessage(): string {
    if (this.isNetworkError) {
      return "We could not reach the server. Check your connection and try again."
    }
    if (this.isUnauthorized) return "Your session has expired. Please sign in again."
    if (this.isForbidden) return "You do not have permission to perform this action."
    if (this.isNotFound) return "We could not find what you were looking for."
    if (this.isRateLimited) {
      return "Too many attempts just now. Please wait a minute and try again."
    }
    if (this.isValidation) {
      const first = this.firstFieldMessage
      if (first) return first
      return "Please check the highlighted fields and try again."
    }
    if (this.isServerError) return "Something went wrong on our side. Please try again shortly."
    return this.message || "Something went wrong."
  }

  /** First message from `fieldErrors`, if any. */
  get firstFieldMessage(): string | undefined {
    if (!this.fieldErrors) return undefined
    for (const messages of Object.values(this.fieldErrors)) {
      if (messages?.length) return messages[0]
    }
    return undefined
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

export function isAbortError(value: unknown): boolean {
  return value instanceof DOMException && value.name === "AbortError"
}

/** Convert any thrown value into an `ApiError`. */
export function normalizeError(error: unknown): ApiError {
  if (isApiError(error)) return error
  if (isAbortError(error)) {
    return new ApiError("The request was cancelled.", { code: "aborted", cause: error })
  }
  if (error instanceof TypeError) {
    // fetch() rejects with TypeError for network-level failures.
    return new ApiError("Network request failed.", { status: 0, cause: error })
  }
  if (error instanceof Error) {
    return new ApiError(error.message, { code: error.name, cause: error })
  }
  return new ApiError(String(error))
}
