# Third-Party Notices

This project incorporates concepts, and in two cases adapted parsing logic, from
the open-source repositories listed below. All are MIT licensed.

**Important distinction:** an MIT licence authorises use of the *code*. It does
**not** authorise automated access to the platforms that code talks to. That is a
separate question, governed by each platform's terms of service, and is handled
by the authorization gate described in
[`docs/provider-authorization-matrix.md`](docs/provider-authorization-matrix.md).
No third-party platform collection is enabled in this repository.

---

## 1. JobSpy

- **Repository:** https://github.com/speedyapply/JobSpy
- **Pinned commit:** `015c31b8417742dbce426453231ebd330303add1`
- **Licence:** MIT — `LICENSE` verified at the pinned commit
- **Copyright:** Copyright (c) 2023 Cullen Watson

### What was reused

- **Conceptual validation** of the LinkedIn guest job endpoint
  (`/jobs-guest/jobs/api/seeMoreJobPostings/search`) and its pagination via the
  `start` parameter.
- Confirmation that LinkedIn's `job_type` and `is_remote` filters are
  unreliable — JobSpy logs a warning and ignores them. Our adapter does not rely
  on them either.
- The general shape of result-card parsing (`.base-search-card` and its child
  classes).

### What was rejected

- **`RequestsRotating` proxy rotation.** Explicitly out of scope: proxy rotation
  to evade restrictions is a circumvention technique. Our client uses a single
  honest user agent and no proxies.
- The multi-board aggregation layer (Indeed, Glassdoor, ZipRecruiter, Bayt,
  Naukri, BDJobs, HelloWork, Google). Only the three target platforms are in
  scope.
- Its DataFrame output model, which does not fit this project's normalized
  `NormalizedJob` representation.

### Local modifications

None. No JobSpy source code was copied into this repository. The LinkedIn parser
here was written independently and then checked against JobSpy's approach for
corroboration.

---

## 2. Jobber

- **Repository:** https://github.com/alwedo/jobber
- **Pinned commit:** `7e41ce73d8cc0d955a6030c7a198635d27d7ebc4`
- **Licence:** MIT — `LICENSE` verified at the pinned commit
- **Copyright:** Copyright (c) 2025 Alvaro Alonso

### What was reused

- **The StepStone structured search API contract**, which was the single most
  valuable finding. Jobber's `scrape/stepstone/stepstone.go` POSTs
  `/public-api/resultlist/unifiedResultlist` with a JSON body and decodes an
  `items` / `pagination` response. This is materially more reliable than scraping
  the result page HTML, so our StepStone parser is built on it:
  - endpoint path, `siteId` 250, and the `fields: ["items", "pagination"]` shape
  - the `item` fields (`id`, `title`, `url`, `companyName`, `location`,
    `textSnippet`, `datePosted`)
  - the search path template `/work/{keywords}/in-{location}`, including the
    requirement to encode spaces as `+` rather than `%20`
  - the `sort=2` (by age) and `ag=age_1` / `ag=age_7` parameters
- **The retry client's structure** (`scrape/retryhttp/retryhttp.go`): the set of
  retryable statuses, exponential backoff, and buffering the request body so a
  request can be replayed. Our `SourceHttpClient` implements the same shape.
- **Corroboration of the LinkedIn selectors** — Jobber's
  `scrape/linkedin/linkedin.go` uses the same card structure we do
  (`li`, `.base-search-card`, `[data-entity-urn]`, `.base-search-card__title`,
  `.base-search-card__subtitle a`, `.job-search-card__location`, `time`).

### What was rejected

- **Retrying HTTP 429.** Jobber's client treats `StatusTooManyRequests` as
  retryable. We do the opposite: 401, 403 and 429 are never retried, because
  retrying a rate limit or an access denial is an attempt to get around it.
- **`WithRandomUserAgent()`.** Random user-agent rotation per request is browser
  fingerprint spoofing. Our client sends one stable, identifying user agent.
- **The Go implementation itself.** Rather than introduce a second runtime, the
  *techniques* above were reimplemented in Python inside the existing Django
  backend. No Go service is deployed.
- Its PostgreSQL/pgx data layer, RSS generation, and CLI.

### Local modifications

Reimplemented in Python (`jobs/sources/http.py`,
`jobs/sources/stepstone/parser.py`, `jobs/sources/stepstone/adapter.py`) with the
two behavioural changes noted above. Deviations are marked with comments in those
files.

---

## 3. stepstone-scraper

- **Repository:** https://github.com/robi-369/stepstone-scraper
- **Pinned commit:** `03b1655691fb83232ead6bdd680f9071920aa514`
- **Licence:** MIT — `LICENSE` verified at the pinned commit
- **Copyright:** Copyright (c) 2025 stepstone-scraper

### Evaluation outcome: not adopted

Evaluated as an alternative StepStone implementation and **rejected** in favour of
Jobber's approach:

