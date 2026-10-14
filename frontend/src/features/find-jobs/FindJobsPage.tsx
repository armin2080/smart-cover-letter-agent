import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useToast } from "../../app/ToastProvider"
import { EmptyState, ErrorState, Skeleton, Spinner } from "../../components/feedback/States"
import { ProviderStatusPanel } from "../../components/jobs/ProviderStatusPanel"
import { PreferencesForm } from "../../components/profile/PreferencesForm"
import { Button } from "../../components/ui/Button"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { normalizeError } from "../../lib/errors"
import { formatDateTime, relativeTime } from "../../lib/format"
import { SOURCE_OPTIONS } from "../../lib/labels"
import { api } from "../../services/api"
import type { Preferences, SearchCriteria, SearchRun } from "../../types"

/** Preferences and search criteria share the same shape; convert between them. */
function toPreferences(criteria: SearchCriteria): Preferences {
  return {
    desiredRoles: criteria.roles,
    locations: criteria.locations,
    radiusKm: criteria.radiusKm,
    employmentTypes: criteria.employmentTypes,
    sources: criteria.sources,
    keywords: criteria.keywords,
  }
}

function fromPreferences(preferences: Preferences, useSavedPreferences: boolean): SearchCriteria {
  return {
    roles: preferences.desiredRoles,
    locations: preferences.locations,
    radiusKm: preferences.radiusKm,
    employmentTypes: preferences.employmentTypes,
    sources: preferences.sources,
    keywords: preferences.keywords,
    useSavedPreferences,
  }
}

const EMPTY_CRITERIA: SearchCriteria = {
  roles: [],
  locations: [],
  radiusKm: 50,
  employmentTypes: [],
  sources: [],
  keywords: [],
  useSavedPreferences: true,
}

/* -------------------------------------------------------------------------- */
/* Progress screen                                                            */
/* -------------------------------------------------------------------------- */

