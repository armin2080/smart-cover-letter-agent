import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../app/AuthProvider"
import { useToast } from "../../app/ToastProvider"
import { ErrorState, Skeleton } from "../../components/feedback/States"
import { PreferencesForm } from "../../components/profile/PreferencesForm"
import { Button } from "../../components/ui/Button"
import { Field } from "../../components/ui/Field"
import { Icon } from "../../components/ui/Icon"
import { useAsync } from "../../hooks/useAsync"
import { normalizeError } from "../../lib/errors"
import { api } from "../../services/api"
import type { IconName, NotificationSettings, Preferences } from "../../types"

type TabKey = "Account" | "Search settings" | "Notifications" | "Privacy"

const TABS: Array<[TabKey, IconName]> = [
  ["Account", "grid"],
  ["Search settings", "search"],
  ["Notifications", "bell"],
  ["Privacy", "shield"],
]

function ToggleRow({
  title,
  text,
  checked,
  onChange,
  disabled,
}: {
  title: string
  text: string
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="toggle-row">
      <div>
        <b>{title}</b>
        <p>{text}</p>
      </div>
      <button
        className={`toggle ${checked ? "on" : ""}`}
        onClick={() => onChange(!checked)}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={`Toggle ${title}`}
        disabled={disabled}
      >
        <i />
      </button>
    </div>
  )
}

