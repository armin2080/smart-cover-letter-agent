# Smart Cover Letter Agent — Frontend

React 19 + Vite + TypeScript single-page application for the Smart Cover Letter
Agent workspace: job discovery, explainable CV matching, and AI-assisted cover
letter drafting.

The app is **backend-ready for Django** and runs **standalone today** through a
built-in mock transport.

## Quick start

```bash
npm install
cp .env.example .env.local   # optional
npm run dev                  # http://localhost:5173
```

Other scripts:

```bash
npm run typecheck   # tsc --noEmit
npm run build       # production bundle in dist/
npm run preview     # serve the production build
npm run format      # oxfmt
```

## Two transports, one API surface

All data access goes through a single typed facade, `src/services/api.ts`:

```
features/**  →  api (src/services/api.ts)  →  httpApi  →  Django REST
                                           ↘  mockApi  →  in-browser state
```

Selection is purely environmental:

| `VITE_API_URL` | `VITE_USE_MOCKS` | Result |
| --- | --- | --- |
| *(empty)* | *(empty)* | **mock** transport |
| *(empty)* | `false` | HTTP via the Vite dev proxy |
| set | *(empty)* | **HTTP** |
| set | `true` | **mock** (forced) |

When mocks are active the top bar shows a **“Sample data”** pill so demo data is
never mistaken for real results. Feature code never imports a transport
directly, so switching backends requires **zero component changes**.

See [`API_CONTRACT.md`](./API_CONTRACT.md) for the full endpoint specification
that the Django backend must implement.

## Project structure

```
src/
  app/                 AuthProvider, ToastProvider, route guards
  components/
    feedback/          Loading / error / empty states, skeletons, spinner
    layout/            Application shell (sidebar + top bar)
    profile/           SectionsEditor, PreferencesForm (shared)
    ui/                Button, Field, Icon, Common, TagInput
  data/seed.ts         Sample data used by the mock transport
  features/            One folder per product area
    auth/ onboarding/ landing/ dashboard/ find-jobs/ jobs/ cover-letter/ profile/ settings/
  hooks/               useAsync, useDebounced
  lib/
    apiClient.ts       fetch wrapper: JWT, single-flight refresh, timeouts, errors
    config.ts          environment-driven runtime configuration
    errors.ts          ApiError + normalisation
    format.ts          date/size/initials/download helpers
    labels.ts          human-readable labels and option lists
    pdf.ts             dependency-free PDF writer (offline fallback)
    storage.ts         token persistence
  services/            api facade, contract, httpApi, mockApi
  types/               api.ts (domain contracts), index.ts (re-exports + UI types)
  styles/app.css       application styles layered on index.css
```

## Conventions

* **Typed errors** — every failure is normalised to `ApiError`, which exposes
  `displayMessage`, `fieldErrors`, `isUnauthorized` and `isRetryable`.
* **Abortable requests** — `useAsync` passes an `AbortSignal` and cancels
  in-flight work on unmount, dependency change or re-run, so stale responses can
  never overwrite fresh state.
* **Loading / empty / error states** are defined for every data-backed view.
* **Accessibility** — visible `:focus-visible` rings, `aria-*` on toggles and
  icon buttons, and semantic landmarks.

## Authentication

JWT access + refresh tokens (SimpleJWT-compatible) stored via
`src/lib/storage.ts`. A `401` triggers one single-flight refresh and one replay;
a failed refresh clears the session and redirects to `/login`. Route guards
(`src/app/RouteGuards.tsx`) protect the application shell and bounce signed-in
users away from the auth pages.

## Notes

* All names, companies, figures and dates in the UI and in `src/data/seed.ts`
  are **illustrative sample data**.
* `src/lib/pdf.ts` generates a real, valid PDF client-side so downloads work
  offline. Once Django is live, PDFs should be rendered server-side (ReportLab)
  from `GET /cover-letters/{id}/pdf/`.