| Criterion | Jobber | stepstone-scraper |
| --- | --- | --- |
| Data source | Structured JSON API | HTML screen-scraping |
| Resilience to redesigns | High (API contract) | Low (CSS selectors) |
| Structured fields | Typed structs | Parsed from DOM text |
| Tests | Fixture-based Go tests — **all pass** | **None present** |
| Compiles | Yes | **No — `SyntaxError`** |

Two findings settled it:

1. **The source does not compile.** `src/scraper/stepstone_parser.py` raises
   `SyntaxError: '[' was never closed` at line 13, where `SEARCH_PATHS = [` is
   opened and never closed:

   ```bash
   python -m py_compile src/scraper/stepstone_parser.py
   # SyntaxError: '[' was never closed
   ```

   The repository is therefore not runnable as published.

2. **No tests exist.** `find . -iname '*test*'` returns nothing, so the claimed
   reliability cannot be verified. Its two missing dependencies
   (`python-dateutil`, `openpyxl`) are also not used elsewhere in this project.

The deciding factor remains the data source: a documented JSON contract is far
more maintainable than selectors against a page whose markup changes without
notice. Its fallback-selector strategy is a reasonable mitigation, but it treats a
symptom rather than the cause.

### What was reused

**Nothing.** No code was copied. Its dependency set
(`requests`, `beautifulsoup4`, `lxml`, `python-dateutil`, `openpyxl`) was reviewed
for licence compatibility and contains no issues; `beautifulsoup4` is already a
dependency here for other reasons.

---

## Upstream test execution results

The task requires running each repository's own tests. Results:

### JobSpy — no tests to run

```bash
find /tmp/jobspy-probe -iname '*test*' -not -path '*/.git/*'
# (no output — the repository contains no test files)
grep -i test /tmp/jobspy-probe/pyproject.toml
# (no output — no pytest configuration)
```

There is no test suite to execute. Its `LinkedIn` class also cannot be imported
under this project's runtime without adding `pandas`:

```bash
python -c "from jobspy.linkedin import LinkedIn"
# ModuleNotFoundError: No module named 'pandas'
```

This is a further reason not to adopt the library wholesale: it would pull a heavy
analytics dependency into a Django backend for one HTTP client.

### Jobber — all tests pass

Go 1.23.4 was installed locally to execute the suite:

```bash
export PATH=/tmp/goroot/go/bin:$PATH GOROOT=/tmp/goroot/go GOPATH=/tmp/gopath GOFLAGS=-mod=mod
cd jobber
go test ./scrape/linkedin/ ./scrape/stepstone/ ./scrape/retryhttp/
```

```
ok   github.com/alwedo/jobber/scrape/linkedin    0.027s
ok   github.com/alwedo/jobber/scrape/stepstone  0.122s
ok   github.com/alwedo/jobber/scrape/retryhttp  0.004s
```

Test functions executed (all `PASS`):

| Test | What it covers |
| --- | --- |
| `TestFetchOffersPage` | StepStone request shape, `UpdatedAt` handling, exponential backoff |
| `TestParseLinkedInBody` | LinkedIn card parsing from saved markup |
| `TestScrape` | End-to-end scrape against a mock transport; "too many retries don't discard data" |
| `TestNormalizeTime` | Relative time normalisation ("2 hours ago") |

Notably, these are **fixture-based tests using a mock `RoundTripper`** — no live
platform request is made. That is the same testing approach adopted here.

### stepstone-scraper — cannot run

```bash
python -m py_compile src/scraper/stepstone_parser.py
# SyntaxError: '[' was never closed (line 13)
```

The repository does not compile and contains no tests.

---

## Dependency licences

Runtime dependencies and their licences:

| Package | Licence |
| --- | --- |
| Django | BSD-3-Clause |
| djangorestframework | BSD-3-Clause |
| djangorestframework-simplejwt | MIT |
| django-cors-headers | MIT |
| django-filter | BSD-3-Clause |
| drf-spectacular | BSD-3-Clause |
| python-dotenv | BSD-3-Clause |
| requests | Apache-2.0 |
| beautifulsoup4 | MIT |
| pypdf | BSD-3-Clause |
| python-docx | MIT |
| reportlab | BSD-3-Clause |
| lxml | BSD-3-Clause |

All are permissive and compatible with this project's use.

---

## Explicitly not used

**`AmirDonyadide/JobFinder`** — not used in any form. Its published licence is
non-commercial, which is incompatible with this application, and no separate
permission has been obtained.

---

## Reproducing the evaluation

```bash
git clone --depth 1 https://github.com/speedyapply/JobSpy.git
git clone --depth 1 https://github.com/alwedo/jobber.git
git clone --depth 1 https://github.com/robi-369/stepstone-scraper.git
git -C JobSpy rev-parse HEAD                 # 015c31b8417742dbce426453231ebd330303add1
git -C jobber rev-parse HEAD                 # 7e41ce73d8cc0d955a6030c7a198635d27d7ebc4
git -C stepstone-scraper rev-parse HEAD      # 03b1655691fb83232ead6bdd680f9071920aa514
```
