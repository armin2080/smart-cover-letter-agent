import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useToast } from "../../app/ToastProvider"
import { EmptyState, ErrorState, Skeleton } from "../../components/feedback/States"
import { LanguageTag } from "../../components/jobs/LanguageTag"
import { Button } from "../../components/ui/Button"
import { Badge, Company } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { useDebounced } from "../../hooks/useDebounced"
import { normalizeError } from "../../lib/errors"
import { relativeTime } from "../../lib/format"
import { EMPLOYMENT_OPTIONS, LANGUAGE_TABS, MATCH_OPTIONS, SOURCE_OPTIONS, employmentLabel, statusLabel } from "../../lib/labels"
import { api } from "../../services/api"
import { ManualImportDialog } from "../../components/jobs/ManualImportDialog"
import { JobDetail } from "./JobDetail"
import type { JobFilters, JobStatus, LanguageFilter } from "../../types"

const TABS: JobStatus[] = ["new", "reviewed", "saved", "dismissed"]

interface FilterState {
  location: string
  source: string
  match: string
  employmentType: string
}

const EMPTY_FILTERS: FilterState = { location: "", source: "", match: "", employmentType: "" }

export function MyJobsPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [tab, setTab] = useState<JobStatus>("new")
  const [language, setLanguage] = useState<LanguageFilter>("any")
  const [query, setQuery] = useState("")
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  const debouncedQuery = useDebounced(query, 300)

  const listFilters: JobFilters = {
    status: tab,
    q: debouncedQuery || undefined,
    location: filters.location || undefined,
    source: filters.source || undefined,
    match: (filters.match || undefined) as JobFilters["match"],
    employmentType: filters.employmentType || undefined,
    // "any" must not be sent: undetermined languages belong in the full list,
    // so only a real narrowing is passed through.
    language: language === "any" ? undefined : language,
  }

  const jobs = useAsync((signal) => api.jobs.list(listFilters, { signal }), [
    tab,
    language,
    debouncedQuery,
    filters.location,
    filters.source,
    filters.match,
    filters.employmentType,
  ])

  const counts = useAsync((signal) => api.jobs.counts({ signal }), [])

  // Keep a valid selection as the list changes.
  useEffect(() => {
    if (!jobs.data) return
    const present = jobs.data.results.some((job) => job.id === selectedId)
    if (!present) setSelectedId(jobs.data.results[0]?.id ?? null)
  }, [jobs.data, selectedId])

  const detail = useAsync(
    (signal) => {
      if (selectedId === null) return Promise.resolve(null)
      return api.jobs.get(selectedId, { signal })
    },
    [selectedId],
    { immediate: false },
  )

  useEffect(() => {
    if (selectedId !== null) void detail.run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  /**
   * Independent actions. Saving does not clear "reviewed", and dismissing keeps
   * the earlier history — the backend stores each as its own timestamp.
   */
  const runAction = async (
    action: (id: number) => Promise<{ status: JobStatus; title: string }>,
    verb: string,
  ) => {
    if (selectedId === null) return
    setBusy(true)
    try {
      const updated = await action(selectedId)
      detail.setData((previous) => (previous ? { ...previous, status: updated.status } : previous))
      await Promise.all([jobs.run(), counts.run()])
      toast.success(`${updated.title} ${verb}.`)
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setBusy(false)
    }
  }

  const changeStatus = (status: JobStatus) => {
    if (status === "reviewed") return runAction((id) => api.jobs.review(id), "marked as reviewed")
    if (status === "saved") return runAction((id) => api.jobs.toggleSave(id), "saved")
    if (status === "dismissed") return runAction((id) => api.jobs.dismiss(id), "dismissed")
    return runAction((id) => api.jobs.restore(id), "restored")
  }

  const results = jobs.data?.results ?? []
  const activeFilters = Object.values(filters).filter(Boolean).length
  // A language selection narrows the list too, so it counts when deciding
  // whether the empty state is "nothing found" or "nothing searched yet".
  const narrowed = activeFilters > 0 || language !== "any"

  return (
    <div className="jobs-page">
      <div className="jobs-toolbar">
        <div>
          <h2>My Jobs</h2>
          <p>Review and organise opportunities matched to your profile.</p>
        </div>
        <div className="jobs-toolbar-actions">
          <Button kind="secondary" onClick={() => setImportOpen(true)} icon="upload">
            Add job
          </Button>
          <Button onClick={() => navigate("/find")} icon="search">
            Find Jobs
          </Button>
        </div>
      </div>

      <div className="jobs-tabs">
        {TABS.map((entry) => (
          <button
            className={tab === entry ? "active" : ""}
            onClick={() => setTab(entry)}
            key={entry}
            type="button"
          >
            {statusLabel(entry)}
            <span>{counts.data?.[entry] ?? 0}</span>
          </button>
        ))}
      </div>

      {/* Language is a second, independent axis: the same job list split by the
          language the advert is written in. Kept as its own bar so it composes
          with the status tabs instead of replacing them. */}
      <div className="language-tabs" role="tablist" aria-label="Filter by posting language">
        {LANGUAGE_TABS.map((entry) => (
          <button
            className={language === entry.value ? "active" : ""}
            onClick={() => setLanguage(entry.value)}
            key={entry.value}
            type="button"
            role="tab"
            aria-selected={language === entry.value}
          >
            {entry.label}
            <span>{counts.data?.languages?.[entry.value] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="jobs-workspace">
        <aside className="job-list">
          <div className="list-tools">
            <div className="search-input">
              <Icon name="search" size={14} />
              <input
                placeholder="Search jobs or companies"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search jobs or companies"
              />
            </div>
            <button
              className={filtersOpen || activeFilters ? "active" : ""}
              onClick={() => setFiltersOpen((open) => !open)}
              type="button"
              aria-label="Toggle filters"
              aria-expanded={filtersOpen}
            >
              <Icon name="filter" />
            </button>
          </div>

          {filtersOpen && (
            <div className="filter-box">
              <select
                value={filters.location}
                onChange={(event) => setFilters({ ...filters, location: event.target.value })}
                aria-label="Filter by location"
              >
                <option value="">All locations</option>
                <option value="Berlin">Berlin</option>
                <option value="Hamburg">Hamburg</option>
                <option value="Munich">Munich</option>
                <option value="Remote">Remote</option>
              </select>

              <select
                value={filters.source}
                onChange={(event) => setFilters({ ...filters, source: event.target.value })}
                aria-label="Filter by source"
              >
                <option value="">All sources</option>
                {SOURCE_OPTIONS.map((source) => (
                  <option value={source} key={source}>
                    {source}
                  </option>
                ))}
              </select>

              <select
                value={filters.match}
                onChange={(event) => setFilters({ ...filters, match: event.target.value })}
                aria-label="Filter by match level"
              >
                <option value="">Any match</option>
                {MATCH_OPTIONS.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              <select
                value={filters.employmentType}
                onChange={(event) => setFilters({ ...filters, employmentType: event.target.value })}
                aria-label="Filter by employment type"
              >
                <option value="">All types</option>
                {EMPLOYMENT_OPTIONS.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              {activeFilters > 0 && (
                <button className="clear-filters" type="button" onClick={() => setFilters(EMPTY_FILTERS)}>
                  Clear filters
                </button>
              )}
            </div>
          )}

          <div className="list-summary">
            <span>
              {results.length} {tab} {results.length === 1 ? "job" : "jobs"}
            </span>
            <button type="button" onClick={() => void jobs.run()}>
              Refresh
            </button>
          </div>

          <div className="job-scroll">
            {jobs.loading ? (
              <div style={{ padding: 12 }}>
                <Skeleton rows={3} height={132} />
              </div>
            ) : jobs.error ? (
              <div style={{ padding: 12 }}>
                <ErrorState error={jobs.error} onRetry={() => void jobs.run()} inline />
              </div>
            ) : results.length ? (
              results.map((job) => (
                <button
                  key={job.id}
                  className={`job-card ${selectedId === job.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(job.id)}
                  type="button"
                  aria-pressed={selectedId === job.id}
                >
                  <div className="job-card-top">
                    <Company job={job} />
                    <Badge match={job.match} />
                  </div>
                  <h3>{job.title}</h3>
                  <p>{job.company}</p>
                  <div className="job-meta">
                    <span>{job.location}</span>
                    <span>{employmentLabel(job.employmentType)}</span>
                    {/* Language sits with the other facts about the advert.
                        A stated requirement is shown instead of the posting's
                        language, because that is the part that affects whether
                        you can apply. */}
                    <LanguageTag job={job} />
                  </div>
                  <div className="skill-row">
                    {job.skills.slice(0, 3).map((skill) => (
                      <span key={skill}>{skill}</span>
                    ))}
                    {job.skills.length > 3 && <span>+{job.skills.length - 3}</span>}
                  </div>
                  <footer>
                    <span>{job.source}</span>
                    <small>{relativeTime(job.postedAt)}</small>
                  </footer>
                </button>
              ))
            ) : (
              <div style={{ padding: 12 }}>
                <EmptyState
                  icon="briefcase"
                  title={`No ${tab} jobs`}
                  description={
                    narrowed || debouncedQuery
                      ? "No roles match your current filters. Try adjusting or clearing them."
                      : tab === "new"
                        ? "Run a search to discover roles that fit your profile."
                        : `Jobs you mark as ${tab} will appear here.`
                  }
                  action={
                    narrowed || debouncedQuery ? (
                      <Button
                        kind="secondary"
                        onClick={() => {
                          setFilters(EMPTY_FILTERS)
                          setLanguage("any")
                          setQuery("")
                        }}
                      >
                        Clear filters
                      </Button>
                    ) : tab === "new" ? (
                      <Button onClick={() => navigate("/find")}>Find Jobs</Button>
                    ) : undefined
                  }
                />
              </div>
            )}
          </div>
        </aside>

        <JobDetail
          job={detail.data}
          loading={detail.loading && selectedId !== null}
          error={detail.error}
          busy={busy}
          onRetry={() => void detail.run()}
          onStatusChange={(status) => void changeStatus(status)}
          onGenerateCoverLetter={() => navigate(`/cover/${selectedId}`)}
        />
      </div>

      <ManualImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => void Promise.all([jobs.run(), counts.run()])}
      />
    </div>
  )
}
