"""Search pipeline: dispatch → normalize → dedupe → match → persist.

The pipeline is source-agnostic. It asks the registry which adapters may run,
collects whatever they return, and applies the shared normalization,
deduplication and matching stages. A source that is disabled, unauthorized, or
failing is recorded as an outcome rather than silently dropped, so the UI can
explain what happened.

Failure isolation is deliberate: one provider raising never prevents the others
from producing results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings

from jobs.sources.base import (
    NormalizedJob,
    ProviderStatus,
    RawJob,
    SearchRequest,
    SourceUnavailable,
)
from jobs.sources.dedup import DeduplicatedJob, deduplicate
from jobs.sources.http import SourceBlocked
from jobs.sources.registry import get_adapter, get_provider_status

logger = logging.getLogger(__name__)


@dataclass
class SourceOutcome:
    """What happened for one source during a run."""

    source: str
    status: ProviderStatus
    fetched: int = 0
    enriched: int = 0
    error: str = ""

    @property
    def produced_results(self) -> bool:
        return self.fetched > 0


@dataclass
class PipelineResult:
    """Everything a run produced, including per-source diagnostics."""

    jobs: list[DeduplicatedJob] = field(default_factory=list)
    outcomes: list[SourceOutcome] = field(default_factory=list)
    raw_count: int = 0
    duplicates_removed: int = 0
    #: Listings set aside because the source never stated an employment type.
    #: The groups are kept, not just counted, because a listing that matches the
    #: user's roles but omits its employment type is exactly the one worth
    #: telling them about — a count alone leaves them unable to judge.
    untyped_withheld_jobs: list[DeduplicatedJob] = field(default_factory=list)
    #: Listings set aside because they are not in the requested language. Kept
    #: as groups for the same reason, and separated from `untyped_withheld_jobs`
    #: so the run can say which filter removed them.
    language_withheld_jobs: list[DeduplicatedJob] = field(default_factory=list)

    @property
    def untyped_withheld(self) -> int:
        return len(self.untyped_withheld_jobs)

    @property
    def language_withheld(self) -> int:
        return len(self.language_withheld_jobs)

    @property
    def warnings(self) -> list[str]:
        """Human-readable notes for sources that did not deliver."""

        notes: list[str] = []
        if self.untyped_withheld:
            notes.append(
                f"{self.untyped_withheld} listing"
                f"{'s' if self.untyped_withheld != 1 else ''} did not state an "
                "employment type and were set aside, because they could not be "
                "confirmed as the type you asked for."
            )
        for outcome in self.outcomes:
            if outcome.produced_results:
                continue
            if outcome.status is ProviderStatus.DISABLED_AUTHORIZATION_PENDING:
                notes.append(
                    f"{outcome.source}: live collection is disabled — no written platform "
                    "authorization is on record."
                )
            elif outcome.status is ProviderStatus.DISABLED_BY_CONFIG:
                notes.append(f"{outcome.source}: disabled in configuration.")
            elif outcome.status is ProviderStatus.TEMPORARILY_UNAVAILABLE:
                notes.append(f"{outcome.source}: temporarily unavailable. {outcome.error}".strip())
            elif outcome.status is ProviderStatus.INTEGRATION_ERROR:
                notes.append(f"{outcome.source}: integration error. {outcome.error}".strip())
            else:
                notes.append(f"{outcome.source}: no results. {outcome.error}".strip())
        return notes

    @property
    def operational_sources(self) -> list[str]:
        return [o.source for o in self.outcomes if o.produced_results]


def _status_for_exception(exc: Exception) -> ProviderStatus:
    if isinstance(exc, SourceBlocked):
        return ProviderStatus.TEMPORARILY_UNAVAILABLE
    return ProviderStatus.INTEGRATION_ERROR


def collect_raw_jobs(
    request: SearchRequest,
    *,
    providers: list[str] | None = None,
    enrich: bool = True,
) -> tuple[list[RawJob], list[SourceOutcome]]:
    """Fetch from every permitted source, isolating failures."""

    requested = providers if providers is not None else request.sources
    # Fall back to every known provider when the caller expressed no preference.
    if not requested:
        from jobs.sources.registry import PROVIDERS

        requested = [name for name in PROVIDERS if name != "manual"]

    raw_jobs: list[RawJob] = []
    outcomes: list[SourceOutcome] = []

    for name in requested:
        status = get_provider_status(name)

        # `is_operational`, not an equality check against READY. A provider
        # running under PROVIDER_TEST_MODE is usable but reports
        # ENABLED_FOR_TESTING, so a READY-only test skipped every adapter and
        # reported "no results" for each — with no error anywhere, which made
        # it look like the platforms were empty rather than unreachable.
        if not status.is_operational:
            # Never call the adapter when the gate says no.
            outcomes.append(SourceOutcome(source=name, status=status))
            continue

        adapter = get_adapter(name)
        if adapter is None:
            outcomes.append(
                SourceOutcome(
                    source=name,
                    status=ProviderStatus.INTEGRATION_ERROR,
                    error="adapter could not be instantiated",
                )
            )
            continue

        try:
            fetched = adapter.search(request)
        except SourceUnavailable as exc:
            outcomes.append(SourceOutcome(source=name, status=exc.status, error=exc.detail))
            continue
        except SourceBlocked as exc:
            logger.warning("Source %s blocked: %s", name, exc)
            outcomes.append(
                SourceOutcome(
                    source=name,
                    status=ProviderStatus.TEMPORARILY_UNAVAILABLE,
                    error=str(exc),
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - isolate every provider
            logger.exception("Source %s failed", name)
            outcomes.append(
                SourceOutcome(source=name, status=_status_for_exception(exc), error=str(exc))
            )
            continue

        raw_jobs.extend(fetched)

        enriched = 0
        if enrich and hasattr(adapter, "enrich"):
            enriched = _enrich_listings(adapter, fetched)

        outcomes.append(
            SourceOutcome(
                source=name,
                # The status that was actually resolved, not a hardcoded READY.
                # Reporting READY here would present a test-mode source as
                # authorized, which is the one thing the status is meant to
                # make impossible to confuse.
                status=status,
                fetched=len(fetched),
                enriched=enriched,
            )
        )

    return raw_jobs, outcomes


def _enrich_listings(adapter, jobs: list[RawJob]) -> int:
    """Fetch detail pages for the first N listings of a source.

    Descriptions materially improve employment classification and matching, but
    each one costs a request. The budget keeps a single search from issuing an
    unbounded number of calls, and a failure is never fatal — the listing is
    still usable without its description.
    """

    budget = settings.SOURCE_ENRICH_LIMIT
    if budget <= 0:
        return 0

    enriched = 0
    for job in jobs[:budget]:
        try:
            adapter.enrich(job)
            enriched += 1
        except SourceBlocked:
            # A block during enrichment means stop enriching this source; the
            # listings already collected remain valid.
            logger.warning("Enrichment blocked for %s; keeping %s listing(s)", adapter.name, len(jobs))
            break
        except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
            logger.debug("Enrichment failed for %s: %s", getattr(job, "url", ""), exc)

    return enriched


def normalize_all(
    raw_jobs: list[RawJob],
    *,
    providers: list[str] | None = None,
) -> list[NormalizedJob]:
    """Normalize every raw record, skipping ones that fail to parse."""

    normalized: list[NormalizedJob] = []

    for raw in raw_jobs:
        try:
            adapter = get_adapter(raw.source.lower()) if raw.source.lower() != "manual" else None
            job = adapter.normalize(raw) if adapter is not None else _normalize_manual(raw)
        except Exception:  # noqa: BLE001 - one bad record must not fail the run
            logger.exception("Could not normalize a %s record", raw.source)
            continue

        if job.is_valid:
            normalized.append(job)

    return normalized


def _normalize_manual(raw: RawJob) -> NormalizedJob:
    from jobs.sources.normalization import normalize_raw_job

    return normalize_raw_job(raw)


def apply_employment_filter(
    jobs: list[DeduplicatedJob], employment_types: list
) -> list[DeduplicatedJob]:
    """Keep only listings that match the requested employment types.

    Selecting "working student" also matches "student assistant", because a
    university HiWi post is the same kind of opportunity and the UI offers no
    separate switch for it.

    `UNKNOWN` listings are decided by evidence rather than guesswork:

    * **No signal at all** — the posting never stated a type, so there is no
      student wording anywhere in it. Excluded. Keeping these was the cause of
      full-time roles appearing in student-only results.
    * **Ambiguous, every candidate matches** — e.g. "Intern / Working Student",
      which genuinely is one of the two. Kept, because whichever reading is
      correct satisfies the request.
    * **Ambiguous with a candidate outside the filter** — e.g. "Werkstudent or
      full-time". Excluded, because the listing might not be what was asked for.
    """

    if not employment_types:
        return jobs

    kept, _ = split_by_employment_filter(jobs, employment_types)
    return kept


def split_by_employment_filter(
    jobs: list[DeduplicatedJob], employment_types: list
) -> tuple[list[DeduplicatedJob], list[DeduplicatedJob]]:
    """Apply the filter and return `(kept, withheld)`.

    Withheld groups are returned rather than counted so the run can name the
    ones that matched the user's roles instead of dropping them silently.
    """

    from jobs.sources.base import STUDENT_EMPLOYMENT_TYPES, EmploymentType

    # No preference means no filtering. Without this guard `wanted` is empty,
    # so every typed listing failed `job_type in wanted` and was dropped while
    # every untyped one was withheld — a search with no employment filter
    # returned nothing at all, which reads as "the boards had no jobs".
    if not employment_types:
        return jobs, []

    wanted = set(employment_types)
    if EmploymentType.WORKING_STUDENT in wanted:
        wanted |= STUDENT_EMPLOYMENT_TYPES

    kept: list[DeduplicatedJob] = []
    withheld: list[DeduplicatedJob] = []

    for group in jobs:
        job_type = group.primary.employment_type

        if job_type is not EmploymentType.UNKNOWN:
            if job_type in wanted:
                kept.append(group)
            continue

        candidates = set(group.primary.employment_type_candidates)
        # Keep only when there is evidence and every plausible reading satisfies
        # the request. No evidence, or a reading outside the filter, means the
        # listing does not belong in a filtered result.
        if candidates and candidates <= wanted:
            kept.append(group)
        else:
            withheld.append(group)

    return kept, withheld


def split_by_language_filter(
    jobs: list[DeduplicatedJob], language_filter: str
) -> tuple[list[DeduplicatedJob], list[DeduplicatedJob]]:
    """Apply the language preference and return `(kept, withheld)`.

    A specific language excludes postings whose language could not be
    determined. That is the deliberate choice: keeping them would show a
    German-only reader adverts that may well be in English, confidently and
    without any indication. Withholding them means the run can say how many
    were set aside, and switching to "any language" brings them back.
    """

    from jobs.sources.language import LanguageFilter, matches_language_filter

    try:
        wanted = LanguageFilter(language_filter or LanguageFilter.ANY)
    except ValueError:
        wanted = LanguageFilter.ANY

    if wanted is LanguageFilter.ANY:
        return jobs, []

    kept: list[DeduplicatedJob] = []
    withheld: list[DeduplicatedJob] = []

    for group in jobs:
        if matches_language_filter(group.primary.language, wanted):
            kept.append(group)
        else:
            withheld.append(group)

    return kept, withheld


def run_pipeline(
    request: SearchRequest,
    *,
    providers: list[str] | None = None,
    apply_filter: bool = True,
) -> PipelineResult:
    """Execute the full collection pipeline."""

    raw_jobs, outcomes = collect_raw_jobs(request, providers=providers)
    normalized = normalize_all(raw_jobs)
    groups = deduplicate(normalized)

    result = PipelineResult(
        jobs=groups,
        outcomes=outcomes,
        raw_count=len(raw_jobs),
        duplicates_removed=max(0, len(normalized) - len(groups)),
    )

    if apply_filter:
        result.jobs, result.untyped_withheld_jobs = split_by_employment_filter(
            result.jobs, request.employment_types
        )
        result.jobs, result.language_withheld_jobs = split_by_language_filter(
            result.jobs, request.language_filter
        )

    if request.posted_within_days:
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=request.posted_within_days)
        result.jobs = [
            group
            for group in result.jobs
            if group.primary.posted_at is None or group.primary.posted_at >= cutoff
        ]

    return result
