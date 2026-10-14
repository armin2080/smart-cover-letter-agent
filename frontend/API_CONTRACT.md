# Frontend ↔ Django API Contract

> **Status: implemented.** The Django backend in [`../backend/`](../backend) serves
> every endpoint below. See [`../backend/README.md`](../backend/README.md) for how
> to run it. This document remains the authoritative description of the payloads
> the frontend sends and expects.

The frontend is backend-ready. Every network call goes through a single typed
facade (`src/services/api.ts`) with two interchangeable implementations:

| Transport | When it is used | File |
| --- | --- | --- |
| `mockApi` | Default when no API URL is configured | `src/services/mockApi.ts` |
| `httpApi` | When `VITE_API_URL` is set (or `VITE_USE_MOCKS=false`) | `src/services/httpApi.ts` |

Switching to Django requires **no component changes** — only environment config.
The authoritative TypeScript definitions live in `src/types/api.ts`; DRF
serializers should match them field-for-field.

## Configuration

```bash
# frontend/.env.local
VITE_API_URL=http://localhost:8000/api   # or leave empty to use the dev proxy
VITE_USE_MOCKS=false
```

`vite.config.ts` proxies `/api` and `/media` to `http://localhost:8000`, so
during development you can leave `VITE_API_URL` empty and **no CORS setup is
required**. Set `DJANGO_URL` to override the proxy target.

## Authentication

JWT bearer tokens (SimpleJWT-compatible).

* `Authorization: Bearer <access>` on every authenticated request.
* Tokens are persisted in `localStorage` via `src/lib/storage.ts`.
* A `401` triggers a **single-flight** refresh against `POST /auth/refresh/`,
  then the original request is replayed exactly once. If the refresh fails, the
  token store is cleared and the user is signed out automatically.

> To switch to httpOnly cookies later, only `src/lib/storage.ts` and
> `src/lib/apiClient.ts` need to change.

## Error format

Return one of these shapes and the UI will surface it correctly:

```jsonc
{ "detail": "Human readable message." }          // preferred
{ "message": "Human readable message." }          // also accepted
{ "errors": { "email": ["Already registered."] } }// field errors
{ "email": ["Already registered."] }              // bare DRF field errors
```

Field errors are mapped onto the matching form inputs. Any non-2xx response is
normalised into an `ApiError` with `displayMessage`, `fieldErrors` and
`isRetryable` helpers (`src/lib/errors.ts`).

---

## Endpoints

All paths are relative to the API base (`/api`).

### Auth

| Method | Path | Body / Query | Response |
| --- | --- | --- | --- |
| `POST` | `/auth/register/` | `RegisterPayload` | `AuthResponse` |
| `POST` | `/auth/login/` | `{ email, password, remember? }` | `AuthResponse` |
| `POST` | `/auth/logout/` | `{ refresh }` | `204` |
| `POST` | `/auth/refresh/` | `{ refresh }` | `{ access, refresh? }` |
| `GET` | `/auth/me/` | — | `User` |
| `PATCH` | `/auth/me/` | `{ fullName?, email?, currentPassword?, newPassword? }` | `User` |

```jsonc
// AuthResponse
{
  "user": { "id": 1, "email": "a@b.com", "fullName": "Armin Keller", "createdAt": "2026-01-01T09:00:00Z" },
  "tokens": { "access": "…", "refresh": "…" }
}
```

### Jobs

| Method | Path | Query / Body | Response |
| --- | --- | --- | --- |
| `GET` | `/jobs/` | `status, q, source, location, employment_type, match, company, ordering` | `Paginated<Job>` |
| `GET` | `/jobs/counts/` | — | `{ new, reviewed, saved, dismissed }` |
| `GET` | `/jobs/{id}/` | — | `JobDetail` |
| `PATCH` | `/jobs/{id}/` | `{ status }` | `Job` |
| `GET` | `/jobs/stats/` | — | `JobStats` |
| `GET` | `/jobs/recent/` | `limit` | `Job[]` |
| `GET` | `/activity/` | `limit` | `ActivityEntry[]` |

```jsonc
// Job
{
  "id": 1,
  "title": "Product Designer",
  "company": "Northstar Labs",
  "companyInitials": "NL",
  "companyColor": "#172333",
  "location": "Berlin, Germany",
  "employmentType": "full-time",
  "postedAt": "2026-10-14T09:00:00Z",
  "source": "LinkedIn",
  "sourceUrl": "https://…",
  "match": "strong",              // "strong" | "good" | "potential"
  "status": "new",                // "new" | "reviewed" | "saved" | "dismissed"
  "skills": ["Figma", "Design systems"],
  "hasCoverLetter": false
}

// JobDetail adds:
{
  "summary": "…",
  "responsibilities": ["…"],
  "requirements": ["…"],
  "analysis": {
    "cvAlignment":    [{ "positive": true,  "title": "…", "detail": "…" }],
    "preferenceFit":  [{ "positive": false, "title": "…", "detail": "…" }]
  }
}
```

`JobStats.cards[].key` must be one of `new`, `reviewed`, `saved`,
`cover-letters` — the dashboard maps those keys to icons.

### Profile & preferences

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| `GET` | `/profile/` | — | `Profile` |
| `PATCH` | `/profile/` | `Partial<Profile>` | `Profile` |
| `PATCH` | `/profile/sections/{sectionId}/` | `{ content }` | `Profile` |
| `POST` | `/profile/cv/` | `multipart/form-data`, field **`file`** | `CvDocument` |
| `DELETE` | `/profile/cv/` | — | `204` |
| `GET` | `/profile/preferences/` | — | `Preferences` |
| `PUT` | `/profile/preferences/` | `Preferences` | `Preferences` |

