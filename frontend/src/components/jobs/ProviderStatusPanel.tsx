import { useAsync } from "../../hooks/useAsync"
import { api } from "../../services/api"
import { Icon } from "../ui/Icon"
import type { ProviderStatus } from "../../types"

/**
 * Per-source availability panel.
 *
 * The interface must never imply a source is connected when it is not. A
 * provider without written platform authorization is shown as disabled, with the
 * reason, rather than as "no results".
 */
export function ProviderStatusPanel({ compact = false }: { compact?: boolean }) {
  const providers = useAsync((signal) => api.jobs.providers({ signal }), [])

  if (providers.loading) {
    return (
      <div className="provider-panel">
        <div className="provider-head">
          <h3>Job sources</h3>
        </div>
        <div className="skeleton" style={{ height: 44 }} />
      </div>
    )
  }

  const entries = providers.data ?? []
  const operational = entries.filter((entry) => entry.operational)

  return (
    <div className="provider-panel">
      <div className="provider-head">
        <div>
          <h3>Job sources</h3>
          <p>
            {operational.length === 0
              ? "No live source is authorized yet. Add jobs manually, or see the authorization matrix."
              : `${operational.length} source${operational.length === 1 ? "" : "s"} available.`}
          </p>
        </div>
      </div>

      <ul className="provider-list">
        {entries.map((entry) => (
          <ProviderRow key={entry.source} entry={entry} compact={compact} />
        ))}
      </ul>
    </div>
  )
}

function ProviderRow({ entry, compact }: { entry: ProviderStatus; compact: boolean }) {
  // A test-mode source is usable but not authorized, so it gets its own state
  // rather than the green "ready" treatment. Showing it as fully ready would
  // imply a permission that does not exist.
  const testMode = entry.status === "enabled-for-testing"
  const state = testMode ? "test" : entry.operational ? "ready" : "disabled"

  // The test-mode warning matters even in the compact layout, so it is never
  // hidden behind the `compact` flag.
  const showDetail = !compact || testMode

  return (
    <li className={`provider-row provider-${state}`}>
      <span className="provider-dot" aria-hidden="true" />
      <div className="provider-body">
        <b>{entry.displayName}</b>
        <small>{entry.statusLabel}</small>
        {showDetail && <p>{entry.operational ? entry.detail : entry.termsNote}</p>}
      </div>
      {testMode ? (
        <Icon name="sparkle" size={14} />
      ) : entry.operational ? (
        <Icon name="check" size={14} />
      ) : (
        <Icon name="shield" size={14} />
      )}
    </li>
  )
}
