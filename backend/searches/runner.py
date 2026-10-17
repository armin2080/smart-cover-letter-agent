"""Background execution of job searches.

A run proceeds through five observable stages, each persisted as it completes so
the client can poll `GET /api/searches/{id}/` for genuine progress:

1. **Discover** — collect listings from every permitted source
2. **Extract**   — normalize records and classify employment type
3. **Dedupe**    — collapse listings advertised on several boards
4. **Compare**   — match against the CV and preferences
5. **Prepare**   — persist new opportunities

Sources that are disabled, unauthorized or failing are reported as outcomes
rather than silently dropped, so the UI can explain why a source produced
nothing.

Execution is a daemon thread by default. Set `SEARCH_RUN_ASYNC=false` to run
inline (required by tests, useful for single-process deployments). For
production, replace `start_search` with a Celery/RQ task — the stage contract and
persistence logic are unchanged.
"""

from __future__ import annotations

import logging
import re
import threading
import time

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import Q
from django.utils import timezone

from jobs.matching import _titles_overlap, build_insight
from jobs.models import ActivityEntry, Job, job_fingerprint
from jobs.sources.base import NormalizedJob, SearchRequest
from jobs.sources.pipeline import PipelineResult, normalize_all, run_pipeline

from .models import AutoSearchSettings, SearchRun

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_SEARCHES = 4
_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT_SEARCHES)

#: Pacing between stages so the five-step progress UI is observable. The work at
#: each step is real; this only spreads it over time. Set to 0 in tests.
_STAGE_PACING_SECONDS = 0.6


def set_pacing(seconds: float) -> None:
    global _STAGE_PACING_SECONDS
    _STAGE_PACING_SECONDS = max(0.0, seconds)


STAGE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("discover", "Discovering job listings"),
    ("extract", "Extracting job information"),
    ("dedupe", "Removing duplicate listings"),
    ("compare", "Comparing jobs against your profile"),
    ("prepare", "Preparing matching opportunities"),
)


def build_stages() -> list[dict]:
    return [
        {"key": key, "label": label, "detail": None, "state": "pending"}
        for key, label in STAGE_DEFINITIONS
    ]


def _set_stage(run: SearchRun, index: int, state: str, detail: str | None = None) -> None:
    stages = list(run.stages or build_stages())
    while len(stages) < len(STAGE_DEFINITIONS):
        stages.append({"key": "", "label": "", "detail": None, "state": "pending"})
    stages[index] = {**stages[index], "state": state, "detail": detail}
    run.stages = stages
    run.save(update_fields=["stages"])


# --------------------------------------------------------------------------- #
# Entry points                                                                #
# --------------------------------------------------------------------------- #


def start_search(run_id: int) -> None:
    """Kick off a search run."""

    if not settings.SEARCH_RUN_ASYNC:
        _execute(run_id)
        return

    thread = threading.Thread(target=_execute, args=(run_id,), name=f"search-{run_id}", daemon=True)
    thread.start()


def execute_search_sync(run_id: int) -> None:
    """Run to completion in the current thread (CLI, tests)."""

    _execute(run_id)


def _execute(run_id: int) -> None:
    acquired = _semaphore.acquire(timeout=30)
    if not acquired:
        _fail(run_id, "The search queue is busy. Please try again in a moment.")
        return

    try:
        close_old_connections()
        _run(run_id)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user via `error`
        logger.exception("Search run %s failed", run_id)
        _fail(run_id, str(exc) or "The search failed unexpectedly.")
    finally:
        connection.close()
        _semaphore.release()


def _fail(run_id: int, message: str) -> None:
    try:
        run = SearchRun.objects.get(pk=run_id)
    except SearchRun.DoesNotExist:
        return
    run.status = SearchRun.Status.FAILED
    run.error = message
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error", "finished_at"])


# --------------------------------------------------------------------------- #
# The run                                                                     #
# --------------------------------------------------------------------------- #


