import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { AuthProvider } from "./app/AuthProvider"
import { ConfigProvider } from "./app/ConfigProvider"
import { ErrorBoundary } from "./app/ErrorBoundary"
import { mountCrashScreen } from "./app/crashScreen"
import { ToastProvider } from "./app/ToastProvider"
import App from "./App"
import "./index.css"
import "./styles/app.css"

declare global {
  interface Window {
    /** Set once React has committed its first render. */
    __smartcoverReady?: boolean
  }
}

window.__smartcoverReady = false

/**
 * Surface failures that happen *before* React can mount.
 *
 * A render error is caught by `ErrorBoundary`. This handler exists for the
 * other case: a module that failed to load, or an exception thrown while the
 * tree was still being created. React never commits in those cases, so no
 * boundary can run and the page would stay blank with nothing to report.
 *
 * Once the app has mounted, errors are left alone — the screen is still usable
 * and replacing it with a full-page message would be worse than the error.
 */
function reportFatal(message: string): void {
  if (window.__smartcoverReady) return
  mountCrashScreen({
    badge: "The app could not start",
    title: "Something went wrong while loading.",
    body:
      "Reload the page. If this keeps happening, restart the dev server — a stale " +
      "module cache is the usual cause in development.",
    message,
  })
}

window.addEventListener("error", (event) => {
  // Resource failures (a missing icon, for example) carry no `error` object and
  // must not be treated as fatal.
  if (!(event.error instanceof Error)) return
  reportFatal(event.error.message)
})

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason
  if (!(reason instanceof Error)) return
  // Aborted requests are an expected part of navigation, not a failure.
  if (reason.name === "AbortError") return
  reportFatal(reason.message)
})

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ConfigProvider>
        <BrowserRouter>
          <ToastProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ToastProvider>
        </BrowserRouter>
      </ConfigProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)

// Mark the app as started once React has committed. Deferred by one frame so
// the initial commit has certainly happened.
requestAnimationFrame(() => {
  window.__smartcoverReady = true
})

