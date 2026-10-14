/**
 * A self-contained failure screen.
 *
 * Built with plain DOM and inline styles rather than React, because the
 * situations it exists for are precisely the ones where React cannot be
 * relied on: an exception during the first render, a module that failed to
 * load, or a broken stylesheet. In all of those cases the user would otherwise
 * stare at a blank white page with no explanation and nothing to report.
 *
 * Inline styles are deliberate. If the CSS bundle is what broke, a
 * class-based screen would render as unstyled text.
 */

export interface CrashScreenOptions {
  /** Small label above the heading, e.g. "Something went wrong". */
  badge: string
  title: string
  body: string
  /** Technical detail. Shown so the failure can be reported accurately. */
  message?: string
  onReload?: () => void
  onRetry?: () => void
}

const SHELL = [
  "position:fixed",
  "inset:0",
  "display:grid",
  "place-items:center",
  "padding:24px",
  "overflow:auto",
  "background:#f6f7f9",
  "color:#172333",
  'font:400 14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
  "z-index:9999",
].join(";")

const CARD = [
  "width:100%",
  "max-width:560px",
  "background:#fff",
  "border:1px solid #e3e6ea",
  "border-radius:14px",
  "padding:28px",
  "box-shadow:0 12px 40px rgba(23,35,51,0.10)",
].join(";")

const BADGE = [
  "display:inline-block",
  "margin-bottom:10px",
  "padding:3px 10px",
  "border-radius:999px",
  "background:#fdecea",
  "color:#a4291c",
  "font-size:11px",
  "font-weight:600",
  "letter-spacing:0.06em",
  "text-transform:uppercase",
].join(";")

const TITLE = "margin:0 0 8px;font-size:20px;font-weight:600;letter-spacing:-0.01em"
const BODY = "margin:0 0 16px;color:#5b6675"

const PRE = [
  "margin:0 0 18px",
  "padding:12px 14px",
  "max-height:180px",
  "overflow:auto",
  "background:#f2f4f6",
  "border:1px solid #e3e6ea",
  "border-radius:8px",
  'font:400 12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace',
  "white-space:pre-wrap",
  "word-break:break-word",
  "color:#39424f",
].join(";")

const ACTIONS = "display:flex;gap:10px;flex-wrap:wrap"

const BUTTON = [
  "appearance:none",
  "border:1px solid transparent",
  "border-radius:9px",
  "padding:10px 18px",
  "background:#172333",
  "color:#fff",
  "font:inherit",
  "font-weight:600",
  "cursor:pointer",
].join(";")

const BUTTON_QUIET = [
  BUTTON,
  "background:#fff",
  "border-color:#d6dbe1",
  "color:#172333",
].join(";")

/** True when a crash screen is already on screen (never stack two). */
export function hasCrashScreen(): boolean {
  return Boolean(document.querySelector("[data-crash-screen]"))
}

export function createCrashScreen(options: CrashScreenOptions): HTMLDivElement {
  const shell = document.createElement("div")
  shell.dataset.crashScreen = "true"
  shell.setAttribute("role", "alert")
  shell.style.cssText = SHELL

  const card = document.createElement("div")
  card.style.cssText = CARD

  const badge = document.createElement("span")
  badge.style.cssText = BADGE
  badge.textContent = options.badge

  const title = document.createElement("h1")
  title.style.cssText = TITLE
  title.textContent = options.title

  const body = document.createElement("p")
  body.style.cssText = BODY
  body.textContent = options.body

  card.append(badge, title, body)

  if (options.message) {
    const pre = document.createElement("pre")
    pre.style.cssText = PRE
    // textContent, never innerHTML: the message is untrusted input.
    pre.textContent = options.message
    card.appendChild(pre)
  }

  const actions = document.createElement("div")
  actions.style.cssText = ACTIONS

  const reload = document.createElement("button")
  reload.type = "button"
  reload.style.cssText = BUTTON
  reload.textContent = "Reload the app"
  reload.addEventListener("click", options.onReload ?? (() => window.location.reload()))
  actions.appendChild(reload)

  if (options.onRetry) {
    const retry = document.createElement("button")
    retry.type = "button"
    retry.style.cssText = BUTTON_QUIET
    retry.textContent = "Try again"
    retry.addEventListener("click", options.onRetry)
    actions.appendChild(retry)
  }

  card.appendChild(actions)
  shell.appendChild(card)
  return shell
}

/** Replace whatever is in `#root` with the crash screen. */
export function mountCrashScreen(options: CrashScreenOptions): void {
  const root = document.getElementById("root")
  if (!root || hasCrashScreen()) return
  root.replaceChildren(createCrashScreen(options))
}
