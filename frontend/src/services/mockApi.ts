/**
 * In-browser mock transport.
 *
 * Implements the exact `ApiSurface` contract using in-memory state, so the
 * application is fully usable before the Django backend exists. Switching to
 * the real API requires only setting `VITE_API_URL` (or `VITE_USE_MOCKS=false`).
 *
 * State is intentionally ephemeral: reloading the page restores the seed data.
 */

import {
  SEED_ACTIVITY,
  SEED_AUTO_SETTINGS,
  SEED_COVER_LETTER,
  SEED_JOBS,
  SEED_NOTIFICATIONS,
  SEED_PREFERENCES,
  SEED_PROFILE,
  SEED_SEARCH_HISTORY,
  SEED_USER,
} from "../data/seed"
import { ApiError } from "../lib/errors"
import { createTextPdf } from "../lib/pdf"
import { companyColor } from "../lib/format"
import type {
  ActivityEntry,
  AuthResponse,
  AutoSearchSettings,
  CoverLetter,
  CoverLetterRequest,
  CvDocument,
  Job,
  JobDetail,
  JobFilters,
  JobStats,
  MatchLevel,
  NotificationSettings,
  Paginated,
  Preferences,
  Profile,
  SearchRun,
  StageState,
  TaskStage,
  User,
} from "../types/api"
import type { ApiSurface } from "./contract"

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError("Request cancelled.", { code: "aborted" }))
      return
    }
    const onAbort = () => {
      clearTimeout(timer)
      reject(new ApiError("Request cancelled.", { code: "aborted" }))
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort)
      resolve()
    }, ms)
    signal?.addEventListener("abort", onAbort, { once: true })
  })
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function paginate<T>(items: T[], pageSize = 50): Paginated<T> {
  return { count: items.length, next: null, previous: null, results: items.slice(0, pageSize) }
}

const MATCH_ORDER: Record<MatchLevel, number> = { strong: 0, good: 1, potential: 2 }

/* -------------------------------------------------------------------------- */
/* Mutable in-memory state                                                    */
/* -------------------------------------------------------------------------- */

interface MockState {
  user: User
  jobs: JobDetail[]
  profile: Profile
  preferences: Preferences
  coverLetters: Map<number, CoverLetter>
  coverLetterByJob: Map<number, number>
  searches: SearchRun[]
  runs: Map<number, SearchRun>
  auto: AutoSearchSettings
  notifications: NotificationSettings
  activity: ActivityEntry[]
  nextId: number
}

const state: MockState = {
  user: clone(SEED_USER),
  jobs: clone(SEED_JOBS),
  profile: clone(SEED_PROFILE),
  preferences: clone(SEED_PREFERENCES),
  coverLetters: new Map([[SEED_COVER_LETTER.id, clone(SEED_COVER_LETTER)]]),
  coverLetterByJob: new Map([[SEED_COVER_LETTER.jobId, SEED_COVER_LETTER.id]]),
  searches: clone(SEED_SEARCH_HISTORY),
  runs: new Map(),
  auto: clone(SEED_AUTO_SETTINGS),
  notifications: clone(SEED_NOTIFICATIONS),
  activity: clone(SEED_ACTIVITY),
  nextId: 1000,
}

function nextId(): number {
  state.nextId += 1
  return state.nextId
}

function makeToken(prefix: string): string {
  return `${prefix}.${Math.random().toString(36).slice(2)}.${Date.now().toString(36)}`
}

function authResponse(): AuthResponse {
  return {
    user: clone(state.user),
    tokens: { access: makeToken("mock-access"), refresh: makeToken("mock-refresh") },
  }
}

/** Apply an independent user action, preserving the other timestamps. */
function applyAction(current: MockState, id: number, field: string, toggles = false) {
  const job = current.jobs.find((entry) => entry.id === id)
  if (!job) throw new ApiError("Job not found.", { status: 404 })

  const existing = (job as unknown as Record<string, unknown>)[field]
  if (toggles && existing) {
    ;(job as unknown as Record<string, unknown>)[field] = null
    if (field === "saved_at") job.status = job.reviewedAt ? "reviewed" : "new"
  } else {
    ;(job as unknown as Record<string, unknown>)[field] = new Date().toISOString()
    job.status = field === "dismissed_at" ? "dismissed" : field === "saved_at" ? "saved" : "reviewed"
  }
  return job
}

