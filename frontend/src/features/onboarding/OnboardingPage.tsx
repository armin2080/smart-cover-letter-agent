import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useToast } from "../../app/ToastProvider"
import { SectionsEditor } from "../../components/profile/SectionsEditor"
import { PreferencesForm } from "../../components/profile/PreferencesForm"
import { Spinner } from "../../components/feedback/States"
import { Button } from "../../components/ui/Button"
import { Logo } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { formatBytes } from "../../lib/format"
import { normalizeError } from "../../lib/errors"
import { api } from "../../services/api"
import type { CvDocument, Preferences } from "../../types"

const ACCEPTED = /\.(pdf|docx)$/i
const MAX_BYTES = 10 * 1024 * 1024
const STEP_LABELS = ["Welcome", "Upload CV", "Review profile", "Preferences", "Ready"]

export function OnboardingPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [step, setStep] = useState(1)

  const profile = useAsync((signal) => api.profile.get({ signal }), [])
  const preferences = useAsync((signal) => api.preferences.get({ signal }), [])

  const [preferencesDraft, setPreferencesDraft] = useState<Preferences | null>(null)
  const [savingPreferences, setSavingPreferences] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedCv, setUploadedCv] = useState<CvDocument | null>(null)

  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (preferences.data) setPreferencesDraft(preferences.data)
  }, [preferences.data])

  const cv = uploadedCv ?? profile.data?.cv ?? null

  const handleFile = async (file: File) => {
    setUploadError(null)

    if (!ACCEPTED.test(file.name)) {
      setUploadError("Please upload a PDF or DOCX file.")
      return
    }
    if (file.size > MAX_BYTES) {
      setUploadError("Files must be 10 MB or smaller.")
      return
    }

    setUploading(true)
    setProgress(0)
    try {
      const document = await api.profile.uploadCv(file, setProgress)
      // The backend extracts CV sections during upload, so reload the full
      // profile before the review step renders.
      setUploadedCv(document)
      await profile.run()
      toast.success("CV uploaded and analysed.")
    } catch (caught) {
      setUploadError(normalizeError(caught).displayMessage)
    } finally {
      setUploading(false)
    }
  }

  const saveSection = async (sectionId: string, content: string) => {
    try {
      const updated = await api.profile.updateSection(sectionId, content)
      profile.setData(updated)
      toast.success("Section saved.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
      throw caught
    }
  }

  const continueFromPreferences = async () => {
    if (!preferencesDraft) return
    setSavingPreferences(true)
    try {
      const saved = await api.preferences.update(preferencesDraft)
      preferences.setData(saved)
      setStep(5)
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setSavingPreferences(false)
    }
  }

  const next = () => {
    if (step === 4) {
      void continueFromPreferences()
      return
    }
    setStep((current) => Math.min(5, current + 1))
  }

  const canContinue = step !== 2 || Boolean(cv)

  return (
    <div className="onboarding">
      <header>
        <Logo />
        <button onClick={() => navigate("/overview")}>Save &amp; exit</button>
      </header>

      <div className="onboard-progress">
        {STEP_LABELS.map((label, index) => {
          const number = index + 1
          return (
            <div key={label} className={number <= step ? "done" : ""} title={label}>
              <span>{number < step ? <Icon name="check" size={13} /> : number}</span>
              <i />
            </div>
          )
        })}
      </div>

      <main className="onboard-card">
        {step === 1 && (
          <div className="center-step">
            <div className="welcome-icon">
              <Icon name="sparkle" size={26} />
            </div>
            <span className="overline">WELCOME TO SMARTCOVER</span>
            <h1>Let's build your personal job search workspace.</h1>
            <p>
              We'll start by learning about your experience and what you're looking for. It takes about five
              minutes, and you can edit everything later.
            </p>
            <div className="reassure">
              <span>
                <Icon name="shield" /> Your CV stays private
              </span>
              <span>
                <Icon name="clock" /> About 5 minutes
              </span>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div className="step-head">
              <span>STEP 2 OF 5</span>
              <h1>Upload your CV</h1>
              <p>We'll use it to understand your experience and find better-matched opportunities.</p>
            </div>

            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="visually-hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void handleFile(file)
                event.target.value = ""
              }}
            />

            <button
              className="dropzone"
              type="button"
              disabled={uploading}
              onClick={() => fileInput.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                const file = event.dataTransfer.files?.[0]
                if (file) void handleFile(file)
              }}
            >
              <span>
                <Icon name="upload" size={24} />
              </span>
              <b>{uploading ? "Uploading…" : "Drop your CV here or browse files"}</b>
              <small>PDF or DOCX · Maximum 10 MB</small>
            </button>

            {uploadError && (
              <div className="error-banner" role="alert" style={{ marginTop: 12 }}>
                <span>{uploadError}</span>
              </div>
            )}

            {cv && (
              <div className="upload-file">
                <div className="pdf">PDF</div>
                <div>
                  <b>{cv.fileName}</b>
                  <small>
                    {uploading ? `Uploading… ${progress}%` : `${formatBytes(cv.sizeBytes)} · Uploaded`}
                  </small>
                  <i>
                    <em style={{ width: `${progress}%` }} />
                  </i>
                </div>
                {!uploading && <Icon name="check" />}
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div>
            <div className="step-head">
              <span>STEP 3 OF 5</span>
              <h1>Review your profile</h1>
              <p>We extracted these details from your CV. Make any changes before continuing.</p>
            </div>

            {profile.loading ? (
              <div className="state-block state-loading">
                <Spinner label="Reading your CV…" />
              </div>
            ) : profile.data ? (
              <SectionsEditor sections={profile.data.sections} onSave={saveSection} />
            ) : (
              <div className="error-banner" role="alert">
                <span>We could not load your profile.</span>
                <button onClick={() => void profile.run()}>Retry</button>
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div>
            <div className="step-head">
              <span>STEP 4 OF 5</span>
              <h1>Set your job preferences</h1>
              <p>
                These settings guide your matches. We combine them with your CV qualifications to decide
                relevance.
              </p>
            </div>

            {preferences.loading || !preferencesDraft ? (
              <div className="state-block state-loading">
                <Spinner label="Loading preferences…" />
              </div>
            ) : (
              <PreferencesForm value={preferencesDraft} onChange={setPreferencesDraft} />
            )}
          </div>
        )}

        {step === 5 && (
          <div className="center-step">
            <div className="complete-icon">
              <Icon name="check" size={28} />
            </div>
            <span className="overline">YOU'RE ALL SET</span>
            <h1>Your job search workspace is ready.</h1>
            <p>
              We've created your profile and saved your search preferences. Let's discover opportunities that
              fit.
            </p>
            <div className="ready-summary">
              <span>
                <Icon name="file" />
                <b>CV analysed</b>
                <small>{uploadedCv?.fileName ?? profile.data?.cv?.fileName ?? "No CV uploaded"}</small>
              </span>
              <span>
                <Icon name="search" />
                <b>Preferences saved</b>
                <small>
                  {preferencesDraft?.desiredRoles.length ?? 0} titles ·{" "}
                  {preferencesDraft?.locations.length ?? 0} locations ·{" "}
                  {preferencesDraft?.sources.length ?? 0} sources
                </small>
              </span>
            </div>
          </div>
        )}

        <div className="onboard-actions">
          {step > 1 && step < 5 ? (
            <Button kind="secondary" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          ) : (
            <span />
          )}

          <Button onClick={next} disabled={!canContinue || savingPreferences}>
            {step === 1
              ? "Set up my profile"
              : step === 4
                ? savingPreferences
                  ? "Saving…"
                  : "Save preferences"
                : step === 5
                  ? "Explore Your Dashboard"
                  : "Continue"}{" "}
            <Icon name="arrow" size={16} />
          </Button>
        </div>
      </main>
    </div>
  )
}
