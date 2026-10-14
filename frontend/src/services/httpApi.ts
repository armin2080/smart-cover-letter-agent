import { apiClient } from "../lib/apiClient"
import { ApiError } from "../lib/errors"
import { tokenStore } from "../lib/storage"
import type {
  ActivityEntry,
  AuthResponse,
  ManualImportPayload,
  ProviderStatus,
  AutoSearchSettings,
  CoverLetter,
  CoverLetterRequest,
  CvDocument,
  Job,
  JobDetail,
  JobFilters,
  JobStats,
  LoginPayload,
  NotificationSettings,
  Paginated,
  Preferences,
  Profile,
  RegisterPayload,
  SearchCriteria,
  SearchRun,
  User,
} from "../types/api"
import type { ApiSurface, RequestOpts } from "./contract"

/* -------------------------------------------------------------------------- */
/* Upload with progress (XMLHttpRequest — fetch cannot report upload %)       */
/* -------------------------------------------------------------------------- */

function uploadWithProgress<T>(
  path: string,
  file: File,
  fieldName = "file",
  onProgress?: (percent: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open("POST", apiClient.url(path))
    request.setRequestHeader("Accept", "application/json")

    const access = tokenStore.getAccess()
    if (access) request.setRequestHeader("Authorization", `Bearer ${access}`)

    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)))
      }
    }

    request.onload = () => {
      let data: unknown = request.responseText
      try {
        data = request.responseText ? JSON.parse(request.responseText) : undefined
      } catch {
        /* keep raw text */
      }

      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100)
        resolve(data as T)
        return
      }

      const record = (data ?? {}) as Record<string, unknown>
      const message =
        (typeof record.detail === "string" && record.detail) ||
        (typeof record.message === "string" && record.message) ||
        (typeof record.error === "string" && record.error) ||
        "The upload failed."
      reject(new ApiError(message, { status: request.status, payload: data }))
    }

    request.onerror = () => reject(new ApiError("Network request failed.", { status: 0 }))
    request.onabort = () => reject(new ApiError("Upload cancelled.", { code: "aborted" }))

    if (signal) {
      if (signal.aborted) {
        request.abort()
        return
      }
      signal.addEventListener("abort", () => request.abort(), { once: true })
    }

    const form = new FormData()
    form.append(fieldName, file)
    request.send(form)
  })
}

/* -------------------------------------------------------------------------- */
/* HTTP implementation of the API surface                                     */
/* -------------------------------------------------------------------------- */