#: How many profile skills to add to the search terms.
#:
#: A profile can list a dozen skills; each becomes a search request. This caps
#: the broadening pass so it cannot dominate the budget the adapters enforce.
MAX_PROFILE_SKILL_TERMS = 4


def _profile_skill_terms(user) -> list[str]:
    """Skills named in the user's profile, as search terms.

    Desired roles say what someone wants; their skills say what they can
    actually do, and the two overlap only partly. Searching on roles alone
    misses postings that match the skills but use a different job title — a
    profile listing Python and Linux should surface backend roles even when
    the user only asked for "AI".

    The profile's skills section is free text, so it is split on the usual
    separators and trimmed. Capped, because this feeds a search budget.
    """

    sections = {section.key: section.content for section in user.profile_sections.all()}
    raw = sections.get("skills", "") or ""

    terms: list[str] = []
    for chunk in re.split(r"[,\n;•|/]+", raw):
        cleaned = chunk.strip().strip(".-–—")
        # Skip fragments that are prose rather than a skill ("and", "etc").
        if not cleaned or len(cleaned) > 40 or len(cleaned.split()) > 3:
            continue
        terms.append(cleaned)
        if len(terms) >= MAX_PROFILE_SKILL_TERMS:
            break
    return terms


def _role_matching_titles(user, groups) -> list[str]:
    """Titles among `groups` that match one of the user's desired roles.

    Used to explain a filtered result: a listing that matches the roles but
    never states an employment type is the one worth naming, because the user
    would otherwise conclude nothing relevant was found.
    """

    desired_roles = list(getattr(getattr(user, "preferences", None), "desired_roles", []) or [])
    if not desired_roles:
        return []

    titles: list[str] = []
    for group in groups:
        title = group.primary.title
        if _titles_overlap(title, desired_roles):
            titles.append(title[:60])
    return titles


def _build_request(run: SearchRun) -> SearchRequest:
    """Translate stored criteria into a provider-independent request."""

    from jobs.sources.base import EmploymentType, WorkModel

    criteria = run.criteria or {}

    def as_list(key: str) -> list:
        value = criteria.get(key) or []
        return list(value) if isinstance(value, (list, tuple)) else [value]

    employment_types = []
    for value in as_list("employment_types"):
        try:
            employment_types.append(EmploymentType(value))
        except ValueError:
            continue

    work_models = []
    for value in as_list("work_models"):
        try:
            work_models.append(WorkModel(value))
        except ValueError:
            continue

    # Roles and skills are interleaved rather than concatenated. The adapters
    # cap how many terms they query, so a strict roles-first order lets five
    # desired roles consume the entire allowance and the specific skills that
    # actually distinguish the search — "Machine Learning", "Computer Vision" —
    # are never sent to the platform at all. Alternating keeps both kinds of
    # term inside the budget.
    role_terms = as_list("roles")
    skill_terms = _profile_skill_terms(run.user)

    ordered: list[str] = []
    for index in range(max(len(role_terms), len(skill_terms))):
        if index < len(role_terms):
            ordered.append(role_terms[index])
        if index < len(skill_terms):
            ordered.append(skill_terms[index])
    ordered.extend(as_list("keywords"))

    keywords: list[str] = []
    seen: set[str] = set()
    for term in ordered:
        cleaned = (term or "").strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            keywords.append(cleaned)

    return SearchRequest(
        keywords=keywords,
        locations=as_list("locations"),
        radius_km=criteria.get("radius_km", 50) or 50,
        employment_types=employment_types,
        sources=list(run.sources or []),
        posted_within_days=criteria.get("posted_within_days"),
        work_models=work_models,
        max_results=settings.SOURCE_MAX_RESULTS,
    )


def _has_live_provider(sources: list[str]) -> bool:
    """True when at least one requested source may actually be collected from.

    Uses `is_operational` rather than comparing against READY. A provider
    running under `PROVIDER_TEST_MODE` is usable but reports
    ENABLED_FOR_TESTING, so a READY-only check would declare that no live
    source exists and silently substitute sample data — which is exactly what
    happened.
    """

    from jobs.sources.registry import get_provider_status

    return any(get_provider_status(name).is_operational for name in (sources or []))


