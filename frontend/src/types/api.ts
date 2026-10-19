/**
 * Canonical API contracts shared by the frontend and the Django backend.
 *
 * These types describe the JSON payloads the UI expects. The Django REST
 * Framework serializers should be authored to match them exactly — see
 * `frontend/API_CONTRACT.md` for the full endpoint list.
 */

/* -------------------------------------------------------------------------- */
/* Primitives                                                                 */
/* -------------------------------------------------------------------------- */

export type JobStatus = "new" | "reviewed" | "saved" | "dismissed"
export type MatchLevel = "strong" | "good" | "potential"
export type EmploymentType = "full-time" | "part-time" | "working-student" | "internship" | "minijob"
export type JobSource = "LinkedIn" | "StepStone" | "Stellenwerk" | string

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/* -------------------------------------------------------------------------- */
/* Auth                                                                       */
/* -------------------------------------------------------------------------- */

export interface User {
  id: number
  email: string
  fullName: string
  createdAt: string
  /**
   * When the guided tour was finished or skipped, or null if not seen yet.
   *
   * Held on the account rather than in browser storage, so signing in from a
   * second device does not replay the tour.
   */
  tourCompletedAt?: string | null
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface AuthResponse {
  user: User
  tokens: AuthTokens
}

export interface RegisterPayload {
  fullName: string
  email: string
  password: string
  passwordConfirm: string
  acceptedTerms: boolean
}

export interface LoginPayload {
  email: string
  password: string
  remember?: boolean
}

/* -------------------------------------------------------------------------- */
/* Jobs                                                                       */
/* -------------------------------------------------------------------------- */

export interface Job {
  id: number
  title: string
  company: string
  companyInitials: string
  companyColor: string
  location: string
  city?: string
  region?: string
  country?: string
  employmentType: EmploymentType | string
  employmentTypeLabel?: string
  employmentTypeConfidence?: number
  employmentTypeEvidence?: string[]
  /**
   * Categories that had evidence when the type could not be decided.
   *
   * Empty when the posting stated no type at all. Non-empty on an ambiguous
   * listing, e.g. "Intern / Working Student" carries both.
   */
  employmentTypeCandidates?: string[]
  /**
   * Language the posting is written in, and what it asks of the reader.
   *
   * The boards searched are mostly German, so this is worth knowing before
   * opening an advert — particularly if you do not read German.
   */
  language?: string
  languageLabel?: string
  languageRequirement?: string
  languageRequirementLabel?: string
  /** The phrase that established the requirement, so the claim is checkable. */
  languageEvidence?: string
  workModel?: string
  postedAt: string
  collectedAt?: string
  source: JobSource
  sourceUrl: string
  match: MatchLevel
  status: JobStatus
  skills: string[]
  hasCoverLetter: boolean
  isUserProvided?: boolean
  salaryMin?: number | null
  salaryMax?: number | null
  /** Independent user-interaction timestamps. */
  reviewedAt?: string | null
  savedAt?: string | null
  dismissedAt?: string | null
}

/** Authorization and availability state of one job source. */
export interface ProviderStatus {
  source: string
  displayName: string
  status: string
  statusLabel: string
  /** True only when live collection is permitted *and* working. */
  operational: boolean
  detail: string
  termsNote: string
}

export interface ManualImportPayload {
  url?: string
  title: string
  company?: string
  location?: string
  employmentType?: string
  description?: string
  notes?: string
}

/** One row in the explainable matching analysis. */
export interface MatchLine {
  positive: boolean
  title: string
  detail: string
  /** True when the comparison could not be made, so the row is information
   *  rather than a pass or a fail. */
  neutral?: boolean
}

export interface MatchAnalysis {
  cvAlignment: MatchLine[]
  preferenceFit: MatchLine[]
}

export interface JobDetail extends Job {
  summary: string
  responsibilities: string[]
  requirements: string[]
  analysis: MatchAnalysis
}

export interface JobFilters {
  status?: JobStatus
  q?: string
  source?: string
  location?: string
  employmentType?: string
  match?: MatchLevel
  company?: string
  ordering?: "newest" | "oldest" | "match"
  /** Which postings to show, by the language they are written in. */
  language?: LanguageFilter
}

/** Which postings to keep, by the language they are written in.
 *
 *  "any" is a preference; "unknown" is not. A user may want every language, but
 *  nobody wants to filter *for* adverts whose language could not be determined —
 *  those appear only in the full list. */
export type LanguageFilter = "any" | "german" | "english"

/** Per-language tallies behind the job list's language tabs. `any` is the total,
 *  not the sum of the others: undetermined postings appear here alone. */
export interface LanguageCounts {
  any: number
  german: number
  english: number
  unknown: number
}

export interface JobCounts {
  new: number
  reviewed: number
  saved: number
  dismissed: number
  languages: LanguageCounts
}

export interface StatCard {
  key: string
  label: string
  value: number
  hint: string
}

export interface JobStats {
  cards: StatCard[]
  automaticSearchActive: boolean
  lastSearchAt: string | null
  nextSearchAt: string | null
  /**
   * Whether an external scheduler actually runs the searches.
   *
   * `automaticSearchActive` only means the *user* asked for automatic search.
   * Without a scheduler nothing fires on a timer, so `nextSearchAt` is an
   * intention rather than a promise.
   */
  schedulerActive: boolean
}

export interface ActivityEntry {
  id: number
  kind: "discovered" | "reviewed" | "saved" | "cover-letter" | "dismissed"
  title: string
  subtitle: string
  occurredAt: string
}

/* -------------------------------------------------------------------------- */
/* Profile + preferences                                                      */
/* -------------------------------------------------------------------------- */

export interface CvDocument {
  id: number
  fileName: string
  sizeBytes: number
  uploadedAt: string
  url: string | null
  status: "processing" | "ready" | "error"
}

/** A structured, independently editable CV section. */
export interface ProfileSection {
  id: string
  key:
    | "personal"
    | "summary"
    | "education"
    | "experience"
    | "skills"
    | "projects"
    | "languages"
    | "certificates"
  title: string
  content: string
}

export interface Profile {
  fullName: string
  email: string
  phone: string
  location: string
  portfolio: string
  summary: string
  sections: ProfileSection[]
  cv: CvDocument | null
}

export interface Preferences {
  desiredRoles: string[]
  locations: string[]
  radiusKm: number
  employmentTypes: EmploymentType[]
  sources: string[]
  keywords: string[]
  languageFilter: LanguageFilter
}

/* -------------------------------------------------------------------------- */
/* Searches                                                                   */
/* -------------------------------------------------------------------------- */

export type SearchMode = "manual" | "automatic"
export type SearchStatus = "queued" | "running" | "completed" | "failed"
export type StageState = "pending" | "active" | "done" | "error"

export interface TaskStage {
  key: string
  label: string
  detail?: string
  state: StageState
}

export interface SearchCriteria {
  roles: string[]
  locations: string[]
  radiusKm: number
  employmentTypes: EmploymentType[]
  sources: string[]
  keywords: string[]
  languageFilter: LanguageFilter
  useSavedPreferences: boolean
}

export interface SearchRun {
  id: number
  mode: SearchMode
  status: SearchStatus
  startedAt: string
  finishedAt: string | null
  criteriaSummary: string
  sources: string[]
  discovered: number
  matched: number
  stages: TaskStage[]
  error: string | null
}

export type SearchFrequency = "daily" | "weekly"

export interface AutoSearchSettings {
  enabled: boolean
  frequency: SearchFrequency
  timeOfDay: string
  weekday: number | null
  sources: string[]
  status: "active" | "paused" | "error"
  lastRunAt: string | null
  nextRunAt: string | null
  /** Whether a scheduler is actually wired up to run the searches. */
  schedulerActive: boolean
}

/* -------------------------------------------------------------------------- */
/* Cover letters                                                              */
/* -------------------------------------------------------------------------- */

export type CoverTone = "professional" | "confident" | "warm"
export type CoverLength = "concise" | "balanced" | "detailed"
export type CoverLetterStatus = "generating" | "draft" | "saved"

export interface CoverLetter {
  id: number
  jobId: number
  content: string
  language: string
  tone: CoverTone
  length: CoverLength
  status: CoverLetterStatus
  updatedAt: string
  savedAt: string | null
}

export interface CoverLetterRequest {
  jobId: number
  language: string
  tone: CoverTone
  length: CoverLength
  instructions?: string
}

export interface CoverLetterGeneration {
  job: Job
  cvLabel: string
  language: string
  tone: CoverTone
  stages: TaskStage[]
}

/* -------------------------------------------------------------------------- */
/* Settings                                                                   */
/* -------------------------------------------------------------------------- */

export interface NotificationSettings {
  newMatches: boolean
  searchCompleted: boolean
  searchFailures: boolean
}

export interface AccountUpdate {
  fullName?: string
  email?: string
  currentPassword?: string
  newPassword?: string
}

/* -------------------------------------------------------------------------- */
/* Public configuration                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Feature flags read before anyone signs in.
 *
 * Served by `GET /api/config/`, which is deliberately unauthenticated — the
 * login screen has to know whether to offer a signup link.
 */
export interface PublicConfig {
  /** Whether visitors may create their own account. */
  registrationEnabled: boolean
}