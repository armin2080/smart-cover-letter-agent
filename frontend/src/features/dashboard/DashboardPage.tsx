import { useNavigate } from "react-router-dom"
import { useAuth } from "../../app/AuthProvider"
import { EmptyState, ErrorState, Skeleton } from "../../components/feedback/States"
import { Button } from "../../components/ui/Button"
import { Badge, Company } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { relativeTime } from "../../lib/format"
import { greeting } from "../../lib/labels"
import { api } from "../../services/api"
import type { ActivityEntry, IconName } from "../../types"

const STAT_ICON: Record<string, IconName> = {
  new: "search",
  reviewed: "check",
  saved: "bookmark",
  "cover-letters": "file",
}

const ACTIVITY_ICON: Record<ActivityEntry["kind"], IconName> = {
  discovered: "search",
  reviewed: "check",
  saved: "bookmark",
  "cover-letter": "file",
  dismissed: "close",
}

export function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

  const dashboard = useAsync(async (signal) => {
    const [stats, recent, activity] = await Promise.all([
      api.jobs.stats({ signal }),
      api.jobs.recent(4, { signal }),
      api.jobs.activity(5, { signal }),
    ])
    return { stats, recent, activity }
  }, [])

  const firstName = (user?.fullName ?? "").trim().split(/\s+/)[0]

  if (dashboard.error) {
    return (
      <div>
        <div className="page-intro">
          <h2>{greeting()}{firstName ? `, ${firstName}` : ""}.</h2>
          <p>We could not load your dashboard right now.</p>
        </div>
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.run()} />
      </div>
    )
  }

  const { stats, recent, activity } = dashboard.data ?? {}

  return (
    <div>
      <div className="page-intro action-intro">
        <div>
          <h2>
            {greeting()}
            {firstName ? `, ${firstName}` : ""}.
          </h2>
          <p>Here's what's happening with your job search.</p>
        </div>
        <Button onClick={() => navigate("/find")} icon="search">
          Find Jobs
        </Button>
      </div>

      {/* Automatic search status */}
      {dashboard.loading ? (
        <Skeleton rows={1} height={78} />
      ) : (
        stats && (
          <div className="status-card">
            <div className="status-icon">
              <Icon name={stats.automaticSearchActive ? "sparkle" : "pause"} />
            </div>
            <div>
              <span className="status-line">
                <b>Automatic search {stats.automaticSearchActive ? "is active" : "is paused"}</b>
                <em>{stats.automaticSearchActive ? "Active" : "Paused"}</em>
              </span>
              <p>
                {stats.automaticSearchActive
                  ? "We'll keep looking for relevant roles based on your preferences."
                  : "No searches are scheduled until you re-enable automatic search."}
              </p>
            </div>
            <div className="status-times">
              <span>
                <small>Last search</small>
                <b>{stats.lastSearchAt ? relativeTime(stats.lastSearchAt) : "Never"}</b>
              </span>
              <span>
                <small>Next search</small>
                <b>
                  {stats.nextSearchAt ? relativeTime(stats.nextSearchAt) : "Not scheduled"}
                </b>
              </span>
            </div>
            <Button kind="secondary" onClick={() => navigate("/find")}>
              Manage
            </Button>
          </div>
        )
      )}

      {/* Summary cards */}
      <div className="stat-grid">
        {dashboard.loading
          ? Array.from({ length: 4 }, (_, index) => <div className="skeleton" key={index} style={{ height: 104 }} />)
          : stats?.cards.map((card) => (
              <div className="stat" key={card.key}>
                <span>
                  <Icon name={STAT_ICON[card.key] ?? "grid"} />
                </span>
                <p>{card.label}</p>
                <b>{card.value}</b>
                <small>{card.hint}</small>
              </div>
            ))}
      </div>

      <div className="dashboard-grid">
        {/* Recent matches */}
        <section className="panel">
          <div className="panel-head">
            <div>
              <h3>Recent job matches</h3>
              <p>Roles selected based on your profile.</p>
            </div>
            <button onClick={() => navigate("/jobs")}>
              View all <Icon name="arrow" size={14} />
            </button>
          </div>

          {dashboard.loading ? (
            <div className="panel-pad">
              <Skeleton rows={3} height={62} />
            </div>
          ) : recent?.length ? (
            recent.map((job) => (
              <button className="dash-job" key={job.id} onClick={() => navigate("/jobs")} type="button">
                <Company job={job} />
                <span>
                  <b>{job.title}</b>
                  <small>
                    {job.company} · {job.location}
                  </small>
                </span>
                <span className="dash-tags">
                  <Badge match={job.match} />
                  <small>{relativeTime(job.postedAt)}</small>
                </span>
                <Icon name="chevron" />
              </button>
            ))
          ) : (
            <div className="panel-pad">
              <EmptyState
                icon="search"
                title="No matches yet"
                description="Run your first search to discover roles that fit your profile."
                action={<Button onClick={() => navigate("/find")}>Find Jobs</Button>}
              />
            </div>
          )}
        </section>

        {/* Recent activity */}
        <section className="panel activity">
          <div className="panel-head">
            <div>
              <h3>Recent activity</h3>
              <p>Your latest actions.</p>
            </div>
          </div>

          {dashboard.loading ? (
            <div className="panel-pad">
              <Skeleton rows={3} height={48} />
            </div>
          ) : activity?.length ? (
            activity.map((entry) => (
              <div className="activity-row" key={entry.id}>
                <span>
                  <Icon name={ACTIVITY_ICON[entry.kind]} />
                </span>
                <div>
                  <b>{entry.title}</b>
                  <small>
                    {[entry.subtitle, relativeTime(entry.occurredAt)].filter(Boolean).join(" · ")}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <div className="panel-pad">
              <EmptyState
                icon="clock"
                title="No activity yet"
                description="Your reviews, saves and cover letters will appear here."
              />
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