def _run(run_id: int) -> None:
    run = SearchRun.objects.select_related("user").get(pk=run_id)
    user = run.user

    run.status = SearchRun.Status.RUNNING
    run.started_at = timezone.now()
    run.stages = build_stages()
    run.save(update_fields=["status", "started_at", "stages"])

    request = _build_request(run)

    # ------------------------------------------------------------ 1. discover --
    _set_stage(run, 0, "active")

    sample_mode = not _has_live_provider(request.sources)

    if sample_mode:
        # No authorized live source is available. Use clearly-labelled synthetic
        # data so the workflow stays usable, and state that plainly on the run.
        from .sample_data import generate_sample_jobs

        raw_jobs = generate_sample_jobs(
            keywords=request.keywords, locations=request.locations, limit=request.max_results
        )
        result = PipelineResult()
    else:
        result = run_pipeline(request, providers=request.sources, apply_filter=True)
        raw_jobs = []

    run.discovered = len(raw_jobs) if sample_mode else result.raw_count
    run.save(update_fields=["discovered"])
    _set_stage(run, 0, "done", f"{run.discovered} listings found")
    time.sleep(_STAGE_PACING_SECONDS)

    # ------------------------------------------------------------- 2. extract --
    _set_stage(run, 1, "active")

    if sample_mode:
        from jobs.sources.dedup import deduplicate
        from jobs.sources.pipeline import split_by_employment_filter

        result.jobs = deduplicate(normalize_all(raw_jobs))
        result.raw_count = len(raw_jobs)
        # The employment filter must apply to sample data too, otherwise a
        # working-student-only search would silently return unrelated roles.
        result.jobs, result.untyped_withheld_jobs = split_by_employment_filter(
            result.jobs, request.employment_types
        )

    described = sum(1 for group in result.jobs if group.primary.description)
    detail = f"{described} postings with details"
    if result.untyped_withheld_jobs:
        # Surfaced here rather than only in the run notes, because the UI renders
        # stage details on a completed run but not its notes.
        #
        # The count alone reads as "nothing relevant was found", when the truth
        # is often the opposite: the listings that did match the user's roles
        # were set aside because the source never said what kind of contract
        # they are. Naming them turns a dead end into a decision the user can
        # act on — either widen the filter, or check those postings directly.
        matching = _role_matching_titles(user, result.untyped_withheld_jobs)
        detail += f" · {result.untyped_withheld} untyped set aside"
        if matching:
            detail += f", {len(matching)} of them matched your roles ({', '.join(matching[:3])})"
    _set_stage(run, 1, "done", detail)
    time.sleep(_STAGE_PACING_SECONDS)

    # -------------------------------------------------------------- 3. dedupe --
    _set_stage(run, 2, "active")
    removed = result.duplicates_removed
    _set_stage(run, 2, "done", f"{removed} duplicates removed" if removed else "No duplicates found")
    time.sleep(_STAGE_PACING_SECONDS)

    # ------------------------------------------------------------- 4. compare --
    _set_stage(run, 3, "active")
    insights = _score(user, result.jobs)
    strong = sum(1 for insight in insights if insight.match == "strong")
    good = sum(1 for insight in insights if insight.match == "good")
    run.matched = strong + good
    run.save(update_fields=["matched"])
    _set_stage(run, 3, "done", f"{strong} strong · {good} good")
    time.sleep(_STAGE_PACING_SECONDS)

    # ------------------------------------------------------------- 5. prepare --
    _set_stage(run, 4, "active")
    created = _persist(user, result.jobs, insights)
    _set_stage(run, 4, "done", f"{created} new opportunities saved")
    time.sleep(_STAGE_PACING_SECONDS * 0.5)

    # -------------------------------------------------------------- finalise --
    run.status = SearchRun.Status.COMPLETED
    run.finished_at = timezone.now()

    notes: list[str] = list(result.warnings)
    if sample_mode:
        notes.insert(
            0,
            "No authorized live source is available, so sample data was used. "
            "See the provider authorization matrix.",
        )
    run.error = " ".join(notes[:4])
    run.save(update_fields=["status", "finished_at", "error"])

    if run.mode == SearchRun.Mode.AUTOMATIC:
        auto, _ = AutoSearchSettings.objects.get_or_create(user=user)
        auto.last_run_at = run.finished_at
        auto.last_error = " ".join(notes[:2])
        auto.save()

    if created:
        ActivityEntry.objects.create(
            user=user,
            kind=ActivityEntry.Kind.DISCOVERED,
            title=f"{created} new job{'s' if created != 1 else ''} discovered",
            subtitle="Automatic search" if run.mode == SearchRun.Mode.AUTOMATIC else "Manual search",
        )


