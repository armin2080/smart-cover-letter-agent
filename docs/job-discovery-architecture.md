# Job Discovery Architecture

How a search request becomes a matched, deduplicated job in the React interface.

## Layers

```
React UI
   │  POST /api/searches/            (start a search)
   │  GET  /api/searches/{id}/       (poll progress)
   ▼
searches/runner.py                   stages, progress, persistence
   │
   ▼
jobs/sources/pipeline.py             dispatch → normalize → dedupe → match
   │
   ├─ jobs/sources/registry.py       AUTHORIZATION GATE
   │
   ├─ linkedin/adapter.py   ─┐
   ├─ stepstone/adapter.py   ├─ jobs/sources/*/parser.py  → RawJob
   ├─ stellenwerk/adapter.py ┘
   └─ manual/adapter.py              user-supplied listings
   │
   ▼
jobs/sources/normalization.py        RawJob → NormalizedJob
jobs/sources/classification.py       German/English employment type
jobs/sources/dedup.py                cross-source deduplication
jobs/matching.py                     CV alignment + preference fit
   │
   ▼
jobs/models.py                       Job rows, per user
```

**Separation of concerns.** Adapters and parsers know only about their platform.
Classification, deduplication and matching are shared, so every source gets
identical treatment and behaviour cannot drift between them.

## The adapter interface

```python
class JobSourceAdapter(ABC):
    name: str
    display_name: str

    def search(self, request: SearchRequest) -> list[RawJob]: ...
    def normalize(self, raw: RawJob) -> NormalizedJob: ...   # shared default
    def health_check(self) -> SourceHealth: ...
```

Adapters fetch and parse. Everything after `RawJob` is shared.

## The authorization gate

`registry.get_adapter(name)` returns `None` unless the provider is `READY`.
`READY` requires **both** an explicit enable **and** a recorded authorization
reference. The pipeline asks for adapters through the registry, so there is no
path that reaches a platform without passing the gate.

See [`provider-authorization-matrix.md`](provider-authorization-matrix.md).

## Normalized job

Every source produces the same structure:

```jsonc
{
  "external_id": "4420960628",
  "source": "LinkedIn",
  "source_url": "https://…",

  "title": "Werkstudent Softwareentwicklung",
  "company": "Acme GmbH",

  "location": "Dortmund, Nordrhein-Westfalen",
  "city": "Dortmund",
  "region": "Nordrhein-Westfalen",
  "country": "Germany",

  "description": "…",

  "employment_type": "working-student",
  "employment_type_confidence": 0.97,
  "employment_type_evidence": ["Werkstudent"],

  "work_model": "hybrid",

  "salary_min": null,
  "salary_max": null,

  "posted_at": "2026-10-09T00:00:00Z",
  "collected_at": "2026-10-14T11:20:00Z",

  "keywords": ["Python", "Django"],
  "required_skills": ["Python", "Django", "Docker"],

  "raw_source_data": { "…": "untouched source payload" }
}
```

`raw_source_data` is retained for traceability. Personal information about
recruiters is never extracted.

## Employment classification

The classifier is rule-based and auditable — deterministic, testable, and it
explains itself.

Categories: `working-student`, `internship`, `student-assistant`, `part-time`,
`full-time`, `minijob`, `temporary`, `apprenticeship`, `other`, `unknown`.

Design decisions:

- **Word-bounded matching.** `\bintern\b` prevents "internal" and
  "international" from registering as internships.
- **Specificity weighting.** `Werkstudent` (0.97) decides on its own; the bare
  word `Student` (0.15) can only corroborate. `"Student Success Manager"` is
  therefore `unknown`, not a working-student role.
- **Field weighting.** A title match (×1.0) outranks the same word in a long
  description (×0.62).
- **Ambiguity is respected.** "Werkstudent Praktikum" returns `unknown` with
  `ambiguous: true` rather than guessing between two equally supported
  categories.
- **Student employment group.** `working-student` and `student-assistant` are
  both student work, so a `working-student` filter matches either. A university
  HiWi post is the same kind of opportunity as a Werkstudent post, and the UI
  offers no separate switch for it.
- **Board badges are honest about their strength.** Job boards label postings
  with structured categories (`Studierendenjob`, `Studentenjob`). These are
  recognised as student employment at 0.6 — deliberately below `Werkstudent`
  (0.97), because in Germany *Werkstudent* is a specific legal classification
  tied to enrolment and ~20h/week during term. A category badge does not
  establish that, and the confidence value says so.

### How `UNKNOWN` interacts with a filter

`UNKNOWN` covers two very different situations, and the filter treats them
differently. The classifier records the categories that actually had evidence
(`candidates`), which is what makes the distinction possible:

| Situation | Candidates | Filter behaviour |
| --- | --- | --- |
| No type stated anywhere | *(empty)* | **Excluded** |
| Ambiguous, all candidates requested | e.g. `working-student`, `internship` | **Kept** |
| Ambiguous, a candidate not requested | e.g. `working-student`, `full-time` | **Excluded** |

A posting with no employment-type evidence is not evidence of student work, so a
student filter must not return it. Previously these were always retained, which
is why full-time roles (`Projektingenieur`, `Trainee Ingenieur`) appeared in
working-student results.

An ambiguous posting such as "Intern / Working Student" is genuinely one of the
two requested types, so it is kept — whichever reading is correct satisfies the
request. Ambiguity that includes a type outside the filter is excluded, because
the listing might not be what was asked for.

