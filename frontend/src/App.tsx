import { Navigate, Route, Routes } from "react-router-dom"
import { RequireAuth, RequireGuest, RequireRegistrationOpen } from "./app/RouteGuards"
import { Shell } from "./components/layout/Shell"
import { AuthPage } from "./features/auth/AuthPage"
import { CoverLetterPage } from "./features/cover-letter/CoverLetterPage"
import { DashboardPage } from "./features/dashboard/DashboardPage"
import { FindJobsPage } from "./features/find-jobs/FindJobsPage"
import { MyJobsPage } from "./features/jobs/MyJobsPage"
import { LandingPage } from "./features/landing/LandingPage"
import { OnboardingPage } from "./features/onboarding/OnboardingPage"
import { ProfilePage } from "./features/profile/ProfilePage"
import { SettingsPage } from "./features/settings/SettingsPage"

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/login"
        element={
          <RequireGuest>
            <AuthPage mode="login" />
          </RequireGuest>
        }
      />
      <Route
        path="/register"
        element={
          <RequireRegistrationOpen>
            <RequireGuest>
              <AuthPage mode="register" />
            </RequireGuest>
          </RequireRegistrationOpen>
        }
      />

      {/* Authenticated */}
      <Route element={<RequireAuth />}>
        {/* Standalone layout (no sidebar) */}
        <Route path="/onboarding" element={<OnboardingPage />} />

        {/* Application shell */}
        <Route element={<Shell />}>
          <Route path="/overview" element={<DashboardPage />} />
          <Route path="/find" element={<FindJobsPage />} />
          <Route path="/jobs" element={<MyJobsPage />} />
          <Route path="/cover" element={<CoverLetterPage />} />
          <Route path="/cover/:jobId" element={<CoverLetterPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
