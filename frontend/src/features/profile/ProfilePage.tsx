import { useEffect, useRef, useState } from "react"
import { useToast } from "../../app/ToastProvider"
import { ErrorState, Skeleton } from "../../components/feedback/States"
import { PreferencesForm } from "../../components/profile/PreferencesForm"
import { SectionsEditor } from "../../components/profile/SectionsEditor"
import { Button } from "../../components/ui/Button"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { normalizeError } from "../../lib/errors"
import { formatBytes, formatDate } from "../../lib/format"
import { employmentLabel } from "../../lib/labels"
import { api } from "../../services/api"
import type { Preferences } from "../../types"

export function ProfilePage() {
  const toast = useToast()

  const profile = useAsync((signal) => api.profile.get({ signal }), [])
  const preferences = useAsync((signal) => api.preferences.get({ signal }), [])

  const [preferencesDraft, setPreferencesDraft] = useState<Preferences | null>(null)
  const [editingPreferences, setEditingPreferences] = useState(false)
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [uploading, setUploading] = useState(false)

  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (preferences.data) setPreferencesDraft(preferences.data)
  }, [preferences.data])

  const cv = profile.data?.cv ?? null

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

  const uploadCv = async (file: File) => {
    setUploading(true)
    try {
      await api.profile.uploadCv(file)
      // Reload so newly extracted CV sections are reflected immediately.
      await profile.run()
      toast.success("CV updated and re-analysed.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setUploading(false)
    }
  }

  const savePreferences = async () => {
    if (!preferencesDraft) return
    setSavingPreferences(true)
    try {
      const saved = await api.preferences.update(preferencesDraft)
      preferences.setData(saved)
      setEditingPreferences(false)
      toast.success("Job preferences saved.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setSavingPreferences(false)
    }
  }

  if (profile.error) {
    return (
      <div>
        <div className="page-intro">
          <h2>My CV &amp; Profile</h2>
        </div>
        <ErrorState error={profile.error} onRetry={() => void profile.run()} />
      </div>
    )
  }

  return (
    <div>
      <div className="page-intro">
        <h2>My CV &amp; Profile</h2>
        <p>Keep your experience up to date for more relevant matches and applications.</p>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="visually-hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void uploadCv(file)
          event.target.value = ""
        }}
      />

      <section className="cv-card">
        {profile.loading ? (
          <div style={{ flex: 1 }}>
            <Skeleton rows={1} height={56} />
          </div>
        ) : cv ? (
          <>
            <div className="pdf large">CV</div>
            <div>
              <h3>{cv.fileName}</h3>
              <p>
                Uploaded {formatDate(cv.uploadedAt)} · {formatBytes(cv.sizeBytes)}
              </p>
              <span>
                <Icon name="check" /> Profile synced with this CV
              </span>
            </div>
            <Button
              kind="secondary"
              icon="eye"
              onClick={() => {
                if (cv.url) window.open(cv.url, "_blank", "noopener")
                else toast.info("CV preview becomes available once the file is stored by the backend.")
              }}
            >
              Preview
            </Button>
            <Button kind="secondary" icon="upload" onClick={() => fileInput.current?.click()} disabled={uploading}>
              {uploading ? "Uploading…" : "Replace CV"}
            </Button>
          </>
        ) : (
          <>
            <div className="pdf large">—</div>
            <div>
              <h3>No CV uploaded</h3>
              <p>Upload your CV to enable matching and cover letter generation.</p>
            </div>
            <Button icon="upload" onClick={() => fileInput.current?.click()} disabled={uploading}>
              {uploading ? "Uploading…" : "Upload CV"}
            </Button>
          </>
        )}
      </section>

      <div className="profile-layout">
        <main>
          <div className="group-head">
            <div>
              <h3>CV information</h3>
              <p>Used to evaluate your alignment with job requirements.</p>
            </div>
          </div>

          {profile.loading ? (
            <Skeleton rows={4} height={92} />
          ) : profile.data ? (
            <SectionsEditor sections={profile.data.sections} onSave={saveSection} />
          ) : null}
        </main>

        <aside className="preferences-card">
          <div className="group-head">
            <div>
              <h3>Job preferences</h3>
              <p>Controls search and matching. Separate from your CV qualifications.</p>
            </div>
            {!editingPreferences && preferencesDraft && (
              <button onClick={() => setEditingPreferences(true)} type="button" aria-label="Edit job preferences">
                <Icon name="edit" />
              </button>
            )}
          </div>

          {preferences.loading || !preferencesDraft ? (
            <Skeleton rows={3} height={38} />
          ) : editingPreferences ? (
            <>
              <PreferencesForm value={preferencesDraft} onChange={setPreferencesDraft} />
              <div className="state-actions" style={{ justifyContent: "flex-start" }}>
                <Button kind="ghost" onClick={() => setEditingPreferences(false)}>
                  Cancel
                </Button>
                <Button onClick={() => void savePreferences()} disabled={savingPreferences}>
                  {savingPreferences ? "Saving…" : "Save"}
                </Button>
              </div>
            </>
          ) : (
            <dl>
              <dt>Desired roles</dt>
              <dd>{preferencesDraft.desiredRoles.join(", ") || "—"}</dd>
              <dt>Locations</dt>
              <dd>{preferencesDraft.locations.join(", ") || "—"}</dd>
              <dt>Employment</dt>
              <dd>
                {preferencesDraft.employmentTypes.map((type) => employmentLabel(type)).join(", ") || "—"}
              </dd>
              <dt>Search radius</dt>
              <dd>{preferencesDraft.radiusKm} km</dd>
              <dt>Sources</dt>
              <dd>{preferencesDraft.sources.join(" · ") || "—"}</dd>
              <dt>Keywords</dt>
              <dd>{preferencesDraft.keywords.join(", ") || "—"}</dd>
            </dl>
          )}
        </aside>
      </div>
    </div>
  )
}
