/**
 * Shared frontend types.
 *
 * Domain/API contracts live in `./api`; this module re-exports them so feature
 * code can import from a single place.
 */

export type {
  AccountUpdate,
  ActivityEntry,
  AuthResponse,
  AuthTokens,
  AutoSearchSettings,
  CoverLength,
  CoverLetter,
  CoverLetterGeneration,
  CoverLetterRequest,
  CoverLetterStatus,
  CoverTone,
  CvDocument,
  EmploymentType,
  Job,
  JobCounts,
  JobDetail,
  JobFilters,
  JobSource,
  JobStats,
  JobStatus,
  LanguageCounts,
  LanguageFilter,
  LoginPayload,
  ManualImportPayload,
  MatchAnalysis,
  MatchLevel,
  MatchLine,
  NotificationSettings,
  Paginated,
  Preferences,
  Profile,
  ProfileSection,
  ProviderStatus,
  RegisterPayload,
  SearchCriteria,
  SearchFrequency,
  SearchMode,
  SearchRun,
  SearchStatus,
  StageState,
  StatCard,
  TaskStage,
  User,
} from "./api"

export type {
  ApiSurface,
  RequestOpts,
} from "../services/contract"

/** Top-level routes. */
export type Page =
  | "landing"
  | "login"
  | "register"
  | "onboarding"
  | "overview"
  | "find"
  | "jobs"
  | "cover"
  | "profile"
  | "settings"

/** Icon names available in the shared <Icon> component. */
export type IconName =
  | "grid"
  | "search"
  | "briefcase"
  | "file"
  | "settings"
  | "bell"
  | "chevron"
  | "menu"
  | "close"
  | "check"
  | "clock"
  | "sparkle"
  | "bookmark"
  | "external"
  | "upload"
  | "filter"
  | "more"
  | "arrow"
  | "pause"
  | "play"
  | "download"
  | "eye"
  | "edit"
  | "trash"
  | "shield"
  | "logout"