function logActivity(entry: Omit<ActivityEntry, "id" | "occurredAt">): void {
  state.activity.unshift({ ...entry, id: nextId(), occurredAt: new Date().toISOString() })
}

/* -------------------------------------------------------------------------- */
/* Search run simulation                                                      */
/* -------------------------------------------------------------------------- */

const SEARCH_STAGES = [
  "Discovering job listings",
  "Extracting job information",
  "Removing duplicate listings",
  "Comparing jobs against your profile",
  "Preparing matching opportunities",
]

const STAGE_DURATION = 950

function stageDetail(index: number, discovered: number): string {
  switch (index) {
    case 0:
      return `${discovered} listings found`
    case 1:
      return "Reading role requirements"
    case 2:
      return "Merging repeated postings"
    case 3:
      return "Scoring CV alignment and preferences"
    case 4:
      return "Finalising your matches"
    default:
      return ""
  }
}

/** Derive live progress from wall-clock time since the run started. */
function materialize(run: SearchRun): SearchRun {
  if (run.status === "completed" || run.status === "failed") return run

  const elapsed = Date.now() - new Date(run.startedAt).getTime()
  const activeIndex = Math.floor(elapsed / STAGE_DURATION)
  const complete = elapsed >= SEARCH_STAGES.length * STAGE_DURATION

  const stages: TaskStage[] = SEARCH_STAGES.map((label, index) => {
    let stageState: StageState = "pending"
    if (complete || index < activeIndex) stageState = "done"
    else if (index === activeIndex) stageState = "active"
    return {
      key: `stage-${index}`,
      label,
      detail: stageState === "pending" ? undefined : stageDetail(index, run.discovered),
      state: stageState,
    }
  })

  if (!complete) return { ...run, stages }

  const finished: SearchRun = {
    ...run,
    status: "completed",
    finishedAt: new Date().toISOString(),
    stages: stages.map((stage) => ({ ...stage, state: "done" as StageState })),
  }

  // Reveal new matches once the run completes.
  const fresh = state.jobs.filter((job) => job.status === "new").length
  finished.matched = Math.max(1, Math.min(run.matched, Math.max(fresh, 1)))

  state.searches.unshift(clone(finished))
  state.runs.set(run.id, finished)

  if (state.auto.enabled) {
    state.auto.lastRunAt = finished.finishedAt
    state.auto.nextRunAt = new Date(Date.now() + 24 * 3_600_000).toISOString()
  }

  logActivity({
    kind: "discovered",
    title: `${finished.matched} new matches found`,
    subtitle: `${run.mode === "automatic" ? "Automatic" : "Manual"} search · just now`,
  })

  return finished
}

/* -------------------------------------------------------------------------- */
/* Cover letter drafting                                                      */
/* -------------------------------------------------------------------------- */

function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? fullName
}

