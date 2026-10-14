import type { ReactNode } from "react"
import { Button } from "../ui/Button"
import { Icon } from "../ui/Icon"
import { normalizeError } from "../../lib/errors"
import type { IconName } from "../../types"

/* -------------------------------------------------------------------------- */
/* Loading                                                                    */
/* -------------------------------------------------------------------------- */

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden="true" />
      {label && <span className="spinner-label">{label}</span>}
    </span>
  )
}

/** Full-block loading placeholder. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-block state-loading" role="status" aria-live="polite">
      <Spinner />
      <p>{label}</p>
    </div>
  )
}

/** Shimmer placeholder for lists and cards. */
export function Skeleton({ rows = 3, height = 64 }: { rows?: number; height?: number }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div className="skeleton" key={index} style={{ height }} />
      ))}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Errors                                                                     */
/* -------------------------------------------------------------------------- */

interface ErrorStateProps {
  error: unknown
  title?: string
  onRetry?: () => void
  /** Render as a compact inline banner instead of a centred block. */
  inline?: boolean
}

export function ErrorState({ error, title = "Something went wrong", onRetry, inline = false }: ErrorStateProps) {
  const apiError = normalizeError(error)
  const message = apiError.displayMessage

  if (inline) {
    return (
      <div className="error-banner" role="alert">
        <Icon name="close" size={15} />
        <span>{message}</span>
        {onRetry && (
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="state-block state-error" role="alert">
      <span className="state-icon state-icon-error">
        <Icon name="close" size={22} />
      </span>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry && (
        <div className="state-actions">
          <Button kind="secondary" onClick={onRetry} icon="play">
            Try again
          </Button>
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Empty                                                                      */
/* -------------------------------------------------------------------------- */

interface EmptyStateProps {
  icon?: IconName
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ icon = "search", title, description, action }: EmptyStateProps) {
  return (
    <div className="state-block state-empty">
      <span className="state-icon">
        <Icon name={icon} size={22} />
      </span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="state-actions">{action}</div>}
    </div>
  )
}
