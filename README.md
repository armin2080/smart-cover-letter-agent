# Smart Cover Letter Agent

Job discovery, explainable CV matching, and AI-assisted cover letter generation.

| | |
| --- | --- |
| **Frontend** | React 19 + Vite + TypeScript — [`frontend/`](frontend/) |
| **Backend** | Django 6 + DRF — [`backend/`](backend/) |
| **Telegram app** | Original Python bot, preserved — [`old version/`](old%20version/) |

The repository currently contains **two independent applications**:

1. The **web application** (`frontend/` + `backend/`) — job discovery, matching
   and cover letters, built on the Django REST API.
2. The **original Telegram bot** (`old version/`) — untouched, self-contained, and
   not wired into the web application.

## Running the stack

Two terminals.

```bash
# Terminal 1 — backend
cd backend
../.venv/bin/pip install -r requirements.txt
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py seed_demo          # optional demo data
../.venv/bin/python manage.py runserver 8000

# Terminal 2 — frontend
cd frontend
npm install

# Point the UI at Django instead of the built-in mock transport.
printf 'VITE_API_URL=\nVITE_USE_MOCKS=false\n' > .env.local

npm run dev                                       # http://localhost:5173
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so no CORS setup
is needed. Without `.env.local` the frontend runs on mock data instead. Log in
with the seeded account:

```
armin.keller@example.com
demo-password-123
```

### Running the frontend on its own

The frontend ships with an in-browser mock transport and works with no backend at
all — a **"Sample data"** pill appears in the top bar while it is active.

```bash
cd frontend && npm run dev
```

Switch transports with environment variables only (see
[`frontend/API_CONTRACT.md`](frontend/API_CONTRACT.md)):

| `VITE_API_URL` | `VITE_USE_MOCKS` | Result |
| --- | --- | --- |
| *(empty)* | *(empty)* | mock transport |
| *(empty)* | `false` | real API via the dev proxy |
| set | *(empty)* | real API |
| set | `true` | mock transport (forced) |

## Feature overview

* **Onboarding** — CV upload (PDF/DOCX) with text extraction and section mapping,
  profile review, and job preferences.
* **Find Jobs** — manual search with editable criteria, automatic scheduled
  search, staged live progress, per-source availability, and search history.
* **My Jobs** — split-view list and detail, independent status tracking (reviewed
  / saved / dismissed as separate timestamps), filters, and an explainable match
  analysis separating **CV alignment** from **preference fit**.
* **Manual import** — add a job you found yourself; it joins the same matching and
  cover-letter workflow.
* **Cover Letter** — generation grounded strictly in the user's own profile, an
  editor with tone/language/length controls, and PDF export.
* **Profile & Settings** — CV management, structured profile sections, preferences,
  notifications, and account deletion.

Relevance is deliberately **qualitative** (`Strong` / `Good` / `Potential` / `Low`)
with plain-language reasons — never an opaque percentage.

Employment type is classified from German *and* English terminology
(`Werkstudent`, `Werkstudierende`, `Praktikum`, `HiWi`, `studentische Hilfskraft`,
…), with confidence scores and the matching terms recorded for auditability.
Ambiguous listings stay `Unknown` rather than being guessed at.

### Where job results come from

**No live platform collection is enabled by default.** LinkedIn, StepStone and
Stellenwerk all restrict automated collection in their terms, and no written
authorization is on record for any of them. The adapters are implemented and
fixture-tested, but they sit behind a compliance gate that requires **both** an
explicit enable **and** a recorded authorization reference before a single request
is made.

Until then:

* Searches run against clearly-labelled **sample data**, and the run states why.
* **Manual import** (`POST /api/jobs/import/`) is the working path — users add
  listings they found themselves. It performs no third-party access, so it needs
  no authorization. The supplied URL is stored but never fetched.

The UI reports each source's real status, so it never implies a connection that
does not exist.

* [`docs/provider-authorization-matrix.md`](docs/provider-authorization-matrix.md) — per-platform status and requirements
* [`docs/job-source-setup.md`](docs/job-source-setup.md) — enabling a provider
* [`docs/job-discovery-architecture.md`](docs/job-discovery-architecture.md) — the pipeline
* [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — upstream licences and test results

## Documentation

* [`backend/README.md`](backend/README.md) — API, matching engine, search pipeline, configuration
* [`frontend/README.md`](frontend/README.md) — frontend architecture and conventions
* [`frontend/API_CONTRACT.md`](frontend/API_CONTRACT.md) — endpoint and payload contract
* [`old version/README.md`](old%20version/README.md) — the original Telegram application

## Sample data

Every company name, job listing, statistic and person referenced in the seed data,
mock transport and documentation is **illustrative sample data**, not real
information.

## Development notes

```bash
# Backend — 102 tests
cd backend && ../.venv/bin/python manage.py test

# Frontend — type check and production build
cd frontend && npm run typecheck && npm run build
```