function buildLetterContent(
  job: JobDetail,
  profile: Profile,
  tone: CoverLetter["tone"],
  language: string,
): string {
  const name = firstName(profile.fullName)
  const skills = job.skills.slice(0, 3)
  const strength = job.analysis.cvAlignment.find((entry) => entry.positive)
  const opening =
    tone === "warm"
      ? `I was genuinely excited to see the ${job.title} role at ${job.company}.`
      : tone === "confident"
        ? `I am writing to apply for the ${job.title} position at ${job.company}, where I believe I can contribute from day one.`
        : `I am writing to express my interest in the ${job.title} position at ${job.company}.`

  if (language === "German") {
    return `Sehr geehrtes Team von ${job.company},

${opening.replace(/^I am writing to express my interest in/, "hiermit bewerbe ich mich für")}

In meiner aktuellen Position arbeite ich an vergleichbaren Aufgaben und bringe Erfahrung in ${skills.join(", ")} mit. ${strength ? strength.detail : ""}

Besonders spricht mich an, dass ${job.company} an Produkten arbeitet, die echten Nutzen stiften. Ich würde mich freuen, meine Erfahrung einzubringen und gemeinsam weiterzuentwickeln.

Über die Möglichkeit eines Gesprächs freue ich mich sehr. Vielen Dank für Ihre Zeit.

Mit freundlichen Grüßen,
${profile.fullName}`
  }

  return `Dear ${job.company} Hiring Team,

${opening} With experience across ${skills.join(", ")}, I see a clear overlap between your requirements and the work I do today.

${strength ? `${strength.title}. ${strength.detail}` : ""} I focus on understanding the underlying problem before proposing a solution, and I work closely with product and engineering to see ideas through to delivery.

${job.company}'s work on ${job.title.toLowerCase()} particularly resonates with me, and I would welcome the chance to contribute while continuing to grow alongside your team.

Thank you for your consideration — I would be glad to discuss how my experience could support your next stage of growth.

Sincerely,
${profile.fullName}`
}

function appendInstruction(content: string, instructions?: string): string {
  if (!instructions?.trim()) return content
  return `${content}\n\n[Refinement applied: ${instructions.trim()}]`
}

/* -------------------------------------------------------------------------- */
/* Mock API implementation                                                    */
/* -------------------------------------------------------------------------- */

