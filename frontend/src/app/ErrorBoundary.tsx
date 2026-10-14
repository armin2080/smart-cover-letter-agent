import { Component, type ErrorInfo, type ReactNode } from "react"
import { createCrashScreen } from "./crashScreen"

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Keeps a render error in one screen from taking the whole app down.
 *
 * Without a boundary, React unmounts the entire tree when a component throws
 * during render, which leaves the user on a blank white page with no
 * explanation, no navigation, and nothing to report. Catching here means the
 * failure stays visible and recoverable.
 *
 * The screen itself is plain DOM (`crashScreen.ts`) so it still renders if the
 * stylesheet or a lazy chunk is what failed.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the full stack in the console for debugging; the screen shows only
    // the message so it stays readable.
    console.error("[SmartCover] A screen failed to render:", error)
    console.error("[SmartCover] Component stack:", info.componentStack)
  }

  private reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div
        ref={(node) => {
          // The screen is built with DOM APIs for the reasons above. Guard
          // against React re-running this ref on every commit.
          if (node && !node.hasChildNodes()) {
            node.appendChild(
              createCrashScreen({
                badge: "Something went wrong",
                title: "This screen could not be displayed.",
                body:
                  "Your saved jobs, profile and searches are unaffected. Reloading usually " +
                  "clears this. If it keeps happening, the message below identifies the cause.",
                message: error.message,
                onRetry: this.reset,
              }),
            )
          }
        }}
      />
    )
  }
}
