import { useState, type FormEvent } from "react"
import { useToast } from "../../app/ToastProvider"
import { Button } from "../ui/Button"
import { Field } from "../ui/Field"
import { Icon } from "../ui/Icon"
import { normalizeError } from "../../lib/errors"
import { EMPLOYMENT_OPTIONS } from "../../lib/labels"
import { api } from "../../services/api"

interface ManualImportProps {
  open: boolean
  onClose: () => void
  onImported: () => void
}

const EMPTY = {
  url: "",
  title: "",
  company: "",
  location: "",
  employmentType: "",
  description: "",
  notes: "",
}

/**
 * Manual job import.
 *
 * This is the path that works without platform authorization, because it
 * performs no third-party access. The supplied URL is stored so the user can
 * open the original posting, but it is never fetched by the server — doing so
 * would be exactly the automated access the authorization gate prevents.
 */
export function ManualImportDialog({ open, onClose, onImported }: ManualImportProps) {
  const toast = useToast()
  const [form, setForm] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  if (!open) return null

  const patch = (changes: Partial<typeof EMPTY>) => setForm((previous) => ({ ...previous, ...changes }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setFieldErrors({})

    if (!form.title.trim()) {
      setFieldErrors({ title: ["A job title is required."] })
      return
    }

    setSubmitting(true)
    try {
      await api.jobs.importJob({
        url: form.url.trim() || undefined,
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location.trim(),
        employmentType: form.employmentType || undefined,
        description: form.description.trim(),
        notes: form.notes.trim(),
      })
      toast.success("Job added and matched against your profile.")
      setForm(EMPTY)
      onImported()
      onClose()
    } catch (caught) {
      const apiError = normalizeError(caught)
      setFieldErrors(apiError.fieldErrors ?? {})
      setError(apiError.displayMessage)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <b>Add a job manually</b>
            <small>Found a role yourself? Add it here and it joins your matching workflow.</small>
          </div>
          <button onClick={onClose} type="button" aria-label="Close">
            <Icon name="close" />
          </button>
        </header>

        <form onSubmit={submit} noValidate>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
            </div>
          )}

          <Field
            label="Job title *"
            placeholder="Werkstudent Softwareentwicklung (m/w/d)"
            value={form.title}
            onChange={(title) => patch({ title })}
            error={fieldErrors.title?.[0]}
          />

          <div className="form-grid">
            <Field
              label="Company"
              placeholder="Acme GmbH"
              value={form.company}
              onChange={(company) => patch({ company })}
            />
            <Field
              label="Location"
              placeholder="Dortmund, Nordrhein-Westfalen"
              value={form.location}
              onChange={(location) => patch({ location })}
            />
          </div>

          <label className="field">
            <span>Employment type</span>
            <select value={form.employmentType} onChange={(event) => patch({ employmentType: event.target.value })}>
              <option value="">Let SmartCover detect it</option>
              {EMPLOYMENT_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <small className="hint">Leave blank and we will classify it from the title and description.</small>
          </label>

          <Field
            label="Original job URL"
            placeholder="https://…"
            value={form.url}
            onChange={(url) => patch({ url })}
          />
          <p className="muted import-note">
            <Icon name="shield" size={13} /> The link is saved for you to open. We never fetch it, because that
            would be automated access to that platform.
          </p>

          <label className="field">
            <span>Job description or notes</span>
            <textarea
              rows={4}
              value={form.description}
              onChange={(event) => patch({ description: event.target.value })}
              placeholder="Paste the description or add your own notes. Used for matching."
            />
          </label>

          <div className="modal-actions">
            <Button kind="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Adding…" : "Add job"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
