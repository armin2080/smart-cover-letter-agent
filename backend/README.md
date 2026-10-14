# Smart Cover Letter Agent — Backend

Django 6 + Django REST Framework API for job discovery, explainable CV matching
and AI-assisted cover letter generation.

Implements the contract in [`../frontend/API_CONTRACT.md`](../frontend/API_CONTRACT.md).

## Quick start

```bash
cd backend

# 1. Dependencies (from the repository root virtualenv)
python -m venv ../.venv                      # if it does not exist yet
../.venv/bin/pip install -r requirements.txt

# 2. Configuration
cp .env.example .env                         # optional; defaults work for local dev

# 3. Database
../.venv/bin/python manage.py migrate

# 4. Demo data (optional but recommended)
../.venv/bin/python manage.py seed_demo

# 5. Run
../.venv/bin/python manage.py runserver 8000
```

* API root: <http://127.0.0.1:8000/api/>
* Interactive docs: <http://127.0.0.1:8000/api/docs>
* OpenAPI schema: <http://127.0.0.1:8000/api/schema/>
* Admin: <http://127.0.0.1:8000/admin/> (`createsuperuser` first)

`seed_demo` creates `armin.keller@example.com` / `demo-password-123` and produces
jobs by running the **real** search pipeline (provider → matching engine →
persistence), so seeded data exercises production code paths.

## Tests

```bash
../.venv/bin/python manage.py test            # 102 tests
../.venv/bin/python manage.py test jobs       # one app
```

## Architecture

```
backend/
  config/            settings, URLs, pagination, error envelope, shared serializers
  accounts/          User, Profile, ProfileSection, CvDocument, Preferences,
                     NotificationSettings + auth/profile/CV/settings endpoints
    cv_parser.py     PDF (pypdf) and DOCX (python-docx) text extraction + section mapping
  jobs/              Job, ActivityEntry, the matching engine, stats and activity
    matching.py      rule-based, explainable CV + preference matching
    services.py      refresh_user_matches() — recompute stored analysis
    sources/         job source adapters (see below)
  searches/          SearchRun, AutoSearchSettings, sample data, background runner
    sample_data.py   deterministic synthetic listings (no network)
    runner.py        staged execution with persisted progress
  cover_letters/     CoverLetter, Groq service, grounded fallback, ReportLab PDF

  jobs/sources/
    base.py            adapter interface, NormalizedJob, ProviderStatus
    registry.py        COMPLIANCE GATE — provider lookup + authorization check
    classification.py  German/English employment-type classifier
    normalization.py   RawJob -> NormalizedJob, location/date/skill parsing
    dedup.py           cross-source deduplication
    http.py            safe HTTP client (timeouts, backoff, Retry-After)
    pipeline.py        dispatch -> normalize -> dedupe -> match
    linkedin/          adapter.py, parser.py, tests.py
    stepstone/         adapter.py, parser.py, tests.py
    stellenwerk/       adapter.py, parser.py, tests.py
    manual/            adapter.py — user-supplied listings (always available)
```

### Endpoints

| Area | Routes |
| --- | --- |
| Auth | `POST /api/auth/register/`, `login/`, `logout/`, `refresh/`, `GET/PATCH /api/auth/me/` |
| Jobs | `GET /api/jobs/`, `GET /api/jobs/counts/`, `stats/`, `recent/`, `GET/PATCH /api/jobs/{id}/` |
| Activity | `GET /api/activity/` |
| Profile | `GET/PATCH /api/profile/`, `PATCH /api/profile/sections/{id}/`, `POST/DELETE /api/profile/cv/` |
| Preferences | `GET/PUT/PATCH /api/profile/preferences/` |
| Searches | `GET/POST /api/searches/`, `GET /api/searches/{id}/`, `POST /api/searches/{id}/cancel/` |
| Auto search | `GET/PUT /api/searches/settings/` |
| Cover letters | `GET/POST /api/cover-letters/`, `preview/`, `GET/PATCH /api/cover-letters/{id}/`, `POST .../regenerate/`, `GET .../pdf/` |
| Settings | `GET/PUT /api/settings/notifications/`, `DELETE /api/account/` |

