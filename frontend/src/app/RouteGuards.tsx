import type { ReactNode } from "react"
import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "./AuthProvider"

function FullPageLoader() {
  return (
    <div className="page-loader">
      <span className="spinner" aria-hidden="true" />
      <span>Loading your workspace…</span>
    </div>
  )
}

/** Only rendered for signed-in users; everything else is redirected to login. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === "loading") return <FullPageLoader />
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <>{children ?? <Outlet />}</>
}

/** Login/registration pages redirect away once a session exists. */
export function RequireGuest({ children }: { children?: ReactNode }) {
  const { status } = useAuth()

  if (status === "loading") return <FullPageLoader />
  if (status === "authenticated") return <Navigate to="/overview" replace />
  return <>{children ?? <Outlet />}</>
}
