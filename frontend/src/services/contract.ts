import type {
  AccountUpdate,
  ActivityEntry,
  AuthResponse,
  AutoSearchSettings,
  CoverLetter,
  CoverLetterRequest,
  CvDocument,
  Job,
  JobCounts,
  JobDetail,
  JobFilters,
  JobStats,
  LoginPayload,
  ManualImportPayload,
  NotificationSettings,
  Paginated,
  Preferences,
  Profile,
  ProviderStatus,
  PublicConfig,
  RegisterPayload,
  SearchCriteria,
  SearchRun,
  User,
} from "../types/api"

/** Options accepted by every read method. */
export interface RequestOpts {
  signal?: AbortSignal
}

/**
 * The complete API surface consumed by the UI.
 *
 * Two implementations satisfy it:
 *  - `httpApi` — talks to the Django REST backend.
 *  - `mockApi` — in-browser stand-in used before the backend is available.
 *
 * Features depend only on this interface, so switching transports never
 * requires a component change.
 */
export interface ApiSurface {
  config: {
    /**
     * Feature flags available before authentication.
     *
     * Never rejects in practice; callers should still tolerate a failure and
     * fall back to the safe default of registration being closed.
     */
    get(opts?: RequestOpts): Promise<PublicConfig>
  }

  auth: {
    register(payload: RegisterPayload, opts?: RequestOpts): Promise<AuthResponse>
    login(payload: LoginPayload, opts?: RequestOpts): Promise<AuthResponse>
    logout(): Promise<void>
    me(opts?: RequestOpts): Promise<User>
    updateAccount(payload: AccountUpdate): Promise<User>
  }

  jobs: {
    list(filters: JobFilters, opts?: RequestOpts): Promise<Paginated<Job>>
    counts(opts?: RequestOpts): Promise<JobCounts>
    get(id: number, opts?: RequestOpts): Promise<JobDetail>
    updateStatus(id: number, status: Job["status"]): Promise<Job>
    stats(opts?: RequestOpts): Promise<JobStats>
    recent(limit?: number, opts?: RequestOpts): Promise<Job[]>
    activity(limit?: number, opts?: RequestOpts): Promise<ActivityEntry[]>
    /** Per-source authorization status. */
    providers(opts?: RequestOpts): Promise<ProviderStatus[]>
    /** Add a listing the user supplies themselves. */
    importJob(payload: ManualImportPayload): Promise<JobDetail>
    /** Independent user actions — each returns the updated job. */
    review(id: number): Promise<Job>
    toggleSave(id: number): Promise<Job>
    dismiss(id: number): Promise<Job>
    restore(id: number): Promise<Job>
  }

  profile: {
    get(opts?: RequestOpts): Promise<Profile>
    update(patch: Partial<Profile>): Promise<Profile>
    updateSection(sectionId: string, content: string): Promise<Profile>
    uploadCv(file: File, onProgress?: (percent: number) => void, signal?: AbortSignal): Promise<CvDocument>
    deleteCv(): Promise<void>
    /**
     * Record that the guided tour was finished or skipped.
     *
     * Returns the updated user so the caller can replace its cached copy
     * instead of keeping a second source of truth for `tourCompletedAt`.
     */
    markTourCompleted(): Promise<User>
  }

  preferences: {
    get(opts?: RequestOpts): Promise<Preferences>
    update(preferences: Preferences): Promise<Preferences>
  }

  searches: {
    list(opts?: RequestOpts): Promise<Paginated<SearchRun>>
    start(criteria: SearchCriteria): Promise<SearchRun>
    get(id: number, opts?: RequestOpts): Promise<SearchRun>
    cancel(id: number): Promise<SearchRun>
    autoSettings(opts?: RequestOpts): Promise<AutoSearchSettings>
    updateAutoSettings(patch: Partial<AutoSearchSettings>): Promise<AutoSearchSettings>
  }

  coverLetters: {
    forJob(jobId: number, opts?: RequestOpts): Promise<CoverLetter | null>
    generationPreview(jobId: number, opts?: RequestOpts): Promise<CoverLetterRequest & { job: Job; cvLabel: string }>
    generate(request: CoverLetterRequest): Promise<CoverLetter>
    get(id: number, opts?: RequestOpts): Promise<CoverLetter>
    save(id: number, patch: Partial<Pick<CoverLetter, "content" | "language" | "tone" | "length">>): Promise<CoverLetter>
    regenerate(id: number, options: Partial<CoverLetterRequest>): Promise<CoverLetter>
    downloadPdf(id: number): Promise<Blob>
  }

  settings: {
    notifications(opts?: RequestOpts): Promise<NotificationSettings>
    updateNotifications(patch: Partial<NotificationSettings>): Promise<NotificationSettings>
    deleteAccount(): Promise<void>
  }
}
