import { Icon } from "../ui/Icon"
import type { Job, JobDetail } from "../../types"

/**
 * Shows what a posting is written in, and what it asks of you.
 *
 * Two different facts, and the requirement is the one that decides whether you
 * can apply, so it takes precedence in the label. A German advert that asks for
 * "fließend Deutsch" is a different proposition from one that asks for English,
 * and a reader who does not speak German needs to see that without opening it.
 *
 * Renders nothing when neither is known — an empty badge is worse than none.
 */
export function LanguageTag({ job, showEvidence = false }: { job: Job | JobDetail; showEvidence?: boolean }) {
  const requirement = job.languageRequirement
  const stated = Boolean(requirement && requirement !== "none-stated")

  const label = stated ? job.languageRequirementLabel : job.languageLabel
  if (!label || (!stated && job.language === "unknown")) return null

  // A stated requirement is emphasised; a plain language note is not, so the
  // two do not read as equally important.
  const tone = stated ? "requirement" : "info"

  return (
    <span className={`language-tag ${tone}`} title={job.languageEvidence || undefined}>
      <Icon name={stated ? "shield" : "file"} size={12} />
      {label}
      {showEvidence && job.languageEvidence && (
        <small className="language-evidence">“{job.languageEvidence}”</small>
      )}
    </span>
  )
}