### Authentication

Email-based custom user (`accounts.User`, `USERNAME_FIELD = "email"`) with
SimpleJWT. Responses use the frontend's `{user, tokens}` envelope. Refresh tokens
rotate and the previous token is blacklisted; `POST /api/auth/logout/` blacklists
the presented refresh token.

Errors are normalised to `{detail, errors}` — see `config/exceptions.py`.

## The matching engine

`jobs/matching.py` is rule-based and fully inspectable. Every verdict is a list of
`{positive, title, detail}` lines the UI renders as plain language; **no opaque
percentage is ever produced** — only `strong` / `good` / `potential`.

The verdict combines two independent signals:

* **`skill_signal`** — the share of the posting's *skill list* evidenced in the
  CV. Requirement prose is excluded, because words like "working" or "knowledge"
  are not skills and would dilute the ratio.
* **`pref_ratio`** — how well location, employment type, source and keywords
  match the user's preferences.

```
strong    : skill_signal >= 0.5  and pref_ratio >= 0.75
good      : skill_signal >= 0.3  or  (target role matched and pref_ratio >= 0.5)
potential : otherwise
```

A role outside the user's domain therefore can never be `strong`, no matter how
well its location and employment type happen to fit.

Analysis is **stored on the job** at discovery time. If the user later edits their
CV or preferences, rebuild it:

```bash
../.venv/bin/python manage.py refresh_matches                  # all users
../.venv/bin/python manage.py refresh_matches --email me@x.y   # one user
```

## Job search

`POST /api/searches/` returns immediately with a `SearchRun` whose `stages` are
updated as work proceeds; the client polls `GET /api/searches/{id}/` until
`status` is `completed` or `failed`.

Execution is staged and each stage persists its own progress:

1. **Discover** — the provider fetches listings
2. **Extract** — normalise, infer employment type and skills
3. **Dedupe** — collapse repeats, keyed by a per-user fingerprint
4. **Compare** — run the matching engine per listing
5. **Prepare** — persist new `Job` rows and count relevant matches

### Job sources (`jobs/sources/`)

Each platform is wrapped in an adapter behind a **compliance gate**
(`jobs/sources/registry.py`). Two conditions must both hold before any live
request is made:

1. `PROVIDER_<NAME>_ENABLED=true`
2. `PROVIDER_<NAME>_AUTHORIZATION_REFERENCE=<non-empty>`

| Provider | Data source | Live collection |
| --- | --- | --- |
| LinkedIn | Public guest job API | **Disabled** — no authorization on record |
| StepStone | Structured `/public-api/resultlist/` JSON | **Disabled** — no authorization on record |
| Stellenwerk | Server-rendered city pages | **Disabled** — no authorization on record |
| Manual import | User-supplied | **Enabled** — no third-party access |

An MIT licence on a scraper library authorises the *code*, not access to the
platform. Setting `ENABLED=true` without a recorded authorization leaves the
provider `DISABLED_AUTHORIZATION_PENDING`; `get_adapter()` returns `None` and the
adapter is never instantiated.

Until a provider is authorized, searches use clearly-labelled sample data and the
run states why. See
[`../docs/provider-authorization-matrix.md`](../docs/provider-authorization-matrix.md).

**Never implemented, by design:** CAPTCHA bypass, login automation, cookie or
credential reuse, proxy/IP rotation, user-agent or fingerprint spoofing, and
retrying 401/403/429 to get past a block. A 403 or 429 means *stop*, not *retry
harder*.

Parsing is verified against saved copies of the real markup
(`jobs/sources/*/tests.py`), so a changed selector fails a test rather than
silently returning nothing.

### Employment classification (`jobs/sources/classification.py`)

Rule-based and auditable. Categories: `working-student`, `internship`,
`student-assistant`, `part-time`, `full-time`, `minijob`, `temporary`,
`apprenticeship`, `other`, `unknown`.

- **Word-bounded** — `\bintern\b` keeps "internal" and "international" out
- **Specificity-weighted** — `Werkstudent` (0.97) decides alone; bare `Student`
  (0.15) can only corroborate, so "Student Success Manager" stays `unknown`
