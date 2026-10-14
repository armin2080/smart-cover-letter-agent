"""Manual, user-directed job import.

This is the path that works without any platform authorization, because it
performs no third-party automated access: the user supplies the listing
themselves.

Deliberately, the supplied URL is **not** fetched. Retrieving it would be
automated access to that platform, which is exactly what the authorization gate
exists to prevent. The user's own description text is used instead.
"""

from __future__ import annotations

from jobs.sources.base import JobSourceAdapter, RawJob, SearchRequest

SOURCE_NAME = "Manual"


class ManualImportAdapter(JobSourceAdapter):
    """Adapter facade for manually added listings.

    Import happens through `build_manual_job`, which the API calls directly; the
    `search` method exists only to satisfy the interface and always returns an
    empty list, because manual listings are never "searched for".
    """

    name = "manual"
    display_name = "Manually added"

    def search(self, request: SearchRequest) -> list[RawJob]:  # noqa: ARG002
        return []


def build_manual_job(
    *,
    url: str,
    title: str,
    company: str = "",
    location: str = "",
    employment_type: str = "",
    description: str = "",
    notes: str = "",
) -> RawJob:
    """Build a `RawJob` from user-supplied fields.

    The record is clearly labelled as user-provided so it is never confused with
    an authorised source result.
    """

    payload = {
        "user_provided": True,
        "notes": (notes or "").strip()[:2000],
    }

    return RawJob(
        source=SOURCE_NAME,
        external_id="",
        title=(title or "").strip(),
        company=(company or "").strip(),
        location=(location or "").strip(),
        url=(url or "").strip(),
        description=(description or "").strip()[:8000],
        employment_type_raw=(employment_type or "").strip(),
        payload=payload,
    )
