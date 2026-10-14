# Provider Authorization Matrix

**This document is the authoritative record of which job platforms may be
collected from.**

An MIT licence on a scraper library authorises the *code*. It does not authorise
access to the platform. Those are separate questions, and the second one is
answered by each platform's terms of service and by any written agreement with
the operator.

## Current status

| Provider | Code | Fixture tests | Live collection | Authorization | Production collection |
| --- | --- | --- | --- | --- | --- |
| **LinkedIn** | Implemented | ✅ Passing | ⚠️ One verification run | ❌ **None on record** | **Disabled** |
| **StepStone** | Implemented | ✅ Passing | ⚠️ One verification run | ❌ **None on record** | **Disabled** |
| **Stellenwerk** | Implemented | ✅ Passing | ⚠️ One verification run | ❌ **None on record** | **Disabled** |
| **Manual import** | Implemented | ✅ Passing | N/A | Not required | **Enabled** |

With the **default configuration no live request is made to any platform**. The
gate holds the three providers in `DISABLED_BY_CONFIG`, and `get_adapter()`
returns `None`.

### The verification run

A single, manually triggered verification run was performed at the operator's
explicit request, using a temporary local `backend/.env` whose authorization
references were literally `TEST-RUN-ONLY-NOT-AN-AUTHORIZATION`. **That string is
not an authorization.** It satisfies the gate's technical check so the code paths
could be exercised once, and it is self-describing precisely so it can never be
mistaken for permission.

What that run established:

- The adapters parse live markup correctly (this is the only way to know).
- The pipeline, deduplication and matching work on real listings.
- LinkedIn's guest endpoint returned **HTTP 429** almost immediately, confirming
  its rate limiting is active and that the gate's "blocked, never retried"
  behaviour is the correct response.

