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

#### Evaluating the adapters before any agreement exists

`PROVIDER_TEST_MODE=true` waives the authorization requirement so the adapters can
be exercised. It is deliberately not a way to pretend permission exists:

* Providers it enables report **"Test mode — no authorization"**, never "Ready",
  and the UI shows them in amber rather than green.
* It enables nothing by itself — each provider still needs its own
  `PROVIDER_<NAME>_ENABLED=true`.
* It never overrides a genuine authorization reference, which always takes
  precedence.

Default is `false`. Leave it off for anything beyond evaluation.

## Registration

**Self-service registration is off by default.** The intended deployment is an
invitation-only pilot: accounts are created deliberately through the admin panel
(`/admin/`) or with `manage.py createsuperuser`, and the signup form is hidden.

`REGISTRATION_ENABLED=true` opens it up. The flag is served publicly by
`GET /api/config/` so the login screen knows whether to offer a signup link, and
`POST /api/auth/register/` is refused with `403` while it is closed — the backend
is the boundary, the hidden form is only a courtesy.

## Automatic search needs a scheduler

Setting "Automatic search" on only records a **preference** — it does not start
anything. The application knows *when* a search should next run, but nothing in
the web process fires on a timer, so without an external trigger the next-run
time is an intention that will never arrive.

To make it real, add a cron entry and tell the app it exists:

```bash
# Run the scheduled searches hourly
0 * * * * cd /path/to/backend && .venv/bin/python manage.py run_scheduled_searches
```

```bash
# backend/.env — so the UI reports the schedule as live
AUTO_SEARCH_SCHEDULER_ENABLED=true
```

Until both are done, `AUTO_SEARCH_SCHEDULER_ENABLED` stays `false` and the UI
says so plainly ("Automatic search is on, but not scheduled") instead of
counting down to a run that will never happen.

## No password reset

There is no self-service password reset: no mail backend is configured, and
accounts are created by an administrator. The login screen says as much rather
than offering a link that goes nowhere. To reset someone's password, use the
Django admin at `/admin/`.

If you later add an email backend, implement reset by issuing a
`PasswordResetTokenGenerator` link and remove the note in `AuthPage.tsx`.

## What a search actually looks for

Three things decide which listings a search can reach, and getting any of them
wrong is invisible — a query for the wrong string simply returns nothing, which
looks the same as a platform having no matching jobs.

**Desired roles, then profile skills.** What you asked for comes first, but the
skills in your profile are searched too. Roles say what you want; skills say
what you can do, and the two overlap only partly. A profile listing Python and
Linux should surface backend roles even when you only typed "AI".

**Every term, not just the first.** A list of themes like `["AI", "Data", "Web"]`
used to query only `"AI"`, which matches almost nothing.

**Both languages.** The listings are overwhelmingly German while the terms typed
are usually English, so the two never meet on their own:

| You type | Also searched | And these titles match |
| --- | --- | --- |
| `Web Development` | `webentwicklung` | Webentwickler, Frontendentwickler |
| `Data Science` | `datenanalyse` | Datenanalyst, Werkstudent Datenanalyse |
| `AI Engineer` | `ki`, `künstliche intelligenz` | KI-Ingenieur, KI-Entwickler |
| `Mechanical Engineering` | `maschinenbau` | Maschinenbauingenieur |

German compounds are handled too — `Maschinenbauingenieur` is `Maschinenbau` +
`Ingenieur`, which exact word matching cannot see.

The vocabulary lives in `jobs/sources/roles.py`. It is a curated list, not a
translation service: it covers the roles this product targets and grows by
adding an entry. `jobs/sources/test_roles.py` guards its coherence, including
that unrelated roles do *not* match — a matcher that says yes to everything
would look successful while being useless.

## Rate limiting

The credential endpoints are rate limited. This is not boilerplate: password
verification in Django is deliberately slow, and measured on the production
droplet (1 vCPU) a **single login attempt costs ~1.5 seconds of CPU**. An
unthrottled login route therefore lets anyone occupy the core — not by
exploiting anything, just by paying the cost of the app's own password hashing.
That machine also runs a more important service on the same core.

Three limits apply to `POST /api/auth/login/`, on independent axes:

| Scope | Default | Keyed on | Purpose |
| --- | --- | --- | --- |
| `auth-burst` | `5/min` | client IP | Stops a script hammering the route |
| `auth-sustained` | `30/hour` | client IP | Stops a slow drip under the burst limit |
| `auth-identity` | `10/hour` | submitted email | Caps attempts on one account regardless of source IP |

`/api/auth/register/` and `/api/auth/refresh/` are limited too.

All three are configurable:

```bash
THROTTLE_AUTH_BURST=5/min
THROTTLE_AUTH_SUSTAINED=30/hour
THROTTLE_AUTH_IDENTITY=10/hour
```

**Single-worker caveat.** Counters live in `LocMemCache`, which is
per-process. That is correct for the current deployment (one gunicorn worker)
and is the honest choice — the moment there is more than one worker, these
limits weaken to *per-worker* and a shared backend (Redis, Memcached) becomes
necessary. The setting is commented in `config/settings.py` so this does not
silently drift.

Tests clear throttle counters before each case (`config/testrunner.py`), since
caches are not transactional and the suite's own auth requests would otherwise
exhaust the limits mid-run.

## Guided tour

A new account is shown a short spotlight tour of the workspace the first time it
reaches a signed-in screen. It highlights the navigation, the notification bell,
and ends with a pointer to Find Jobs.

The state lives on the account (`Profile.tour_completed_at`), not in browser
storage, so signing in from a second device does not replay it. Finishing and
skipping are equivalent — both mean "do not show this again" — and the tour can
be replayed at any time from **Settings → Guided tour**.

It is hand-rolled (`frontend/src/components/tour/`) rather than a tour library:
one screen's worth of behaviour did not justify the dependency. Targets are
plain `data-tour` attributes, so adding a step means adding an attribute and an
entry to `steps.ts` — no component wiring.

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