```jsonc
// ProfileSection.key — one of:
// personal | summary | education | experience | skills | projects | languages | certificates
{ "id": "experience", "key": "experience", "title": "Work experience", "content": "line 1\nline 2" }

// Preferences
{
  "desiredRoles": ["Product Designer"],
  "locations": ["Berlin"],
  "radiusKm": 50,
  "employmentTypes": ["full-time"],   // full-time | part-time | working-student | internship | minijob
  "sources": ["LinkedIn", "StepStone", "Stellenwerk"],
  "keywords": ["SaaS"]
}
```

`POST /profile/cv/` should return `status: "ready"` once parsing finishes. The UI
shows an inline progress bar during upload (real `XHR` upload progress).

### Searches

| Method | Path | Body / Query | Response |
| --- | --- | --- | --- |
| `GET` | `/searches/` | — | `Paginated<SearchRun>` |
| `POST` | `/searches/` | `SearchCriteria` | `SearchRun` (status `running`) |
| `GET` | `/searches/{id}/` | — | `SearchRun` (polled ~every 700 ms) |
| `POST` | `/searches/{id}/cancel/` | — | `SearchRun` |
| `GET` | `/searches/settings/` | — | `AutoSearchSettings` |
| `PUT` | `/searches/settings/` | `Partial<AutoSearchSettings>` | `AutoSearchSettings` |

```jsonc
// SearchRun — stages drive the progress UI
{
  "id": 42,
  "mode": "manual",                 // manual | automatic
  "status": "running",              // queued | running | completed | failed
  "startedAt": "…", "finishedAt": null,
  "criteriaSummary": "Product Designer · Berlin · 50 km",
  "sources": ["LinkedIn", "StepStone"],
  "discovered": 43, "matched": 4,
  "stages": [
    { "key": "discover", "label": "Discovering job listings", "detail": "43 listings found", "state": "done" },
    { "key": "extract",  "label": "Extracting job information", "state": "active" }
  ],
  "error": null
}
```

`state` is `pending | active | done | error`. The UI polls until `status` is
`completed` or `failed`. Prefer asynchronous processing (Celery/RQ) and return
progress from `GET /searches/{id}/`.

### Cover letters

| Method | Path | Body / Query | Response |
| --- | --- | --- | --- |
| `GET` | `/cover-letters/` | `?job={jobId}` | `CoverLetter` or `null` |
| `GET` | `/cover-letters/preview/` | `?job={jobId}` | `{ job, cvLabel, language, tone, length }` |
| `POST` | `/cover-letters/` | `CoverLetterRequest` | `CoverLetter` |
| `GET` | `/cover-letters/{id}/` | — | `CoverLetter` |
| `PATCH` | `/cover-letters/{id}/` | `{ content?, language?, tone?, length? }` | `CoverLetter` |
| `POST` | `/cover-letters/{id}/regenerate/` | `Partial<CoverLetterRequest>` | `CoverLetter` |
| `GET` | `/cover-letters/{id}/pdf/` | — | `application/pdf` binary |

```jsonc
{
  "id": 1, "jobId": 2,
  "content": "Dear …",
  "language": "English",
  "tone": "professional",     // professional | confident | warm
  "length": "balanced",       // concise | balanced | detailed
  "status": "draft",          // generating | draft | saved
  "updatedAt": "…", "savedAt": null
}
```

The PDF endpoint must return raw bytes (the client fetches it as a `Blob` and
triggers the download). Generation must **never fabricate** skills, experience
or qualifications that are absent from the user's profile.

### Settings

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| `GET` | `/settings/notifications/` | — | `{ newMatches, searchCompleted, searchFailures }` |
| `PUT` | `/settings/notifications/` | `Partial<…>` | same |
| `DELETE` | `/account/` | — | `204` |

---

## Suggested Django project layout

```
backend/
  config/            # settings, urls, asgi/wsgi
  accounts/          # custom User, auth views, profile, preferences, CV upload
  jobs/              # Job, MatchAnalysis, activity, stats, saved/dismissed
  searches/          # SearchRun, SearchCriteria, AutoSearchSettings, scheduling
  cover_letters/     # CoverLetter model, Groq generation, ReportLab PDF export
```

Recommended packages: `djangorestframework`, `djangorestframework-simplejwt`,
`django-cors-headers`, `django-filter`, `drf-spectacular`, `reportlab`,
`groq`. Mount the routers under `/api/`.

## Matching rules the UI assumes

* `match` is **qualitative only** (`strong` / `good` / `potential`) — never a
  percentage. The UI renders "Strong match", "Good match", "Potential match".
* Matching must combine **CV qualifications** *and* **user preferences**, and the
  two must be explainable separately via `analysis.cvAlignment` and
  `analysis.preferenceFit`.
* `postedAt`, `occurredAt`, `updatedAt` etc. must be ISO-8601 UTC so the client
  can render relative times.

## Verifying the contract

```bash
cd frontend
npm run dev          # runs against mockApi
npm run typecheck
npm run build

# once Django is running:
VITE_API_URL=http://localhost:8000/api npm run dev
```

Compare behaviour: with mocks the top bar shows a **“Sample data”** pill;
against the real API that pill disappears automatically.