export function SettingsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { user, updateAccount, logout } = useAuth()

  const [tab, setTab] = useState<TabKey>("Account")

  const [fullName, setFullName] = useState(user?.fullName ?? "")
  const [email, setEmail] = useState(user?.email ?? "")
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [savingAccount, setSavingAccount] = useState(false)

  const notifications = useAsync((signal) => api.settings.notifications({ signal }), [])
  const autoSettings = useAsync((signal) => api.searches.autoSettings({ signal }), [])
  const preferences = useAsync((signal) => api.preferences.get({ signal }), [])

  const [preferencesDraft, setPreferencesDraft] = useState<Preferences | null>(null)
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (user) {
      setFullName(user.fullName)
      setEmail(user.email)
    }
  }, [user])

  useEffect(() => {
    if (preferences.data) setPreferencesDraft(preferences.data)
  }, [preferences.data])

  const saveAccount = async () => {
    setSavingAccount(true)
    try {
      await updateAccount({
        fullName: fullName.trim(),
        email: email.trim(),
        currentPassword: currentPassword || undefined,
        newPassword: newPassword || undefined,
      })
      setCurrentPassword("")
      setNewPassword("")
      toast.success("Account updated.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setSavingAccount(false)
    }
  }

  const savePreferences = async () => {
    if (!preferencesDraft) return
    setSavingPreferences(true)
    try {
      const saved = await api.preferences.update(preferencesDraft)
      preferences.setData(saved)
      toast.success("Search preferences saved.")
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setSavingPreferences(false)
    }
  }

  const updateNotification = async (patch: Partial<NotificationSettings>) => {
    try {
      const saved = await api.settings.updateNotifications(patch)
      notifications.setData(saved)
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    }
  }

  const requestExport = () => {
    toast.info("Data export will be emailed once the backend endpoint is available.")
  }

  const deleteAccount = async () => {
    if (!window.confirm("Delete your account and all associated data? This cannot be undone.")) return
    setDeleting(true)
    try {
      await api.settings.deleteAccount()
      await logout()
      toast.success("Account deleted.")
      navigate("/", { replace: true })
    } catch (caught) {
      toast.error(normalizeError(caught).displayMessage)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div>
      <div className="page-intro">
        <h2>Settings</h2>
        <p>Manage your account, search behaviour and privacy.</p>
      </div>

      <div className="settings-layout">
        <nav>
          {TABS.map(([label, icon]) => (
            <button
              className={tab === label ? "active" : ""}
              onClick={() => setTab(label)}
              key={label}
              type="button"
            >
              <Icon name={icon} />
              {label}
            </button>
          ))}
        </nav>

        <main className="settings-panel">
          {tab === "Account" && (
            <>
              <div className="settings-head">
                <h2>Account details</h2>
                <p>Update your personal information and password.</p>
              </div>
              <div className="form-grid">
                <Field label="Full name" value={fullName} onChange={setFullName} autoComplete="name" />
                <Field
                  label="Email address"
                  type="email"
                  value={email}
                  onChange={setEmail}
                  autoComplete="email"
                />
              </div>
              <hr />
              <h3>Change password</h3>
              <div className="form-grid">
                <Field
                  label="Current password"
                  type="password"
                  placeholder="••••••••"
                  value={currentPassword}
                  onChange={setCurrentPassword}
                  autoComplete="current-password"
                />
                <Field
                  label="New password"
                  type="password"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChange={setNewPassword}
                  autoComplete="new-password"
                />
              </div>
              <Button onClick={() => void saveAccount()} disabled={savingAccount}>
                {savingAccount ? "Saving…" : "Save changes"}
              </Button>
            </>
          )}

          {tab === "Search settings" && (
            <>
              <div className="settings-head">
                <h2>Default search preferences</h2>
                <p>Applied whenever you start a new search.</p>
              </div>

              {preferences.loading || !preferencesDraft ? (
                <Skeleton rows={3} height={64} />
              ) : (
                <>
                  <PreferencesForm value={preferencesDraft} onChange={setPreferencesDraft} />
                  <Button onClick={() => void savePreferences()} disabled={savingPreferences}>
                    {savingPreferences ? "Saving…" : "Save preferences"}
                  </Button>
                </>
              )}

              <hr />

              {autoSettings.error ? (
                <ErrorState error={autoSettings.error} onRetry={() => void autoSettings.run()} inline />
              ) : autoSettings.data ? (
                <ToggleRow
                  title="Automatic search"
                  text={`Search ${autoSettings.data.frequency} using your saved preferences.`}
                  checked={autoSettings.data.enabled}
                  onChange={(enabled) =>
                    void api.searches
                      .updateAutoSettings({ enabled })
                      .then(autoSettings.setData)
                      .catch((caught) => toast.error(normalizeError(caught).displayMessage))
                  }
                />
              ) : (
                <Skeleton rows={1} height={60} />
              )}
            </>
          )}

          {tab === "Notifications" && (
            <>
              <div className="settings-head">
                <h2>Notification preferences</h2>
                <p>Choose which updates you want to receive.</p>
              </div>

              {notifications.loading ? (
                <Skeleton rows={3} height={62} />
              ) : notifications.error ? (
                <ErrorState error={notifications.error} onRetry={() => void notifications.run()} inline />
              ) : notifications.data ? (
                <>
                  <ToggleRow
                    title="New job matches"
                    text="When new relevant opportunities are found."
                    checked={notifications.data.newMatches}
                    onChange={(newMatches) => void updateNotification({ newMatches })}
                  />
                  <ToggleRow
                    title="Search completed"
                    text="A summary after each automatic search."
                    checked={notifications.data.searchCompleted}
                    onChange={(searchCompleted) => void updateNotification({ searchCompleted })}
                  />
                  <ToggleRow
                    title="Search failures"
                    text="When a source could not be searched."
                    checked={notifications.data.searchFailures}
                    onChange={(searchFailures) => void updateNotification({ searchFailures })}
                  />
                </>
              ) : null}
            </>
          )}

          {tab === "Privacy" && (
            <>
              <div className="settings-head">
                <h2>Privacy &amp; data</h2>
                <p>Control your personal data in SmartCover.</p>
              </div>

              <div className="privacy-row">
                <div>
                  <b>Download your data</b>
                  <p>Export your profile, jobs and cover letters.</p>
                </div>
                <Button kind="secondary" icon="download" onClick={requestExport}>
                  Request export
                </Button>
              </div>

              <div className="privacy-row danger-zone">
                <div>
                  <b>Delete account</b>
                  <p>Permanently remove your account and all associated data.</p>
                </div>
                <Button kind="danger" icon="trash" onClick={() => void deleteAccount()} disabled={deleting}>
                  {deleting ? "Deleting…" : "Delete account"}
                </Button>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