export const mockApi: ApiSurface = {
  auth: {
    async register(payload): Promise<AuthResponse> {
      await delay(650)
      state.user = {
        id: nextId(),
        email: payload.email,
        fullName: payload.fullName || "New User",
        createdAt: new Date().toISOString(),
      }
      state.profile = { ...state.profile, fullName: state.user.fullName, email: state.user.email }
      return authResponse()
    },
    async login(): Promise<AuthResponse> {
      await delay(550)
      return authResponse()
    },
    async logout() {
      await delay(150)
    },
    async me() {
      await delay(200)
      return clone(state.user)
    },
    async updateAccount(payload) {
      await delay(350)
      state.user = {
        ...state.user,
        fullName: payload.fullName ?? state.user.fullName,
        email: payload.email ?? state.user.email,
      }
      state.profile = { ...state.profile, fullName: state.user.fullName, email: state.user.email }
      return clone(state.user)
    },
  },

  jobs: {
    async list(filters: JobFilters): Promise<Paginated<Job>> {
      await delay(320)
      let results = [...state.jobs]

      if (filters.status) results = results.filter((job) => job.status === filters.status)
      if (filters.source) results = results.filter((job) => job.source === filters.source)
      if (filters.location) {
        results = results.filter((job) => job.location.toLowerCase().includes(filters.location!.toLowerCase()))
      }
      if (filters.employmentType) {
        results = results.filter((job) => job.employmentType === filters.employmentType)
      }
      if (filters.match) results = results.filter((job) => job.match === filters.match)
      if (filters.company) {
        results = results.filter((job) => job.company.toLowerCase().includes(filters.company!.toLowerCase()))
      }
      if (filters.q) {
        const query = filters.q.toLowerCase()
        results = results.filter((job) =>
          `${job.title} ${job.company} ${job.location}`.toLowerCase().includes(query),
        )
      }

      const ordering = filters.ordering ?? "newest"
      results.sort((a, b) => {
        if (ordering === "oldest") return a.postedAt.localeCompare(b.postedAt)
        if (ordering === "match") {
          return MATCH_ORDER[a.match] - MATCH_ORDER[b.match] || b.postedAt.localeCompare(a.postedAt)
        }
        return b.postedAt.localeCompare(a.postedAt)
      })

      return paginate(results)
    },

    async counts() {
      await delay(120)
      return {
        new: state.jobs.filter((job) => job.status === "new").length,
        reviewed: state.jobs.filter((job) => job.status === "reviewed").length,
        saved: state.jobs.filter((job) => job.status === "saved").length,
        dismissed: state.jobs.filter((job) => job.status === "dismissed").length,
      }
    },

    async get(id: number): Promise<JobDetail> {
      await delay(240)
      const job = state.jobs.find((entry) => entry.id === id)
      if (!job) throw new ApiError("Job not found.", { status: 404 })
      return clone(job)
    },

    async updateStatus(id, status) {
      await delay(220)
      const job = state.jobs.find((entry) => entry.id === id)
      if (!job) throw new ApiError("Job not found.", { status: 404 })
      job.status = status
      logActivity({
        kind: status === "saved" ? "saved" : status === "reviewed" ? "reviewed" : "dismissed",
        title: `${job.title} marked as ${status}`,
        subtitle: `${job.company} · just now`,
      })
      return clone(job)
    },

    async stats(): Promise<JobStats> {
      await delay(300)
      return {
        cards: [
          {
            key: "new",
            label: "New matches",
            value: state.jobs.filter((job) => job.status === "new").length,
            hint: "Ready to review",
          },
          {
            key: "reviewed",
            label: "Reviewed jobs",
            value: state.jobs.filter((job) => job.status === "reviewed").length,
            hint: "Looked at recently",
          },
          {
            key: "saved",
            label: "Saved jobs",
            value: state.jobs.filter((job) => job.status === "saved").length,
            hint: "Worth revisiting",
          },
          {
            key: "cover-letters",
            label: "Cover letters",
            value: state.coverLetters.size,
            hint: "Drafted or saved",
          },
        ],
        automaticSearchActive: state.auto.enabled,
        lastSearchAt: state.auto.lastRunAt,
        nextSearchAt: state.auto.enabled ? state.auto.nextRunAt : null,
      }
    },

    async recent(limit = 5) {
      await delay(280)
      return clone(
        [...state.jobs]
          .filter((job) => job.status !== "dismissed")
          .sort((a, b) => b.postedAt.localeCompare(a.postedAt))
          .slice(0, limit),
      )
    },

    async providers() {
      await delay(120)
      // Mirrors the backend's compliance gate: no platform is operational
      // without written authorization, and the manual path always is.
      return [
        {
          source: "linkedin",
          displayName: "LinkedIn",
          status: "disabled-authorization-pending",
          statusLabel: "Disabled — authorization pending",
          operational: false,
          detail: "Live collection disabled: no written platform authorization is on record.",
          termsNote: "LinkedIn's User Agreement prohibits scraping and unauthorised automated access.",
        },
        {
          source: "stepstone",
          displayName: "StepStone",
          status: "disabled-authorization-pending",
          statusLabel: "Disabled — authorization pending",
          operational: false,
          detail: "Live collection disabled: no written platform authorization is on record.",
          termsNote: "StepStone's terms prohibit scraping for other purposes and commercial reuse.",
        },
        {
          source: "stellenwerk",
          displayName: "Stellenwerk",
          status: "disabled-authorization-pending",
          statusLabel: "Disabled — authorization pending",
          operational: false,
          detail: "Live collection disabled: no written platform authorization is on record.",
          termsNote: "Stellenwerk's legal notice restricts commercial reuse of its documents.",
        },
        {
          source: "manual",
          displayName: "Manually added",
          status: "ready",
          statusLabel: "Ready",
          operational: true,
          detail: "No third-party access is performed, so no authorization is required.",
          termsNote: "User-supplied listings.",
        },
      ]
    },

    async importJob(payload) {
      await delay(400)
      if (!payload.title?.trim()) {
        throw new ApiError("A job title is required.", { status: 400, fieldErrors: { title: ["Required."] } })
      }
      const id = nextId()
      const job: JobDetail = {
        id,
        title: payload.title.trim(),
        company: payload.company?.trim() || "Unknown company",
        companyInitials: (payload.company?.trim() || "UC").slice(0, 2).toUpperCase(),
        companyColor: companyColor(payload.company || "Unknown"),
        location: payload.location || "",
        employmentType: payload.employmentType || "unknown",
        postedAt: new Date().toISOString(),
        source: "Manual",
        sourceUrl: payload.url || "",
        match: "good",
        status: "new",
        skills: [],
        hasCoverLetter: false,
        isUserProvided: true,
        summary: payload.description || "",
        responsibilities: [],
        requirements: [],
        analysis: { cvAlignment: [], preferenceFit: [] },
      }
      state.jobs.unshift(job)
      return clone(job)
    },

    async review(id) {
      await delay(180)
      return clone(applyAction(state, id, "reviewed_at"))
    },
    async toggleSave(id) {
      await delay(180)
      return clone(applyAction(state, id, "saved_at", true))
    },
    async dismiss(id) {
      await delay(180)
      return clone(applyAction(state, id, "dismissed_at"))
    },
    async restore(id) {
      await delay(180)
      const job = state.jobs.find((entry) => entry.id === id)
      if (!job) throw new ApiError("Job not found.", { status: 404 })
      job.reviewedAt = null
      job.savedAt = null
      job.dismissedAt = null
      job.status = "new"
      return clone(job)
    },

    async activity(limit = 8) {
      await delay(240)
      return clone(
        [...state.activity]
          .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt))
          .slice(0, limit),
      )
    },
  },

  profile: {
    async get() {
      await delay(260)
      return clone(state.profile)
    },
    async update(patch) {
      await delay(340)
      state.profile = { ...state.profile, ...patch }
      return clone(state.profile)
    },
    async updateSection(sectionId, content) {
      await delay(320)
      state.profile.sections = state.profile.sections.map((section) =>
        section.id === sectionId ? { ...section, content } : section,
      )
      return clone(state.profile)
    },
    async uploadCv(file, onProgress, signal): Promise<CvDocument> {
      for (let percent = 0; percent <= 100; percent += 10) {
        await delay(90, signal)
        onProgress?.(percent)
      }
      await delay(700, signal)
      const document: CvDocument = {
        id: nextId(),
        fileName: file.name,
        sizeBytes: file.size,
        uploadedAt: new Date().toISOString(),
        url: null,
        status: "ready",
      }
      state.profile.cv = document
      return clone(document)
    },
    async deleteCv() {
      await delay(250)
      state.profile.cv = null
    },
  },

  preferences: {
    async get() {
      await delay(200)
      return clone(state.preferences)
    },
    async update(preferences) {
      await delay(320)
      state.preferences = clone(preferences)
      return clone(state.preferences)
    },
  },

  searches: {
    async list() {
      await delay(260)
      return paginate(state.searches)
    },
    async start(criteria) {
      await delay(400)
      const id = nextId()
      const run: SearchRun = {
        id,
        mode: criteria.useSavedPreferences && !criteria.roles.length ? "automatic" : "manual",
        status: "running",
        startedAt: new Date().toISOString(),
        finishedAt: null,
        criteriaSummary: [
          criteria.roles.length ? criteria.roles.join(", ") : state.preferences.desiredRoles.join(", "),
          criteria.locations.length ? criteria.locations[0] : state.preferences.locations[0],
          `${criteria.radiusKm} km`,
        ]
          .filter(Boolean)
          .join(" · "),
        sources: criteria.sources.length ? criteria.sources : state.preferences.sources,
        discovered: 38 + (id % 12),
        matched: 7 + (id % 6),
        stages: SEARCH_STAGES.map((label, index) => ({
          key: `stage-${index}`,
          label,
          state: index === 0 ? "active" : "pending",
        })),
        error: null,
      }
      state.runs.set(id, run)
      return clone(run)
    },
    async get(id) {
      const run = state.runs.get(id)
      if (!run) throw new ApiError("Search run not found.", { status: 404 })
      return clone(materialize(run))
    },
    async cancel(id) {
      const run = state.runs.get(id)
      if (!run) throw new ApiError("Search run not found.", { status: 404 })
      const cancelled: SearchRun = {
        ...run,
        status: "failed",
        finishedAt: new Date().toISOString(),
        error: "Search cancelled.",
      }
      state.runs.set(id, cancelled)
      return clone(cancelled)
    },
    async autoSettings() {
      await delay(200)
      return clone(state.auto)
    },
    async updateAutoSettings(patch) {
      await delay(320)
      state.auto = { ...state.auto, ...patch }
      state.auto.status = state.auto.enabled ? "active" : "paused"
      return clone(state.auto)
    },
  },

  coverLetters: {
    async forJob(jobId) {
      await delay(240)
      const letterId = state.coverLetterByJob.get(jobId)
      if (!letterId) return null
      const letter = state.coverLetters.get(letterId)
      return letter ? clone(letter) : null
    },
    async generationPreview(jobId) {
      await delay(200)
      const job = state.jobs.find((entry) => entry.id === jobId)
      if (!job) throw new ApiError("Job not found.", { status: 404 })
      return {
        jobId,
        language: "English",
        tone: "professional" as const,
        length: "balanced" as const,
        job: clone(job),
        cvLabel: state.profile.cv?.fileName ?? "No CV uploaded",
      }
    },
    async generate(request: CoverLetterRequest): Promise<CoverLetter> {
      await delay(2_200)
      const job = state.jobs.find((entry) => entry.id === request.jobId)
      if (!job) throw new ApiError("Job not found.", { status: 404 })

      const content = appendInstruction(
        buildLetterContent(job, state.profile, request.tone, request.language),
        request.instructions,
      )

      const existingId = state.coverLetterByJob.get(job.id)
      const letter: CoverLetter = {
        id: existingId ?? nextId(),
        jobId: job.id,
        content,
        language: request.language,
        tone: request.tone,
        length: request.length,
        status: "draft",
        updatedAt: new Date().toISOString(),
        savedAt: null,
      }

      state.coverLetters.set(letter.id, letter)
      state.coverLetterByJob.set(job.id, letter.id)
      job.hasCoverLetter = true

      logActivity({
        kind: "cover-letter",
        title: "Cover letter generated",
        subtitle: `${job.company} · just now`,
      })

      return clone(letter)
    },
    async get(id) {
      await delay(200)
      const letter = state.coverLetters.get(id)
      if (!letter) throw new ApiError("Cover letter not found.", { status: 404 })
      return clone(letter)
    },
    async save(id, patch) {
      await delay(320)
      const letter = state.coverLetters.get(id)
      if (!letter) throw new ApiError("Cover letter not found.", { status: 404 })
      const saved: CoverLetter = {
        ...letter,
        ...patch,
        status: "saved",
        updatedAt: new Date().toISOString(),
        savedAt: new Date().toISOString(),
      }
      state.coverLetters.set(id, saved)
      return clone(saved)
    },
    async regenerate(id, options) {
      await delay(1_800)
      const letter = state.coverLetters.get(id)
      if (!letter) throw new ApiError("Cover letter not found.", { status: 404 })
      const job = state.jobs.find((entry) => entry.id === letter.jobId)
      if (!job) throw new ApiError("Job not found.", { status: 404 })

      const updated: CoverLetter = {
        ...letter,
        language: options.language ?? letter.language,
        tone: options.tone ?? letter.tone,
        length: options.length ?? letter.length,
        content: appendInstruction(
          buildLetterContent(job, state.profile, options.tone ?? letter.tone, options.language ?? letter.language),
          options.instructions,
        ),
        status: "draft",
        updatedAt: new Date().toISOString(),
      }
      state.coverLetters.set(id, updated)
      return clone(updated)
    },
    async downloadPdf(id) {
      await delay(500)
      const letter = state.coverLetters.get(id)
      if (!letter) throw new ApiError("Cover letter not found.", { status: 404 })
      const job = state.jobs.find((entry) => entry.id === letter.jobId)
      const title = job ? `${job.title} — ${job.company}` : "Cover letter"
      return createTextPdf(title, letter.content)
    },
  },

  settings: {
    async notifications() {
      await delay(180)
      return clone(state.notifications)
    },
    async updateNotifications(patch) {
      await delay(260)
      state.notifications = { ...state.notifications, ...patch }
      return clone(state.notifications)
    },
    async deleteAccount() {
      await delay(500)
    },
  },
}