function SearchProgress({ run, onCancel, onDone }: { run: SearchRun; onCancel: () => void; onDone: () => void }) {
  const complete = run.status === "completed"
  const failed = run.status === "failed"
  const doneCount = run.stages.filter((stage) => stage.state === "done").length
  const percent = Math.round((doneCount / Math.max(run.stages.length, 1)) * 100)
  const current = run.stages.find((stage) => stage.state === "active")

  return (
    <div className="search-progress">
      <div className="progress-orbit">
        <Icon name={complete ? "check" : failed ? "close" : "search"} size={26} />
      </div>

      <span className="overline">
        {complete ? "SEARCH COMPLETE" : failed ? "SEARCH FAILED" : "SEARCHING YOUR SOURCES"}
      </span>

      <h2>
        {complete
          ? run.matched > 0
            ? `${run.matched} matching jobs are ready.`
            : "Your search finished."
          : failed
            ? "We could not finish this search."
            : `${current?.label ?? "Working"}…`}
      </h2>

      <p>
        {complete
          ? run.matched > 0
            ? `Analysed ${run.discovered} listings and kept the ones that fit your profile.`
            : `Analysed ${run.discovered} listings. Nothing scored as a strong or good match this time — ` +
              "new roles may still be worth a look, or try widening your criteria."
          : failed
            ? run.error ?? "Please try again in a moment."
            : "This usually takes a moment. You can safely leave this page."}
      </p>

      <div className="progress-bar" style={{ maxWidth: 420, margin: "4px auto 18px" }}>
        <i style={{ width: `${complete ? 100 : Math.max(percent, 6)}%` }} />
      </div>

      <div className="stage-list">
        {run.stages.map((stage) => (
          <div
            className={
              stage.state === "done" ? "complete" : stage.state === "active" ? "current" : ""
            }
            key={stage.key}
          >
            <span>{stage.state === "done" ? <Icon name="check" size={14} /> : null}</span>
            <b>{stage.label}</b>
            {stage.detail && <small>{stage.detail}</small>}
          </div>
        ))}
      </div>

      <div className="state-actions">
        {complete ? (
          <Button onClick={onDone}>
            {run.matched > 0 ? `Review ${run.matched} matches` : "View new jobs"} <Icon name="arrow" size={16} />
          </Button>
        ) : failed ? (
          <Button kind="secondary" onClick={onDone}>
            Back to search
          </Button>
        ) : (
          <Button kind="secondary" onClick={onCancel}>
            Cancel search
          </Button>
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Page                                                                       */
/* -------------------------------------------------------------------------- */

export function FindJobsPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [mode, setMode] = useState<"manual" | "automatic">("manual")
  const [criteria, setCriteria] = useState<SearchCriteria>(EMPTY_CRITERIA)
  const [prefilled, setPrefilled] = useState(false)
  const [starting, setStarting] = useState(false)
  const [run, setRun] = useState<SearchRun | null>(null)

  const savedPreferences = useAsync((signal) => api.preferences.get({ signal }), [])
  const autoSettings = useAsync((signal) => api.searches.autoSettings({ signal }), [])
  const history = useAsync((signal) => api.searches.list({ signal }), [])

  // Pre-fill the manual form once the saved preferences arrive.
  useEffect(() => {
    if (prefilled || !savedPreferences.data) return
    setCriteria(fromPreferences(savedPreferences.data, true))
    setPrefilled(true)
  }, [savedPreferences.data, prefilled])

  // Poll the running search until it reaches a terminal state.
  useEffect(() => {
    if (!run || run.status === "completed" || run.status === "failed") return
    const timer = window.setInterval(async () => {
      try {
        const next = await api.searches.get(run.id)
        setRun(next)
        if (next.status === "completed" || next.status === "failed") {
          window.clearInterval(timer)
          void history.run()
        }
      } catch {
        window.clearInterval(timer)
      }
    }, 700)
    return () => window.clearInterval(timer)
  }, [run, history])

  const startSearch = async (payload: SearchCriteria, nextMode: "manual" | "automatic" = "manual") => {
    setStarting(true)
    try {
      const started = await api.searches.start({ ...payload, useSavedPreferences: payload.useSavedPreferences })
      setRun({ ...started, mode: nextMode })
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setStarting(false)
    }
  }

  const cancelSearch = async () => {
    if (!run) return
    try {
      const cancelled = await api.searches.cancel(run.id)
      setRun(cancelled)
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    }
  }

  const toggleAutomatic = async (enabled: boolean) => {
    try {
      const updated = await api.searches.updateAutoSettings({ enabled })
      autoSettings.setData(updated)
      toast.success(enabled ? "Automatic search enabled." : "Automatic search paused.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    }
  }

  if (run) {
    return (
      <SearchProgress
        run={run}
        onCancel={() => void cancelSearch()}
        onDone={() => {
          if (run.status === "completed") navigate("/jobs")
          else setRun(null)
        }}
      />
    )
  }

  const settings = autoSettings.data
  const runs = history.data?.results ?? []

  return (
    <div>
      <div className="page-intro">
        <h2>Find your next opportunity</h2>
        <p>Search trusted job sources manually or let SmartCover look for you.</p>
      </div>

      <ProviderStatusPanel />

      <div className="mode-tabs">
        <button
          className={mode === "manual" ? "active" : ""}
          onClick={() => setMode("manual")}
          type="button"
        >
          <Icon name="search" />
          Manual Search<small>Search when you're ready</small>
        </button>
        <button
          className={mode === "automatic" ? "active" : ""}
          onClick={() => setMode("automatic")}
          type="button"
        >
          <Icon name="sparkle" />
          Automatic Search<small>We search on schedule</small>
        </button>
      </div>

      {mode === "manual" ? (
        <section className="form-panel">
          <div className="panel-head">
            <div>
              <h3>Search criteria</h3>
              <p>We'll compare results against your CV and preferences.</p>
            </div>
            <label className="check-label">
              <input
                type="checkbox"
                checked={criteria.useSavedPreferences}
                onChange={(event) => {
                  const useSaved = event.target.checked
                  setCriteria((previous) =>
                    useSaved && savedPreferences.data
                      ? fromPreferences(savedPreferences.data, true)
                      : { ...previous, useSavedPreferences: useSaved },
                  )
                }}
              />{" "}
              Use saved preferences
            </label>
          </div>

          {savedPreferences.loading && !prefilled ? (
            <Skeleton rows={2} height={70} />
          ) : (
            <PreferencesForm
              value={toPreferences(criteria)}
              onChange={(next) => setCriteria(fromPreferences(next, criteria.useSavedPreferences))}
            />
          )}

          <div className="form-actions">
            <span>
              <Icon name="shield" /> Search settings stay private
            </span>
            <Button onClick={() => void startSearch(criteria)} icon="search" disabled={starting}>
              {starting ? "Starting…" : "Find Matching Jobs"}
            </Button>
          </div>
        </section>
      ) : (
        <div className="auto-grid">
          <section className="form-panel">
            {autoSettings.error ? (
              <ErrorState error={autoSettings.error} onRetry={() => void autoSettings.run()} inline />
            ) : !settings ? (
              <Skeleton rows={2} height={60} />
            ) : (
              <>
                <div className="auto-head">
                  <div>
                    <span className="status-icon">
                      <Icon name={settings.enabled ? "sparkle" : "pause"} />
                    </span>
                    <div>
                      <h3>Automatic search</h3>
                      <p>
                        {!settings.schedulerActive
                          ? "Needs a scheduler on the server — see below"
                          : settings.status === "error"
                            ? "The last run failed — check your sources"
                            : settings.enabled
                              ? `Active and searching ${settings.frequency}`
                              : "Paused — no scheduled searches"}
                      </p>
                    </div>
                  </div>
                  <button
                    className={`toggle ${settings.enabled ? "on" : ""}`}
                    onClick={() => void toggleAutomatic(!settings.enabled)}
                    type="button"
                    role="switch"
                    aria-checked={settings.enabled}
                    aria-label="Toggle automatic search"
                  >
                    <i />
                  </button>
                </div>

                <hr />

                {!settings.schedulerActive && settings.enabled && (
                  <p className="schedule-warning">
                    <Icon name="clock" size={14} /> This setting records your preference,
                    but nothing runs it on a timer yet. Searches will only start when you
                    run one. A scheduler needs to be enabled on the server for automatic
                    searching to work.
                  </p>
                )}

                <div className="auto-settings">
                  <div>
                    <small>Frequency</small>
                    <select
                      value={settings.frequency}
                      onChange={(event) =>
                        void api.searches
                          .updateAutoSettings({ frequency: event.target.value as "daily" | "weekly" })
                          .then(autoSettings.setData)
                      }
                    >
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </div>
                  <div>
                    <small>Scheduled time</small>
                    <select
                      value={settings.timeOfDay}
                      onChange={(event) =>
                        void api.searches
                          .updateAutoSettings({ timeOfDay: event.target.value })
                          .then(autoSettings.setData)
                      }
                    >
                      {["07:00", "08:30", "12:00", "17:00", "20:00"].map((time) => (
                        <option value={time} key={time}>
                          {time}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <small>Sources</small>
                    <b>{settings.sources.join(", ") || "None selected"}</b>
                  </div>
                  <div>
                    <small>Search criteria</small>
                    <b>Inherited from profile preferences</b>
                  </div>
                </div>

                <Button kind="secondary" onClick={() => setMode("manual")}>
                  Edit search criteria
                </Button>
              </>
            )}
          </section>

          <section className="form-panel schedule">
            <h3>Search schedule</h3>
            {settings ? (
              <>
                <div>
                  <span>
                    <Icon name="check" />
                  </span>
                  <p>
                    <small>Last successful search</small>
                    <b>{settings.lastRunAt ? formatDateTime(settings.lastRunAt) : "Not yet run"}</b>
                  </p>
                </div>
                <i />
                <div>
                  <span>
                    <Icon name="clock" />
                  </span>
                  <p>
                    <small>Next scheduled search</small>
                    <b>
                      {!settings.enabled
                        ? "Paused"
                        : settings.schedulerActive && settings.nextRunAt
                          ? formatDateTime(settings.nextRunAt)
                          : "Not scheduled"}
                    </b>
                  </p>
                </div>
              </>
            ) : (
              <Skeleton rows={2} height={52} />
            )}

            <Button
              onClick={() => void startSearch({ ...criteria, useSavedPreferences: true }, "automatic")}
              icon="play"
              disabled={starting}
            >
              Run search now
            </Button>
          </section>

          <section className="form-panel history">
            <div className="panel-head">
              <div>
                <h3>Search history</h3>
                <p>Previous manual and automatic searches.</p>
              </div>
            </div>

            {history.loading ? (
              <Skeleton rows={3} height={40} />
            ) : history.error ? (
              <ErrorState error={history.error} onRetry={() => void history.run()} inline />
            ) : runs.length ? (
              runs.map((entry) => (
                <div key={entry.id}>
                  <span className={entry.status === "failed" ? "is-error" : ""}>
                    <Icon name={entry.status === "failed" ? "close" : "check"} />
                  </span>
                  <b>{formatDateTime(entry.startedAt)}</b>
                  <small>
                    {entry.criteriaSummary} · {entry.discovered} analysed · {entry.matched} matched
                  </small>
                  <button type="button" onClick={() => navigate("/jobs")}>
                    View results
                  </button>
                </div>
              ))
            ) : (
              <EmptyState
                icon="clock"
                title="No searches yet"
                description="Run a manual search or enable automatic search to build your history."
              />
            )}
          </section>
        </div>
      )}

      {starting && mode === "manual" && (
        <div className="state-block state-loading" style={{ marginTop: 16 }}>
          <Spinner label="Starting your search…" />
        </div>
      )}
    </div>
  )
}
