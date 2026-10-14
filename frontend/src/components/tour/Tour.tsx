import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { Icon } from "../ui/Icon"

export interface TourStep {
  /**
   * Value of a `data-tour` attribute to highlight.
   *
   * Omitted for a centred step with no anchor — used for the opening and
   * closing panels, which introduce the tour rather than point at anything.
   */
  anchor?: string
  title: string
  body: string
  /** Nudge applied to the spotlight when a target is visually offset. */
  placement?: "right" | "below" | "above"
}

interface Rect {
  top: number
  left: number
  width: number
  height: number
}

interface TourProps {
  steps: TourStep[]
  onFinish: () => void
}

const PAD = 8
const TOOLTIP_WIDTH = 320
const GAP = 14

function measure(anchor: string | undefined): Rect | null {
  if (!anchor) return null
  const element = document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`)
  if (!element) return null
  // Scroll the target into view first so a sidebar item below the fold is not
  // highlighted off-screen.
  element.scrollIntoView({ block: "nearest", behavior: "smooth" })
  const box = element.getBoundingClientRect()
  return { top: box.top, left: box.left, width: box.width, height: box.height }
}

/**
 * A lightweight spotlight tour.
 *
 * Deliberately hand-rolled rather than pulling in a tour library: this is one
 * screen's worth of behaviour, and a dependency would outweigh it. It renders
 * the spotlight from a measured `getBoundingClientRect`, which keeps it correct
 * regardless of how the target is positioned.
 *
 * Accessibility: the dialog is announced, Escape closes it, and arrow keys move
 * between steps. Focus is moved into the panel so keyboard users are not left
 * behind on the page underneath.
 */
export function Tour({ steps, onFinish }: TourProps) {
  const [index, setIndex] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const step = steps[index]
  const isLast = index === steps.length - 1
  const isFirst = index === 0

  const next = useCallback(() => {
    if (isLast) onFinish()
    else setIndex((current) => current + 1)
  }, [isLast, onFinish])

  const back = useCallback(() => {
    setIndex((current) => Math.max(0, current - 1))
  }, [])

  // Measure the target for this step. useLayoutEffect so the spotlight is in
  // place before paint rather than visibly jumping after it.
  useLayoutEffect(() => {
    setRect(measure(step.anchor))
  }, [step.anchor])

  // Re-measure on resize and scroll: the spotlight is positioned from a
  // viewport rect, so it has to follow the target.
  useEffect(() => {
    const remeasure = () => setRect(measure(step.anchor))
    window.addEventListener("resize", remeasure)
    window.addEventListener("scroll", remeasure, true)
    return () => {
      window.removeEventListener("resize", remeasure)
      window.removeEventListener("scroll", remeasure, true)
    }
  }, [step.anchor])

  useEffect(() => {
    panelRef.current?.focus()
  }, [index])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onFinish()
      else if (event.key === "ArrowRight") next()
      else if (event.key === "ArrowLeft") back()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [next, back, onFinish])

  // Position the panel beside the spotlight where there is room, otherwise
  // below it. Clamped to the viewport so it can never be pushed off-screen.
  const panelStyle = (): React.CSSProperties => {
    if (!rect) {
      return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
    }

    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight
    const preferRight = rect.left + rect.width + PAD + GAP + TOOLTIP_WIDTH < viewportWidth

    const left = preferRight
      ? rect.left + rect.width + PAD + GAP
      : Math.min(Math.max(12, rect.left), viewportWidth - TOOLTIP_WIDTH - 12)

    const top = Math.min(
      Math.max(12, rect.top - PAD),
      Math.max(12, viewportHeight - 260),
    )

    return { top, left, width: TOOLTIP_WIDTH }
  }

  return (
    <div className="tour-root" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* The dark surround. Four panels rather than one overlay with a hole, so
          the target stays crisp and clickable-looking without a mask image. */}
      {rect ? (
        <>
          <div className="tour-shade" style={{ top: 0, left: 0, right: 0, height: Math.max(0, rect.top - PAD) }} />
          <div
            className="tour-shade"
            style={{ top: rect.top + rect.height + PAD, left: 0, right: 0, bottom: 0 }}
          />
          <div
            className="tour-shade"
            style={{ top: Math.max(0, rect.top - PAD), left: 0, width: Math.max(0, rect.left - PAD), height: rect.height + PAD * 2 }}
          />
          <div
            className="tour-shade"
            style={{
              top: Math.max(0, rect.top - PAD),
              left: rect.left + rect.width + PAD,
              right: 0,
              height: rect.height + PAD * 2,
            }}
          />
          <div
            className="tour-ring"
            aria-hidden="true"
            style={{
              top: rect.top - PAD,
              left: rect.left - PAD,
              width: rect.width + PAD * 2,
              height: rect.height + PAD * 2,
            }}
          />
        </>
      ) : (
        <div className="tour-shade" style={{ inset: 0 }} />
      )}

      <div className="tour-panel" style={panelStyle()} ref={panelRef} tabIndex={-1}>
        <span className="tour-step-count">
          Step {index + 1} of {steps.length}
        </span>
        <h3 id="tour-title">{step.title}</h3>
        <p>{step.body}</p>

        <div className="tour-actions">
          <button type="button" className="tour-skip" onClick={onFinish}>
            Skip tour
          </button>
          <div>
            {!isFirst && (
              <button type="button" className="tour-back" onClick={back}>
                Back
              </button>
            )}
            <button type="button" className="tour-next" onClick={next} autoFocus>
              {isLast ? "Get started" : "Next"}
              <Icon name="arrow" size={14} />
            </button>
          </div>
        </div>

        <div className="tour-dots" aria-hidden="true">
          {steps.map((entry, dotIndex) => (
            <i key={entry.title} className={dotIndex === index ? "active" : ""} />
          ))}
        </div>
      </div>
    </div>
  )
}