- **Field-weighted** — a title match outranks the same word in a description
- **Ambiguity respected** — "Werkstudent Praktikum" returns `unknown`,
  `ambiguous: true`, rather than guessing

### Deduplication (`jobs/sources/dedup.py`)

Canonical URL → source+external id → normalized title+company+location →
conservative fuzzy (same company *and* city, ≥0.93). Never merges on title alone;
under-merging is preferred to over-merging. All source URLs are kept in
`provenance`.

### Concurrency### Concurrency

Searches run on a daemon thread (max 4 concurrent per process). Set
`SEARCH_RUN_ASYNC=false` to execute inline — required in tests, and useful for
single-process deployments. For production, replace `start_search` with a
Celery/RQ task; the stage contract and persistence logic stay identical.

Scheduled searches:

```bash
# Every hour, for example
0 * * * * cd /path/to/backend && ../.venv/bin/python manage.py run_scheduled_searches
```

## Cover letters

`cover_letters/services.py` selects a strategy automatically:

* **Groq** (when `GROQ_API_KEY` is set) — the prompt forbids inventing skills,
  employers, metrics, dates or achievements.
* **Grounded template** (fallback) — composes the letter purely from stored
  profile and job data. It mentions only skills that genuinely appear in both the
  CV and the posting, reproduces their original casing, and explicitly names
  requirements it cannot evidence rather than overstating the candidate.

`generator` records which strategy produced the current content.

PDFs are rendered server-side with ReportLab and streamed from
`GET /api/cover-letters/{id}/pdf/` as an attachment.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | dev value | **Set a real value in production** |
| `DJANGO_DEBUG` | `true` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | localhost | Comma-separated |
| `CORS_ALLOWED_ORIGINS` | `:5173`, `:3000` | Direct-origin clients |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | `60` / `14` | Token lifetimes |
| `GROQ_API_KEY` | *(empty)* | Enables AI generation |
| `GROQ_MODEL` | `llama-3.1-70b-versatile` | Model id |
| `PROVIDER_*_ENABLED` | `false` | Per-platform opt-in |
| `PROVIDER_*_AUTHORIZATION_REFERENCE` | *(empty)* | Recorded authorization |
| `PROVIDER_MANUAL_ENABLED` | `true` | Manual import |
| `SAMPLE_DATA_ENABLED` | `true` | Synthetic fallback |
| `SOURCE_HTTP_TIMEOUT_SECONDS` | `20` | Per-request timeout |
| `SOURCE_HTTP_MAX_ATTEMPTS` | `3` | Transient-failure retries only |
| `SOURCE_MAX_RESULTS` | `50` | Cap per search |
| `SEARCH_RUN_ASYNC` | `true` | Background vs inline execution |
| `CV_MAX_UPLOAD_BYTES` | `10485760` | 10 MB CV limit |

## Notes and limitations

* **SQLite** is configured for local development. For production set a real
  database and object storage for `MEDIA_ROOT` (uploaded CVs).
* The background runner is **in-process**. With multiple web workers, run
  searches in a dedicated worker (Celery/RQ) instead.
* **No live platform collection is enabled by default.** LinkedIn, StepStone and
  Stellenwerk all restrict automated collection, and no written authorization is
  on record for any of them. Searches therefore use clearly-labelled sample data
  and the run states why. The adapters are implemented and fixture-tested behind
  the compliance gate; see
  [`../docs/provider-authorization-matrix.md`](../docs/provider-authorization-matrix.md).
* **Manual import** (`POST /api/jobs/import/`) is the working path today. It
  performs no third-party access, so it needs no authorization. The supplied URL
  is stored for the user to open but is never fetched by the server.
* Platform HTML and APIs change without notice. The fixture tests in
  `jobs/sources/*/tests.py` run against saved copies of the real markup, so a
  broken selector fails a test rather than silently returning nothing.
* Match analysis is a snapshot — run `refresh_matches` after changing profile data
  or matching rules.
* Uploaded CVs are stored on the local filesystem and served from `/media/` in
  DEBUG only.
* Scraping is subject to each site's terms of service. For commercial use,
  consider official partner APIs or a licensed job-data provider instead.
