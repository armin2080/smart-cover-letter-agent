import { useState, type ReactNode } from "react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"
import { Icon } from "../ui/Icon"
import { Logo } from "../ui/Common"
import { useAuth } from "../../app/AuthProvider"
import { useAsync } from "../../hooks/useAsync"
import { api, isMockMode } from "../../services/api"
import { initials, relativeTime } from "../../lib/format"
import type { ActivityEntry, IconName } from "../../types"

const TITLES: Record<string, string> = {
  overview: "Overview",
  find: "Find Jobs",
  jobs: "My Jobs",
  cover: "Cover Letter",
  profile: "My CV & Profile",
  settings: "Settings",
}

const ACTIVITY_ICON: Record<ActivityEntry["kind"], IconName> = {
  discovered: "search",
  reviewed: "check",
  saved: "bookmark",
  "cover-letter": "file",
  dismissed: "close",
}

interface NavItem {
  path: string
  label: string
  icon: IconName
}

const WORKSPACE_ITEMS: NavItem[] = [
  { path: "overview", label: "Overview", icon: "grid" },
  { path: "find", label: "Find Jobs", icon: "search" },
  { path: "jobs", label: "My Jobs", icon: "briefcase" },
]

const PERSONAL_ITEMS: NavItem[] = [
  { path: "profile", label: "My CV & Profile", icon: "file" },
  { path: "settings", label: "Settings", icon: "settings" },
]

interface ShellProps {
  children?: ReactNode
}

export function Shell({ children }: ShellProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)

  const { data: counts } = useAsync((signal) => api.jobs.counts({ signal }), [])
  const { data: activity } = useAsync((signal) => api.jobs.activity(4, { signal }), [])

  // Use the first path segment so parameterised routes (e.g. /cover/12) resolve correctly.
  const currentPath = location.pathname.split("/").filter(Boolean)[0] ?? "overview"
  const displayName = user?.fullName ?? "Your account"
  const displayEmail = user?.email ?? ""

  const go = (path: string) => {
    navigate(`/${path}`)
    setMobileOpen(false)
    setNotificationsOpen(false)
    setAccountOpen(false)
  }

  const handleLogout = async () => {
    setAccountOpen(false)
    await logout()
    navigate("/", { replace: true })
  }

  const isActive = (item: NavItem) =>
    currentPath === item.path || (currentPath === "cover" && item.path === "jobs")

  const renderNavItem = (item: NavItem) => (
    <button className={isActive(item) ? "active" : ""} onClick={() => go(item.path)} key={item.path}>
      <Icon name={item.icon} />
      {!collapsed && <span>{item.label}</span>}
      {!collapsed && item.path === "jobs" && counts?.new ? <em className="nav-count">{counts.new}</em> : null}
    </button>
  )

  return (
    <div className={`app-shell ${collapsed ? "is-collapsed" : ""}`}>
      <aside className={mobileOpen ? "mobile-open" : ""}>
        <div className="side-head">
          <Logo compact={collapsed} />
          <button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
            <Icon name="close" />
          </button>
        </div>

        <nav>
          <label>{!collapsed && "WORKSPACE"}</label>
          {WORKSPACE_ITEMS.map(renderNavItem)}
          <label>{!collapsed && "PERSONAL"}</label>
          {PERSONAL_ITEMS.map(renderNavItem)}
        </nav>

        <button className="collapse" onClick={() => setCollapsed(!collapsed)}>
          <Icon name="chevron" />
          {!collapsed && "Collapse sidebar"}
        </button>

        <button className="side-user" onClick={() => go("profile")}>
          <span className="avatar">{initials(displayName)}</span>
          {!collapsed && (
            <span>
              <b>{displayName}</b>
              <small>{displayEmail}</small>
            </span>
          )}
          {!collapsed && <Icon name="more" />}
        </button>
      </aside>

      {mobileOpen && <div className="scrim" onClick={() => setMobileOpen(false)} />}

      <div className="app-main">
        <header className="topbar">
          <div>
            <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Icon name="menu" />
            </button>
            <h1>{TITLES[currentPath] ?? "Overview"}</h1>
            {isMockMode && <span className="demo-pill">Sample data</span>}
          </div>

          <div className="top-actions">
            <button
              className="icon-button"
              aria-label="Notifications"
              aria-expanded={notificationsOpen}
              onClick={() => {
                setNotificationsOpen((open) => !open)
                setAccountOpen(false)
              }}
            >
              <Icon name="bell" />
              {activity && activity.length > 0 && <i />}
            </button>

            <button
              className="top-user"
              aria-label="Account menu"
              aria-expanded={accountOpen}
              onClick={() => {
                setAccountOpen((open) => !open)
                setNotificationsOpen(false)
              }}
            >
              <span className="avatar">{initials(displayName)}</span>
              <span>{displayName}</span>
              <Icon name="chevron" size={14} />
            </button>
          </div>

          {notificationsOpen && (
            <div className="dropdown notif">
              <div>
                <b>Recent activity</b>
                <button onClick={() => go("overview")}>View overview</button>
              </div>
              {activity?.length ? (
                activity.map((entry) => (
                  <p key={entry.id}>
                    <span className="notif-dot" />
                    <b>{entry.title}</b>
                    <small>
                      {[entry.subtitle, relativeTime(entry.occurredAt)].filter(Boolean).join(" · ")}
                    </small>
                  </p>
                ))
              ) : (
                <p className="notif-empty">Nothing new right now.</p>
              )}
            </div>
          )}

          {accountOpen && (
            <div className="dropdown account">
              <div className="account-head">
                <span className="avatar">{initials(displayName)}</span>
                <span>
                  <b>{displayName}</b>
                  <small>{displayEmail}</small>
                </span>
              </div>
              <button onClick={() => go("profile")}>
                <Icon name="file" /> My profile
              </button>
              <button onClick={() => go("settings")}>
                <Icon name="settings" /> Settings
              </button>
              <hr />
              <button onClick={handleLogout}>
                <Icon name="logout" /> Log out
              </button>
            </div>
          )}
        </header>

        <div className="page-content">{children ?? <Outlet />}</div>
      </div>
    </div>
  )
}
