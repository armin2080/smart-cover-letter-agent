import { matchClass, matchLabel } from "../../lib/labels"
import type { Job, MatchLevel } from "../../types"

/** Company avatar with deterministic initials + colour. */
export function Company({
  job,
  large = false,
}: {
  job: Pick<Job, "companyColor" | "companyInitials">
  large?: boolean
}) {
  return (
    <span
      className={`company-logo ${large ? "large" : ""}`}
      style={{ backgroundColor: job.companyColor }}
      aria-hidden="true"
    >
      {job.companyInitials}
    </span>
  )
}

/** Qualitative match indicator — never a percentage. */
export function Badge({ match }: { match: MatchLevel }) {
  return <span className={`badge ${matchClass(match)}`}>{matchLabel(match)}</span>
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="logo">
      <span className="logo-mark">S</span>
      {!compact && <strong>SmartCover</strong>}
    </div>
  )
}
