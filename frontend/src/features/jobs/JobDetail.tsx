import { ErrorState, Skeleton } from "../../components/feedback/States"
import { LanguageTag } from "../../components/jobs/LanguageTag"
import { Button } from "../../components/ui/Button"
import { Badge, Company } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import { relativeTime } from "../../lib/format"
import { employmentLabel } from "../../lib/labels"
import type { ApiError } from "../../lib/errors"
import type { JobDetail as JobDetailData, JobStatus, MatchLine } from "../../types"

function MatchRow({ line }: { line: MatchLine }) {
  return (
    <div className={`match-line ${line.positive ? "good" : ""}`}>
      <span>{line.positive ? <Icon name="check" size={13} /> : "!"}</span>
      <p>
        <b>{line.title}</b>
        <small>{line.detail}</small>
      </p>
    </div>
  )
}

interface JobDetailProps {
  job: JobDetailData | null
  loading: boolean
  error: ApiError | null
  busy?: boolean
  onRetry: () => void
  onStatusChange: (status: JobStatus) => void
  onGenerateCoverLetter: () => void
}

export function JobDetail({
  job,
  loading,
  error,
  busy = false,
  onRetry,
  onStatusChange,
  onGenerateCoverLetter,
}: JobDetailProps) {
  if (loading) {
    return (
      <article className="job-detail">
        <div className="panel-pad">
          <Skeleton rows={4} height={58} />
        </div>
      </article>
    )
  }

  if (error) {
    return (
      <article className="job-detail">
        <div className="panel-pad">
          <ErrorState error={error} onRetry={onRetry} title="Could not load this job" />
        </div>
      </article>
    )
  }

  if (!job) {
    return (
      <article className="job-detail">
        <div className="panel-pad">
          <ErrorState
            error={new Error("No job selected")}
            title="Select a job"
            onRetry={undefined}
          />
        </div>
      </article>
    )
  }

  const isSaved = job.status === "saved"

  return (
    <article className="job-detail">
      <div className="detail-head">
        <div className="match-job">
          <Company job={job} large />
          <div>
            <h2>{job.title}</h2>
            <p>{job.company}</p>
          </div>
        </div>
        <div className="detail-head-actions">
          <button
            onClick={() => onStatusChange(isSaved ? "new" : "saved")}
            className={isSaved ? "saved" : ""}
            type="button"
            aria-label={isSaved ? "Remove from saved" : "Save job"}
            aria-pressed={isSaved}
            disabled={busy}
          >
            <Icon name="bookmark" />
          </button>
        </div>
      </div>

      <div className="detail-meta">
        <span>{job.location}</span>
        <i /> <span>{employmentLabel(job.employmentType)}</span>
        <i />
        <span>Posted {relativeTime(job.postedAt)}</span>
        <i />
        <a href={job.sourceUrl} target="_blank" rel="noreferrer noopener">
          {job.source} <Icon name="external" size={13} />
        </a>
      </div>

      <div className="detail-badges">
        <Badge match={job.match} />
        {/* Shown here with the matched phrase, so the claim can be checked
            against the advert rather than taken on trust. */}
        <LanguageTag job={job} showEvidence />
        {job.hasCoverLetter && <span className="badge badge-cover">Cover letter</span>}
      </div>

      <section className="why-match">
        <div className="section-title">
          <span>
            <Icon name="sparkle" />
          </span>
          <div>
            <h3>Why this job matches you</h3>
            <p>Based on your CV qualifications and job preferences.</p>
          </div>
        </div>
        <div className="analysis-grid">
          <div>
            <h4>CV Alignment</h4>
            {job.analysis.cvAlignment.length ? (
              job.analysis.cvAlignment.map((line) => <MatchRow line={line} key={line.title} />)
            ) : (
              <p className="muted">No alignment details available.</p>
            )}
          </div>
          <div>
            <h4>Preference Fit</h4>
            {job.analysis.preferenceFit.length ? (
              job.analysis.preferenceFit.map((line) => <MatchRow line={line} key={line.title} />)
            ) : (
              <p className="muted">No preference details available.</p>
            )}
          </div>
        </div>
      </section>

      <section className="description">
        {job.summary && <p>{job.summary}</p>}

        {job.responsibilities.length > 0 && (
          <>
            <h3>What you'll do</h3>
            <ul>
              {job.responsibilities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        )}

        {job.requirements.length > 0 && (
          <>
            <h3>What we're looking for</h3>
            <ul>
              {job.requirements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        )}

        <a className="original" href={job.sourceUrl} target="_blank" rel="noreferrer noopener">
          View original job posting <Icon name="external" size={14} />
        </a>
      </section>

      <div className="detail-actions">
        <Button
          kind="secondary"
          onClick={() => onStatusChange("reviewed")}
          icon="check"
          disabled={busy || job.status === "reviewed"}
        >
          Mark Reviewed
        </Button>
        <Button
          kind="secondary"
          onClick={() => onStatusChange("dismissed")}
          icon="close"
          disabled={busy || job.status === "dismissed"}
        >
          Dismiss
        </Button>
        <Button onClick={onGenerateCoverLetter} icon="sparkle" disabled={busy}>
          Generate Cover Letter
        </Button>
      </div>
    </article>
  )
}