Before any ongoing, automated, or multi-user use, written authorization must be
obtained from each platform and recorded as described in
[Recording an authorization](#recording-an-authorization). Until then the
providers must remain disabled.

## The gate

Two independent conditions must both hold before any live request is issued
(`backend/jobs/sources/registry.py`):

1. `PROVIDER_<NAME>_ENABLED=true`
2. `PROVIDER_<NAME>_AUTHORIZATION_REFERENCE=<non-empty>`

Condition 2 exists so that flipping a boolean cannot silently switch on
collection nobody has documented a right to perform. Setting `ENABLED=true`
without a reference leaves the provider in
`DISABLED_AUTHORIZATION_PENDING`, and `get_adapter()` returns `None` so the
adapter is never instantiated — let alone called.

Statuses:

| Status | Meaning |
| --- | --- |
| `READY` | Enabled, authorised, and usable. |
| `DISABLED_AUTHORIZATION_PENDING` | Enabled but no written authorization recorded. |
| `DISABLED_BY_CONFIG` | Switched off. |
| `TEMPORARILY_UNAVAILABLE` | Authorised but currently blocked or rate limited. |
| `INTEGRATION_ERROR` | Adapter misconfigured or raised unexpectedly. |

## Platform positions

### LinkedIn

The User Agreement prohibits scraping and unauthorised automated access. The
guest jobs endpoint being reachable without a login is **not** permission — a
public endpoint is still automated access.

*Required to enable:* written authorisation covering automated access to the job
search endpoints, storage and display of listings, and multi-user SaaS use.

### StepStone

The terms prohibit scraping for other purposes, republication, use outside the
intended service, and commercial reuse of applicant services. The structured
result-list endpoint we parse is publicly reachable; that does not change the
position.

*Required to enable:* a partnership or licence agreement covering API access,
storage, normalisation, and display to end users.

### Stellenwerk

The legal notice restricts commercial reuse and modification of the website's
documents and graphics.

*Required to enable:* written permission for commercial reuse, or an official feed
or partnership agreement.

## Personal / non-commercial use

"Not commercial" changes the position for some platforms and **not at all** for
others. The distinction is whether the terms contain a personal-use carve-out.

| Platform | Personal use permitted? | Primary source |
| --- | --- | --- |
| **LinkedIn** | ❌ **No carve-out** | User Agreement §8.2 |
| **Stellenwerk** | ✅ **Explicitly permitted** | Impressum, copyright notice |
| **Adzuna** | ✅ **Explicitly permitted** | API ToS, "Permissible Use" |
| **StepStone** | ❓ **Not verified** | Terms not retrievable (403/404) |

### LinkedIn — no personal-use exemption

The User Agreement §8.2 "Don'ts" opens with:

> *"This list of 'Dos and Don'ts' … limits what you can and cannot do on our
> Services, **unless otherwise explicitly permitted by LinkedIn in a separate
> writing** (e.g., through a research agreement)."*

And prohibits:

> *(2) "Develop, support or use software, devices, scripts, robots or any other
> means or processes (such as crawlers, browser plugins and add-ons or any other
> technology) to scrape or copy the Services…"*
>
> *(13) "Use bots or other unauthorized automated methods to access the Services…"*

There is **no non-commercial or personal-use exception**. The only escape is a
separate written agreement. §3.4 adds that LinkedIn "reserves the right to
restrict, suspend, or terminate your account" for breaches — and the account at
risk is the user's own LinkedIn profile.

**Conclusion: personal use does not make LinkedIn collection permissible.**

### Stellenwerk — personal use explicitly contemplated

Their Impressum states:

> *"Die auf dem Server verfügbaren Dokumente und dazugehörige Grafiken dürfen
> **für den eigenen Gebrauch** verwendet (gelesen, gespeichert und gedruckt)
> werden. Eine Modifikation oder **kommerzielle Weiterverwendung** ist
> unzulässig."*

Translation: documents and graphics may be used — read, saved and printed — **for
one's own use**; modification or **commercial** reuse is prohibited.

Non-commercial use is therefore expressly contemplated; only commercial reuse is
barred. Note this is a copyright notice about *documents*, not an API grant, so
it permits personal saving rather than granting a bulk-collection licence.

### Adzuna — "Personal research" is a named permissible use

The API Terms of Service list permissible uses as:

> *"1. Publishing Adzuna ad listings  2. Publishing Jobsworth salary estimates
> **3. Personal research**"*

The 14-day trial and licence requirement applies to *"any commercial, government
or academic organisation"*. Personal research sits outside that, and the free
tier (25 hits/min, 2,500/month) applies.

### StepStone — unverified

Their terms pages returned HTTP 403/404 to automated retrieval. No claim is made
either way. Treat as **unknown**, which under this project's policy means
disabled.

### The multi-user caveat

"Own use" and "personal research" describe **one person**. Sharing a deployment
with friends moves beyond the literal wording, even without income. The
realistic risk at that scale is very low, but it is no longer squarely within the
permitted wording. A handful of friends is a judgement call; a public signup page
is not.

---

## Recording an authorization

When an agreement exists, record a **reference** to it — not the document itself,
which must stay out of Git:

```bash
# backend/.env  (never committed)
PROVIDER_STEPSTONE_ENABLED=true
PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE=CONTRACT-2026-0142
```

A reference is a document id, ticket number, or the path to a contract held
outside the repository. The system records *that* an authorization exists; it does
not attempt to verify its contents, which is a legal judgement for the operator.

### Disabling the verification configuration

If a local `backend/.env` was created for a verification run, disable it before
any ongoing use:

```bash
# backend/.env
PROVIDER_LINKEDIN_ENABLED=false
PROVIDER_STEPSTONE_ENABLED=false
PROVIDER_STELLENWERK_ENABLED=false
```

The Django development server must be **restarted** afterwards. `settings.py`
reads `.env` once at import time, so a server started with `--noreload` (or any
long-running process) keeps the values it booted with. The UI's Job Sources panel
is the quickest check — all three should read *Disabled by configuration*.

Deleting `backend/.env` also works, since the shipped defaults in `settings.py`
are `False` for every platform provider. The test suite is unaffected either way:
provider settings are pinned in `config/testkit.py` so a developer's local `.env`
cannot change what the tests assert.

## What is deliberately not implemented

The following are out of scope and will not be added:

- CAPTCHA bypass
- Login or account automation, fake accounts
- Stolen or shared session cookies or credentials
- Residential proxy rotation or IP rotation
- Browser fingerprint or user-agent spoofing
- Cloudflare or access-control circumvention
- Retrying 401 / 403 / 429 in order to get past a block
- Collecting authenticated profile information

Where a platform returns 401, 403 or 429, the adapter stops and reports the source
as unavailable. It does not escalate.

## The permitted path today

**Manual import** (`POST /api/jobs/import/`) lets a user add a listing they found
themselves. It performs no third-party automated access, so it requires no
platform authorization. The supplied URL is stored for the user to visit and is
**never fetched by the server** — fetching it would be exactly the automated
access the gate exists to prevent.

Imported listings flow through the same normalization, employment
classification, deduplication, matching and cover-letter pipeline as any other
job, and are labelled `isUserProvided` so they are never confused with an
authorised source result.

## See also

- [`job-source-setup.md`](job-source-setup.md) — configuring providers
- [`job-discovery-architecture.md`](job-discovery-architecture.md) — the pipeline
- [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) — upstream licences