# --------------------------------------------------------------------------- #
# Matching and persistence                                                    #
# --------------------------------------------------------------------------- #


def _score(user, groups) -> list:
    """Run the matching engine for every deduplicated job."""

    profile = getattr(user, "profile", None)
    preferences = getattr(user, "preferences", None)
    sections = {section.key: section.content for section in user.profile_sections.all()}

    desired_roles = list(getattr(preferences, "desired_roles", []) or [])
    preferred_locations = list(getattr(preferences, "locations", []) or [])
    employment_types = list(getattr(preferences, "employment_types", []) or [])
    preferred_sources = list(getattr(preferences, "sources", []) or [])
    keywords = list(getattr(preferences, "keywords", []) or [])

    insights = []
    for group in groups:
        job = group.primary
        insights.append(
            build_insight(
                job_title=job.title,
                company=job.company,
                location=job.location,
                employment_type=job.employment_type.value,
                source=job.source,
                job_skills=job.required_skills,
                job_requirements=[],
                job_summary=job.description,
                desired_roles=desired_roles,
                preferred_locations=preferred_locations,
                employment_types=employment_types,
                preferred_sources=preferred_sources,
                keywords=keywords,
                profile_sections=sections,
                profile_summary=getattr(profile, "summary", "") or "",
                radius_km=getattr(preferences, "radius_km", None),
            )
        )
    return insights


def _persist(user, groups, insights) -> int:
    """Create `Job` rows for listings the user does not already have."""

    existing = set(Job.objects.filter(user=user).values_list("fingerprint", flat=True))
    created = 0

    with transaction.atomic():
        for group, insight in zip(groups, insights):
            job: NormalizedJob = group.primary

            fingerprint = job_fingerprint(job.source, job.source_url, job.title, job.company)
            if fingerprint in existing:
                _merge_provenance(user, fingerprint, group)
                continue

            Job.objects.create(
                user=user,
                title=job.title[:255],
                company=job.company[:255],
                location=job.location[:255],
                city=job.city[:120],
                region=job.region[:120],
                country=job.country[:80],
                employment_type=job.employment_type.value,
                employment_type_confidence=job.employment_type_confidence,
                employment_type_evidence=job.employment_type_evidence,
                employment_type_candidates=[
                    category.value for category in job.employment_type_candidates
                ],
                language=job.language,
                language_requirement=job.language_requirement,
                language_evidence=job.language_evidence,
                work_model=job.work_model.value,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                summary=(job.description[:400] if job.description else ""),
                description=job.description,
                skills=job.required_skills,
                source=job.source[:64],
                source_url=job.source_url[:1024],
                external_id=job.external_id[:128],
                is_user_provided=bool(job.raw_source_data.get("user_provided")),
                provenance=group.as_provenance(),
                raw_source_data=job.raw_source_data,
                posted_at=job.posted_at or timezone.now(),
                collected_at=job.collected_at or timezone.now(),
                match=insight.match,
                cv_alignment=insight.cv_dicts,
                preference_fit=insight.preference_dicts,
                status=Job.Status.NEW,
                fingerprint=fingerprint,
            )
            existing.add(fingerprint)
            created += 1

    return created


