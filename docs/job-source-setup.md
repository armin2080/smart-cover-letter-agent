# Job Source Setup

## Default state

Out of the box, **no live platform collection is enabled**. This is deliberate,
not a misconfiguration. Searches run against clearly-labelled sample data so the
workflow remains usable, and the run reports why no live source was used.

The permitted path that works immediately is **manual import** — users add
listings they found themselves.

## Environment variables

```bash
cd backend
cp .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROVIDER_LINKEDIN_ENABLED` | `false` | Configuration opt-in |
| `PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE` | *(empty)* | Recorded authorization |
| `PROVIDER_STEPSTONE_ENABLED` | `false` | Configuration opt-in |
| `PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE` | *(empty)* | Recorded authorization |
| `PROVIDER_STELLENWERK_ENABLED` | `false` | Configuration opt-in |
| `PROVIDER_STELLENWERK_AUTHORIZATION_REFERENCE` | *(empty)* | Recorded authorization |
| `PROVIDER_MANUAL_ENABLED` | `true` | Manual import (no authorization needed) |
| `SAMPLE_DATA_ENABLED` | `true` | Synthetic fallback when no live source is available |
| `SOURCE_HTTP_TIMEOUT_SECONDS` | `20` | Per-request timeout |
| `SOURCE_HTTP_MAX_ATTEMPTS` | `3` | Retry attempts for *transient* errors only |
| `SOURCE_MAX_RESULTS` | `50` | Cap per search |

## Enabling a provider

**Only after written authorization exists.** See
[`provider-authorization-matrix.md`](provider-authorization-matrix.md).

```bash
# backend/.env — never committed
PROVIDER_STEPSTONE_ENABLED=true
PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE=CONTRACT-2026-0142
```

Setting `ENABLED=true` **without** a reference leaves the provider
`DISABLED_AUTHORIZATION_PENDING`. The adapter is not instantiated and no request
is made. This is intentional: a boolean flip must not be able to silently enable
collection nobody documented a right to perform.

## Verifying the current state

```bash
# Per-provider status, including why anything is disabled
curl -s http://127.0.0.1:8000/api/jobs/providers/ -H "Authorization: Bearer <token>" | jq
```

```jsonc
[
  {
    "source": "linkedin",
    "displayName": "LinkedIn",
    "status": "disabled-authorization-pending",
    "statusLabel": "Disabled — authorization pending",
    "operational": false,
    "detail": "Live collection disabled: no written platform authorization is on record.",
    "termsNote": "LinkedIn's User Agreement prohibits scraping…"
  }
]
```

The same data drives the source indicators in the UI, so the interface never
claims a source is connected when it is not.

## Manual import

Works with no authorization because it performs no third-party automated access.

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/import/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/jobs/1",
    "title": "Werkstudent Softwareentwicklung (m/w/d)",
    "company": "Acme GmbH",
    "location": "Dortmund, Nordrhein-Westfalen",
    "employmentType": "working-student",
    "description": "Python und Django Entwicklung.",
    "notes": "Referred by a friend."
  }'
```

**The supplied URL is never fetched by the server.** Fetching it would be exactly
the automated access the gate exists to prevent. The URL is stored so the user can
visit the original posting themselves.

Imported listings are marked `isUserProvided` and flow through the same
normalization, classification, matching and cover-letter pipeline as any other
job.

## Adding a new source

1. Create `jobs/sources/<name>/` with `adapter.py` and `parser.py`.
2. Implement `search()` returning `list[RawJob]`; reuse the shared `normalize()`.
3. Register the provider in `jobs/sources/registry.py` `PROVIDERS` with its terms
   note. It defaults to disabled — that is the point.
4. Add fixture-based tests in `jobs/sources/<name>/tests.py`. **Never** write a
   test that performs a live request.

## Scheduled searches

```bash
# Hourly
0 * * * * cd /path/to/backend && ../.venv/bin/python manage.py run_scheduled_searches
```

Automatic searches use the user's **saved preferences**, not temporary overrides.
Temporary overrides apply to a single manual search and never modify the profile.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Every search returns sample data | Expected — no provider is authorized |
| Provider shows `disabled-authorization-pending` | `ENABLED=true` but no reference recorded |
| Provider shows `temporarily-unavailable` | 401/403/429 from the platform. Not retried by design |
| `integration-error` | Adapter misconfigured; check logs |
| No results from an enabled provider | Markup or API contract changed. Check the fixture tests |

## Legal

Authorization is a legal question for the operator, not something the software can
determine. The gate records *that* an authorization exists and refuses to collect
without one. Recording a reference for an agreement that does not cover the
required activities does not make the collection permitted.