Excluded listings are **counted, not dropped silently**: the run reports how many
were set aside and why, in the extract stage.

## Skills and matching vocabulary

Skills are extracted from the title and description through a single vocabulary
that maps every spelling and language to **one canonical label**
(`Softwareentwicklung` and `software development` both become
`Software development`).

The vocabulary covers German as well as English. This is not decoration: the
product's market is Germany, so a listing titled "Werkstudent
Softwareentwicklung" used to yield no skills at all and the `strong` tier was
unreachable for exactly the roles the product exists to find.

Acronyms (`IT`, `AI`, `KI`, `UX`, `HR`) are matched **case-sensitively** with the
same word boundaries, because a case-insensitive `ai` matches "Mai" and `it`
matches "Qualität". `LogProIT` therefore does not register as `IT`.

Matching compares canonical label to canonical label, which is
language-independent: a German CV matches an identically-meaning English label.
The gap list excludes anything already matched, so the UI never reports a skill
as missing while the line above it shows the same skill as found.

## Deduplication

In decreasing order of confidence:

1. **Canonical URL** — tracking parameters, fragments and `www.` stripped
2. **Source + external id** — authoritative within one source
3. **Normalised title + company + location** — catches re-posts across boards
4. **Conservative fuzzy title** — same company *and* location, ≥0.93 similarity

Two jobs are never merged on title alone. Under-merging is preferred to
over-merging: a duplicate card is a cosmetic annoyance, but merging two genuinely
different openings hides an opportunity.

When records merge, the richer one (more description, more skills) becomes
primary, and every source URL is kept in `provenance`.

## Matching

`jobs/matching.py`, unchanged in principle from the existing implementation. Two
independent dimensions, each rendered as plain language:

- **CV alignment** — skills, experience, education, evidenced requirements
- **Preference fit** — target role, location, employment type, source, keywords

Verdicts are qualitative: `strong`, `good`, `potential`, `low`. **No percentage is
ever exposed.** The skill signal is computed from the posting's skill list rather
than requirement prose, so a role outside the user's field cannot be rated
`strong` merely because its location happens to fit.

Where a posting carries canonical skill labels, the skill signal compares label to
label. Prose fallback is used only when no labelled skills were extracted.

## Search orchestration

```
POST /api/searches/  →  SearchRun (queued) → returns immediately
                              │
                              ▼
                    daemon thread (max 4 concurrent)
                              │
  1. Discover  ── collect from every permitted source
  2. Enrich    ── fetch detail pages (budgeted, best-effort)
  3. Extract   ── normalize + classify
  4. Dedupe    ── collapse cross-source duplicates
  5. Compare   ── match against CV + preferences
  6. Prepare   ── persist new Job rows
                              │
                              ▼
GET /api/searches/{id}/  ←  client polls until completed/failed
```

Each stage persists its own state, so progress survives a page reload and is
genuine rather than decorative.

**Failure isolation.** A source that is disabled, unauthorised, blocked or
raising is recorded as a `SourceOutcome` with a reason. One provider failing never
prevents the others from delivering results.

**Enrichment is budgeted.** Descriptions materially improve classification and
matching, but each detail page costs a request. `SOURCE_ENRICH_LIMIT` (default 6)
caps the fetches per source. A failure or a block during enrichment stops that
source's enrichment and keeps the listings already collected — it never escalates
into retrying a rate limit.

Some sources return descriptions inline (StepStone) and define no `enrich()`;
that is tolerated. Note that StepStone's payload truncates descriptions to ~300
characters, so its listings frequently yield no skills at all.

Set `SEARCH_RUN_ASYNC=false` to run inline (tests, single-process deployments).
For production, replace `start_search` with a Celery/RQ task — the stage contract
and persistence logic are unchanged.

## Job lifecycle

A job record holds two independent concerns:

- **The listing** — title, company, description, provenance
- **The user's interaction** — `reviewed_at`, `saved_at`, `dismissed_at`,
  `cover_letter_created_at`

These are genuinely independent. Saving does not clear "reviewed"; dismissing
preserves the fact that it was saved. `status` is a denormalised convenience for
tab filtering, derived from the timestamps by `Job.sync_status()`. One user's
state never affects another's.

## Error handling

| Condition | Behaviour |
| --- | --- |
| Timeout / 5xx / 408 / 425 | Retried with exponential backoff (max 3) |
| **401 / 403 / 429** | **Never retried.** Raised as `SourceBlocked`; source reported unavailable |
| `Retry-After` present | Honoured, and surfaced to the caller |
| One source raises | Isolated; other sources still return |
| One record fails to parse | Skipped; the run continues |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/searches/` | Start a search |
| `GET` | `/api/searches/{id}/` | Poll progress |
| `POST` | `/api/searches/{id}/cancel/` | Cancel |
| `GET` | `/api/jobs/` | List with filters |
| `GET` | `/api/jobs/{id}/` | Detail incl. analysis and provenance |
| `POST` | `/api/jobs/{id}/review/` | Mark reviewed |
| `POST` | `/api/jobs/{id}/save/` | Toggle saved |
| `POST` | `/api/jobs/{id}/dismiss/` | Dismiss |
| `POST` | `/api/jobs/{id}/restore/` | Clear all interaction state |
| `GET` | `/api/jobs/providers/` | **Per-source authorization status** |
| `POST` | `/api/jobs/import/` | **Manual import (permitted path)** |
| `GET/PUT` | `/api/searches/settings/` | Automatic search configuration |