def _merge_provenance(user, fingerprint: str, group) -> None:
    """Record that an existing job was also advertised on another source."""

    job = Job.objects.filter(user=user, fingerprint=fingerprint).first()
    if job is None:
        return

    known = {(entry.get("source"), entry.get("url")) for entry in (job.provenance or [])}
    merged = list(job.provenance or [])
    for entry in group.as_provenance():
        key = (entry.get("source"), entry.get("url"))
        if key not in known:
            merged.append(entry)
            known.add(key)

    if len(merged) != len(job.provenance or []):
        job.provenance = merged
        job.save(update_fields=["provenance", "updated_at"])


# --------------------------------------------------------------------------- #
# Scheduling                                                                  #
# --------------------------------------------------------------------------- #


def criteria_from_preferences(user, sources: list[str] | None = None) -> dict:
    """Build a stored-criteria dict from a user's saved preferences."""

    preferences = getattr(user, "preferences", None)
    return {
        "roles": list(getattr(preferences, "desired_roles", []) or []),
        "locations": list(getattr(preferences, "locations", []) or []),
        "radius_km": getattr(preferences, "radius_km", 50),
        "employment_types": list(getattr(preferences, "employment_types", []) or []),
        "keywords": list(getattr(preferences, "keywords", []) or []),
        "sources": list(sources or []),
        "use_saved_preferences": True,
    }


def run_scheduled_searches(*, force: bool = False, now=None) -> int:
    """Start a search for every user whose scheduled time has arrived.

    Invoked from `manage.py run_scheduled_searches`, which an external timer
    (cron, systemd timer) calls. That process is short-lived, so runs execute
    inline: `start_search` would hand the work to a daemon thread that is
    killed the moment the command returns, leaving the run stuck at "running"
    forever and the user with nothing.

    Only runs that are actually due are started. A timer ticks far more often
    than any user's schedule (quarter-hourly, say), so without this check a
    daily setting would fire once per tick.

    A user who still has a queued or running search is skipped, so a slow or
    hung run cannot stack up behind itself.
    """

    now = now or timezone.now()

    due = AutoSearchSettings.objects.filter(enabled=True).select_related("user")
    if not force:
        # `next_run_at` is null only for a row saved before it was populated,
        # which should still run rather than never run.
        due = due.filter(Q(next_run_at__lte=now) | Q(next_run_at__isnull=True))

    in_flight = set(
        SearchRun.objects.filter(
            status__in=[SearchRun.Status.QUEUED, SearchRun.Status.RUNNING]
        ).values_list("user_id", flat=True)
    )

    started = 0
    for auto in due:
        if auto.user_id in in_flight:
            logger.info("Skipping scheduled search for user %s: a run is in progress", auto.user_id)
            continue

        criteria = criteria_from_preferences(auto.user, sources=list(auto.sources or []))

        run = SearchRun.objects.create(
            user=auto.user,
            mode=SearchRun.Mode.AUTOMATIC,
            status=SearchRun.Status.QUEUED,
            criteria=criteria,
            criteria_summary=summarise_criteria(criteria),
            sources=list(auto.sources or []),
            stages=build_stages(),
        )
        execute_search_sync(run.id)
        started += 1

    return started


def summarise_criteria(criteria: dict) -> str:
    """Human-readable one-line criteria summary shown in history."""

    parts: list[str] = []
    roles = criteria.get("roles") or []
    if roles:
        parts.append(", ".join(roles[:2]))
    locations = criteria.get("locations") or []
    if locations:
        parts.append(str(locations[0]))
    radius = criteria.get("radius_km", criteria.get("radiusKm"))
    if radius is not None:
        parts.append(f"{radius} km")
    return " · ".join(parts) or "Profile preferences"