export const httpApi: ApiSurface = {
  auth: {
    register(payload: RegisterPayload, opts?: RequestOpts) {
      return apiClient.post<AuthResponse>("/auth/register/", payload, {
        anonymous: true,
        signal: opts?.signal,
      })
    },
    login(payload: LoginPayload, opts?: RequestOpts) {
      return apiClient.post<AuthResponse>("/auth/login/", payload, {
        anonymous: true,
        signal: opts?.signal,
      })
    },
    async logout() {
      try {
        await apiClient.post<void>("/auth/logout/", { refresh: tokenStore.getRefresh() })
      } catch {
        // Logout is best-effort: the local session is cleared regardless.
      }
    },
    me(opts?: RequestOpts) {
      return apiClient.get<User>("/auth/me/", { signal: opts?.signal })
    },
    updateAccount(payload) {
      return apiClient.patch<User>("/auth/me/", payload)
    },
  },

  jobs: {
    list(filters: JobFilters, opts?: RequestOpts) {
      return apiClient.get<Paginated<Job>>("/jobs/", {
        query: {
          status: filters.status,
          q: filters.q,
          source: filters.source,
          location: filters.location,
          employment_type: filters.employmentType,
          match: filters.match,
          company: filters.company,
          ordering: filters.ordering,
        },
        signal: opts?.signal,
      })
    },
    counts(opts?: RequestOpts) {
      return apiClient.get<Record<string, number>>("/jobs/counts/", { signal: opts?.signal })
    },
    get(id: number, opts?: RequestOpts) {
      return apiClient.get<JobDetail>(`/jobs/${id}/`, { signal: opts?.signal })
    },
    updateStatus(id: number, status: Job["status"]) {
      return apiClient.patch<Job>(`/jobs/${id}/`, { status })
    },
    stats(opts?: RequestOpts) {
      return apiClient.get<JobStats>("/jobs/stats/", { signal: opts?.signal })
    },
    recent(limit = 5, opts?: RequestOpts) {
      return apiClient.get<Job[]>("/jobs/recent/", { query: { limit }, signal: opts?.signal })
    },
    activity(limit = 8, opts?: RequestOpts) {
      return apiClient.get<ActivityEntry[]>("/activity/", { query: { limit }, signal: opts?.signal })
    },
    providers(opts?: RequestOpts) {
      return apiClient.get<ProviderStatus[]>("/jobs/providers/", { signal: opts?.signal })
    },
    importJob(payload) {
      return apiClient.post<JobDetail>("/jobs/import/", payload)
    },
    review(id: number) {
      return apiClient.post<Job>(`/jobs/${id}/review/`)
    },
    toggleSave(id: number) {
      return apiClient.post<Job>(`/jobs/${id}/save/`)
    },
    dismiss(id: number) {
      return apiClient.post<Job>(`/jobs/${id}/dismiss/`)
    },
    restore(id: number) {
      return apiClient.post<Job>(`/jobs/${id}/restore/`)
    },
  },

  profile: {
    get(opts?: RequestOpts) {
      return apiClient.get<Profile>("/profile/", { signal: opts?.signal })
    },
    update(patch) {
      return apiClient.patch<Profile>("/profile/", patch)
    },
    updateSection(sectionId: string, content: string) {
      return apiClient.patch<Profile>(`/profile/sections/${sectionId}/`, { content })
    },
    uploadCv(file: File, onProgress?: (percent: number) => void, signal?: AbortSignal) {
      return uploadWithProgress<CvDocument>("/profile/cv/", file, "file", onProgress, signal)
    },
    async deleteCv() {
      await apiClient.delete<void>("/profile/cv/")
    },
  },

  preferences: {
    get(opts?: RequestOpts) {
      return apiClient.get<Preferences>("/profile/preferences/", { signal: opts?.signal })
    },
    update(preferences: Preferences) {
      return apiClient.put<Preferences>("/profile/preferences/", preferences)
    },
  },

  searches: {
    list(opts?: RequestOpts) {
      return apiClient.get<Paginated<SearchRun>>("/searches/", { signal: opts?.signal })
    },
    start(criteria: SearchCriteria) {
      return apiClient.post<SearchRun>("/searches/", criteria)
    },
    get(id: number, opts?: RequestOpts) {
      return apiClient.get<SearchRun>(`/searches/${id}/`, { signal: opts?.signal })
    },
    cancel(id: number) {
      return apiClient.post<SearchRun>(`/searches/${id}/cancel/`)
    },
    autoSettings(opts?: RequestOpts) {
      return apiClient.get<AutoSearchSettings>("/searches/settings/", { signal: opts?.signal })
    },
    updateAutoSettings(patch: Partial<AutoSearchSettings>) {
      return apiClient.put<AutoSearchSettings>("/searches/settings/", patch)
    },
  },

  coverLetters: {
    forJob(jobId: number, opts?: RequestOpts) {
      return apiClient.get<CoverLetter | null>("/cover-letters/", {
        query: { job: jobId },
        signal: opts?.signal,
      })
    },
    generationPreview(jobId: number, opts?: RequestOpts) {
      return apiClient.get<CoverLetterRequest & { job: Job; cvLabel: string }>(
        "/cover-letters/preview/",
        { query: { job: jobId }, signal: opts?.signal },
      )
    },
    generate(request: CoverLetterRequest) {
      return apiClient.post<CoverLetter>("/cover-letters/", request)
    },
    get(id: number, opts?: RequestOpts) {
      return apiClient.get<CoverLetter>(`/cover-letters/${id}/`, { signal: opts?.signal })
    },
    save(id, patch) {
      return apiClient.patch<CoverLetter>(`/cover-letters/${id}/`, patch)
    },
    regenerate(id, options) {
      return apiClient.post<CoverLetter>(`/cover-letters/${id}/regenerate/`, options)
    },
    downloadPdf(id: number) {
      return apiClient.getBlob(`/cover-letters/${id}/pdf/`)
    },
  },

  settings: {
    notifications(opts?: RequestOpts) {
      return apiClient.get<NotificationSettings>("/settings/notifications/", { signal: opts?.signal })
    },
    updateNotifications(patch) {
      return apiClient.put<NotificationSettings>("/settings/notifications/", patch)
    },
    async deleteAccount() {
      await apiClient.delete<void>("/account/")
    },
  },
}
