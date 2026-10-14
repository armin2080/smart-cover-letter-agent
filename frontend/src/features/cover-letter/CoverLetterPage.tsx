import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useToast } from "../../app/ToastProvider"
import { ErrorState, Skeleton, Spinner } from "../../components/feedback/States"
import { Button } from "../../components/ui/Button"
import { Company } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { downloadBlob, formatDateTime } from "../../lib/format"
import { normalizeError } from "../../lib/errors"
import { LANGUAGE_OPTIONS, LENGTH_OPTIONS, TONE_OPTIONS, lengthLabel, toneLabel } from "../../lib/labels"
import { coverLetterFileName } from "../../lib/pdf"
import { api } from "../../services/api"
import type { CoverLength, CoverTone } from "../../types"

const GENERATION_STAGES = [
  "Reading the job requirements",
  "Comparing them with your CV",
  "Drafting your letter",
]

export function CoverLetterPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { jobId: jobIdParam } = useParams<{ jobId?: string }>()

  const jobId = Number(jobIdParam)
  const validJobId = Number.isFinite(jobId) && jobId > 0

  const [content, setContent] = useState("")
  const [language, setLanguage] = useState(LANGUAGE_OPTIONS[0])
  const [tone, setTone] = useState<CoverTone>("professional")
  const [length, setLength] = useState<CoverLength>("balanced")
  const [instructions, setInstructions] = useState("")
  const [dirty, setDirty] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)

  useEffect(() => {
    if (!validJobId) navigate("/jobs", { replace: true })
  }, [validJobId, navigate])

  const data = useAsync(
    async (signal) => {
      if (!validJobId) return null
      const [letter, preview] = await Promise.all([
        api.coverLetters.forJob(jobId, { signal }),
        api.coverLetters.generationPreview(jobId, { signal }),
      ])
      return { letter, preview }
    },
    [validJobId, jobId],
  )

  // Hydrate the editor whenever a letter is loaded or replaced.
  const letter = data.data?.letter ?? null
  const preview = data.data?.preview ?? null

  useEffect(() => {
    if (!letter) return
    setContent(letter.content)
    setLanguage(letter.language)
    setTone(letter.tone)
    setLength(letter.length)
    setDirty(false)
  }, [letter])

  const generate = async () => {
    setGenerating(true)
    try {
      const created = await api.coverLetters.generate({ jobId, language, tone, length, instructions })
      data.setData((previous) => (previous ? { ...previous, letter: created } : previous))
      toast.success("Cover letter drafted.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setGenerating(false)
    }
  }

  const save = async () => {
    if (!letter) return
    setBusy(true)
    try {
      const saved = await api.coverLetters.save(letter.id, { content, language, tone, length })
      data.setData((previous) => (previous ? { ...previous, letter: saved } : previous))
      setDirty(false)
      toast.success("Cover letter saved.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setBusy(false)
    }
  }

  const regenerate = async () => {
    if (!letter) return
    setBusy(true)
    try {
      const updated = await api.coverLetters.regenerate(letter.id, {
        language,
        tone,
        length,
        instructions,
        jobId,
      })
      data.setData((previous) => (previous ? { ...previous, letter: updated } : previous))
      toast.success("Draft regenerated.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setBusy(false)
    }
  }

  const downloadPdf = async () => {
    if (!letter || !preview) return
    setBusy(true)
    try {
      const blob = await api.coverLetters.downloadPdf(letter.id)
      downloadBlob(blob, coverLetterFileName(preview.job.company, preview.job.title))
      toast.success("PDF downloaded.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setBusy(false)
    }
  }

  if (data.loading) {
    return (
      <div className="cover-page">
        <div className="cover-toolbar">
          <div>
            <button onClick={() => navigate("/jobs")} type="button">
              ← My Jobs
            </button>
            <h2>Cover letter</h2>
            <p>Loading…</p>
          </div>
        </div>
        <div style={{ padding: 32 }}>
          <Skeleton rows={5} height={64} />
        </div>
      </div>
    )
  }

  if (data.error || !preview) {
    return (
      <div className="cover-page">
        <div className="cover-toolbar">
          <div>
            <button onClick={() => navigate("/jobs")} type="button">
              ← My Jobs
            </button>
            <h2>Cover letter</h2>
          </div>
        </div>
        <div style={{ padding: 32 }}>
          <ErrorState
            error={data.error ?? new Error("This job could not be found.")}
            title="We could not open this cover letter"
            onRetry={() => void data.run()}
          />
        </div>
      </div>
    )
  }

  const job = preview.job

  /* ------------------------------ Generation ----------------------------- */

  if (!letter) {
    return (
      <div className="cover-page">
        <div className="cover-toolbar">
          <div>
            <button onClick={() => navigate("/jobs")} type="button">
              ← My Jobs
            </button>
            <h2>Cover letter for {job.company}</h2>
            <p>No letter yet for this role.</p>
          </div>
        </div>

        <div className="generation-panel">
          <div className="match-job">
            <Company job={job} large />
            <div>
              <h3>{job.title}</h3>
              <p>
                {job.company} · {job.location}
              </p>
            </div>
          </div>

          <div className="generation-meta">
            <span>
              <Icon name="file" /> CV: {preview.cvLabel}
            </span>
            <span>
              <Icon name="sparkle" /> Language: {language}
            </span>
          </div>

          {generating ? (
            <div className="state-block state-loading">
              <Spinner label="Drafting your cover letter…" />
              <div className="stage-list" style={{ maxWidth: 380 }}>
                {GENERATION_STAGES.map((stage) => (
                  <div className="current" key={stage}>
                    <span />
                    <b>{stage}</b>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              <p className="muted">
                We'll draft a first version grounded in your CV and this job's requirements. You can edit
                every word afterwards.
              </p>
              <div className="generation-controls">
                <label className="field">
                  <span>Language</span>
                  <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                    {LANGUAGE_OPTIONS.map((option) => (
                      <option value={option} key={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Tone</span>
                  <select value={tone} onChange={(event) => setTone(event.target.value as CoverTone)}>
                    {TONE_OPTIONS.map((option) => (
                      <option value={option} key={option}>
                        {toneLabel(option)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <Button onClick={() => void generate()} icon="sparkle">
                Generate Cover Letter
              </Button>
            </>
          )}
        </div>
      </div>
    )
  }

  /* -------------------------------- Editor ------------------------------- */

  const statusLabel = dirty ? "Draft · unsaved changes" : letter.status === "saved" ? "All changes saved" : "Draft"

  return (
    <div className="cover-page">
      <div className="cover-toolbar">
        <div>
          <button onClick={() => navigate("/jobs")} type="button">
            ← My Jobs
          </button>
          <h2>Cover letter for {job.company}</h2>
          <p>
            <span className={!dirty && letter.status === "saved" ? "saved-dot" : ""} />
            {statusLabel}
            {letter.savedAt && !dirty ? ` · saved ${formatDateTime(letter.savedAt)}` : ""}
          </p>
        </div>
        <div>
          <Button kind="secondary" onClick={() => setPreviewOpen(true)} icon="eye">
            Preview PDF
          </Button>
          <Button kind="secondary" onClick={() => void downloadPdf()} icon="download" disabled={busy}>
            Download PDF
          </Button>
          <Button onClick={() => void save()} disabled={busy || (!dirty && letter.status === "saved")}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div className="editor-layout">
        <main className="document-wrap">
          <div className="document">
            <div className="document-contact">
              <b>{preview.job.company ? "Your details from your profile" : ""}</b>
              <span>{job.title}</span>
              <span>{job.location}</span>
            </div>
            <div className="document-address">
              <span>{formatDateTime(letter.updatedAt)}</span>
              <span>
                {job.company}
                <br />
                Hiring Team
                <br />
                {job.location}
              </span>
            </div>
            <b className="subject">Application for {job.title}</b>
            <textarea
              value={content}
              onChange={(event) => {
                setContent(event.target.value)
                setDirty(true)
              }}
              aria-label="Cover letter content"
              spellCheck
            />
          </div>
        </main>

        <aside className="ai-panel">
          <div className="ai-title">
            <span>
              <Icon name="sparkle" />
            </span>
            <div>
              <h3>Writing assistant</h3>
              <p>Refine your letter with job context.</p>
            </div>
          </div>

          <label>
            Language
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              {LANGUAGE_OPTIONS.map((option) => (
                <option value={option} key={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label>
            Tone
            <div className="tone-options">
              {TONE_OPTIONS.map((option) => (
                <button
                  className={tone === option ? "active" : ""}
                  onClick={() => setTone(option)}
                  key={option}
                  type="button"
                >
                  {toneLabel(option)}
                </button>
              ))}
            </div>
          </label>

          <label>
            Length
            <select value={length} onChange={(event) => setLength(event.target.value as CoverLength)}>
              {LENGTH_OPTIONS.map((option) => (
                <option value={option} key={option}>
                  {lengthLabel(option)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Improvement instructions
            <textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="e.g. Emphasise my design systems experience…"
            />
          </label>

          <Button onClick={() => void regenerate()} icon="sparkle" className="wide" disabled={busy}>
            {busy ? "Working…" : "Regenerate draft"}
          </Button>

          <hr />

          <div className="context-title">
            <b>Job context</b>
            <button onClick={() => navigate(`/jobs`)} type="button">
              View job
            </button>
          </div>
          <div className="context-job">
            <Company job={job} />
            <span>
              <b>{job.title}</b>
              <small>
                {job.company} · {job.location}
              </small>
            </span>
          </div>
          <div className="context-skills">
            {job.skills.map((skill) => (
              <span key={skill}>{skill}</span>
            ))}
          </div>
        </aside>
      </div>

      {previewOpen && (
        <div className="modal-backdrop" onClick={() => setPreviewOpen(false)}>
          <div className="pdf-modal" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <b>PDF preview</b>
                <small>{coverLetterFileName(job.company, job.title)}</small>
              </div>
              <button onClick={() => setPreviewOpen(false)} type="button" aria-label="Close preview">
                <Icon name="close" />
              </button>
            </header>
            <div className="pdf-preview-paper">{content}</div>
            <footer>
              <Button kind="secondary" onClick={() => setPreviewOpen(false)}>
                Close
              </Button>
              <Button onClick={() => void downloadPdf()} icon="download" disabled={busy}>
                Download PDF
              </Button>
            </footer>
          </div>
        </div>
      )}
    </div>
  )
}
