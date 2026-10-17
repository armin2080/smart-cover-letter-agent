"""Reusable jobs-domain operations."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .matching import build_insight
from .models import Job

User = get_user_model()


def refresh_user_matches(user, *, only_statuses: set[str] | None = None) -> int:
    """Recompute stored match analysis for a user's jobs.

    Match analysis is written once when a job is discovered. If the user later
    edits their CV or preferences, existing rows would otherwise keep a stale
    verdict — this rebuilds them from the current profile.

    Returns the number of jobs updated.
    """

    profile = getattr(user, "profile", None)
    preferences = getattr(user, "preferences", None)
    sections = {section.key: section.content for section in user.profile_sections.all()}

    desired_roles = list(getattr(preferences, "desired_roles", []) or [])
    preferred_locations = list(getattr(preferences, "locations", []) or [])
    employment_types = list(getattr(preferences, "employment_types", []) or [])
    preferred_sources = list(getattr(preferences, "sources", []) or [])
    keywords = list(getattr(preferences, "keywords", []) or [])
    profile_summary = getattr(profile, "summary", "") or ""

    queryset = Job.objects.filter(user=user)
    if only_statuses:
        queryset = queryset.filter(status__in=only_statuses)

    updated = 0
    for job in queryset.iterator():
        insight = build_insight(
            job_title=job.title,
            company=job.company,
            location=job.location,
            employment_type=job.employment_type,
            source=job.source,
            job_skills=job.skills,
            job_requirements=job.requirements,
            job_summary=job.summary,
            desired_roles=desired_roles,
            preferred_locations=preferred_locations,
            employment_types=employment_types,
            preferred_sources=preferred_sources,
            keywords=keywords,
            profile_sections=sections,
            profile_summary=profile_summary,
            radius_km=getattr(preferences, "radius_km", None),
        )

        if job.match != insight.match or job.cv_alignment != insight.cv_dicts or job.preference_fit != insight.preference_dicts:
            job.match = insight.match
            job.cv_alignment = insight.cv_dicts
            job.preference_fit = insight.preference_dicts
            job.save(update_fields=["match", "cv_alignment", "preference_fit", "updated_at"])
            updated += 1

    return updated
