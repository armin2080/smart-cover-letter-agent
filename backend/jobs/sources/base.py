"""Shared types and the adapter interface for every job source.

Nothing in this module knows about Django models or about any particular
platform. Parsing lives in each adapter package; matching and persistence live
outside, in `jobs.matching` and the search pipeline.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# --------------------------------------------------------------------------- #
# Employment types                                                            #
# --------------------------------------------------------------------------- #


class EmploymentType(str, enum.Enum):
    """Internal employment categories.

    Values are stable strings because they are persisted and exposed over the
    API. `UNKNOWN` is a first-class outcome: an ambiguous listing must never be
    forced into a category we cannot support with evidence.
    """

    WORKING_STUDENT = "working-student"
    INTERNSHIP = "internship"
    STUDENT_ASSISTANT = "student-assistant"
    PART_TIME = "part-time"
    FULL_TIME = "full-time"
    MINI_JOB = "minijob"
    TEMPORARY = "temporary"
    APPRENTICESHIP = "apprenticeship"
    OTHER = "other"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            EmploymentType.WORKING_STUDENT: "Working student",
            EmploymentType.INTERNSHIP: "Internship",
            EmploymentType.STUDENT_ASSISTANT: "Student assistant",
            EmploymentType.PART_TIME: "Part-time",
            EmploymentType.FULL_TIME: "Full-time",
            EmploymentType.MINI_JOB: "Minijob",
            EmploymentType.TEMPORARY: "Temporary",
            EmploymentType.APPRENTICESHIP: "Apprenticeship",
            EmploymentType.OTHER: "Other",
            EmploymentType.UNKNOWN: "Unknown",
        }[self]


#: Employment types that count as "student employment" for search filtering.
#: The product goal is surfacing working-student style roles, and a university
#: HiWi post is the same kind of opportunity as a Werkstudent post, so both are
#: included when a user filters for student work.
STUDENT_EMPLOYMENT_TYPES: frozenset[EmploymentType] = frozenset(
    {EmploymentType.WORKING_STUDENT, EmploymentType.STUDENT_ASSISTANT}
)


class WorkModel(str, enum.Enum):
    """Where the work is performed."""

    ON_SITE = "on-site"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Provider status and authorization                                           #
# --------------------------------------------------------------------------- #


class ProviderStatus(str, enum.Enum):
    """Lifecycle state of a source integration.

    The distinction that matters most is between a connector that has been
    *proven against fixtures* and one that is *authorised to collect live data*.
    """

    READY = "ready"
    """Implemented, fixture-tested, and authorised for live collection."""

    ENABLED_FOR_TESTING = "enabled-for-testing"
    """Switched on through `PROVIDER_TEST_MODE`, which waives the recorded
    authorization requirement so the adapters can be evaluated before any
    agreement exists.

    It is usable, so the pipeline treats it as operational, but it is
    deliberately **not** READY: no authorization covers this collection, and
    every surface that reports status must say so.
    """

    DISABLED_AUTHORIZATION_PENDING = "disabled-authorization-pending"
    """Implemented and fixture-tested, but no written platform authorisation
    exists, so live collection is switched off."""

    DISABLED_BY_CONFIG = "disabled-by-config"
    """Switched off through configuration."""

    TEMPORARILY_UNAVAILABLE = "temporarily-unavailable"
    """Authorised, but currently failing (rate limited, upstream error)."""

    INTEGRATION_ERROR = "integration-error"
    """The adapter itself is misconfigured or raised unexpectedly."""

    @property
    def is_operational(self) -> bool:
        """True when the adapter may actually be called right now.

        Covers both the authorised case and the explicit test override.
        """

        return self in {ProviderStatus.READY, ProviderStatus.ENABLED_FOR_TESTING}

    @property
    def is_authorized(self) -> bool:
        """True only when a recorded authorization covers this collection."""

        return self is ProviderStatus.READY

    @property
    def label(self) -> str:
        return {
            ProviderStatus.READY: "Ready",
            ProviderStatus.ENABLED_FOR_TESTING: "Test mode — no authorization",
            ProviderStatus.DISABLED_AUTHORIZATION_PENDING: "Disabled — authorization pending",
            ProviderStatus.DISABLED_BY_CONFIG: "Disabled by configuration",
            ProviderStatus.TEMPORARILY_UNAVAILABLE: "Temporarily unavailable",
            ProviderStatus.INTEGRATION_ERROR: "Integration error",
        }[self]


@dataclass
class SourceHealth:
    """Result of an adapter health probe."""

    source: str
    status: ProviderStatus
    detail: str = ""
    checked_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Raw and normalized records                                                  #
# --------------------------------------------------------------------------- #


@dataclass
class RawJob:
    """A listing exactly as parsed from a source, before normalization.

    Keeping the untouched payload lets us store `raw_source_data` for
    traceability and re-parse later if our normalization improves.
    """

    source: str
    external_id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    employment_type_raw: str = ""
    posted_at_raw: str = ""
    salary_raw: str = ""
    work_model_raw: str = ""
    #: Free-form structured data from the source (e.g. a JSON API payload).
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedJob:
    """The standardised representation every adapter must produce."""

    source: str
    source_url: str
    title: str
    company: str

    external_id: str = ""

    location: str = ""
    city: str = ""
    region: str = ""
    country: str = "Germany"

    description: str = ""

    employment_type: EmploymentType = EmploymentType.UNKNOWN
    employment_type_confidence: float = 0.0
    employment_type_evidence: list[str] = field(default_factory=list)
    #: Categories that had evidence. Empty when the listing stated no type.
    employment_type_candidates: list[EmploymentType] = field(default_factory=list)

    work_model: WorkModel = WorkModel.UNKNOWN

    salary_min: int | None = None
    salary_max: int | None = None

    posted_at: datetime | None = None
    collected_at: datetime | None = None

    keywords: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)

    raw_source_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        self.source_url = (self.source_url or "").strip()

    @property
    def is_valid(self) -> bool:
        """Minimum viable record. A listing without a title is unusable."""

        return bool(self.title)


# --------------------------------------------------------------------------- #
# Search request                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class SearchRequest:
    """A normalized, provider-independent search query."""

    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    radius_km: int = 50
    employment_types: list[EmploymentType] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    posted_within_days: int | None = None
    work_models: list[WorkModel] = field(default_factory=list)
    max_results: int = 50

    def summary(self) -> str:
        parts: list[str] = []
        if self.keywords:
            parts.append(", ".join(self.keywords[:2]))
        if self.locations:
            parts.append(self.locations[0])
        if self.radius_km is not None:
            parts.append(f"{self.radius_km} km")
        return " · ".join(parts) or "Profile preferences"


#: How many distinct search terms one source will be queried with.
#:
#: Each term costs a request, so this is a budget rather than a preference. A
#: user's desired roles are often a list of themes — "AI", "Data", "Web" —
#: and querying only the first returns nothing useful.
MAX_SEARCH_TERMS = 3


def _search_terms(request: SearchRequest) -> list[str]:
    """The distinct terms to query a source with, in order.

    Falls back to a broad term when the user has expressed no preference, so a
    search still returns something rather than querying an empty string.
    """

    seen: list[str] = []
    for term in request.keywords or []:
        cleaned = (term or "").strip()
        if cleaned and cleaned.lower() not in {t.lower() for t in seen}:
            seen.append(cleaned)
        if len(seen) >= MAX_SEARCH_TERMS:
            break

    return seen or ["Werkstudent"]


# --------------------------------------------------------------------------- #
# Adapter interface                                                           #
# --------------------------------------------------------------------------- #


class SourceUnavailable(RuntimeError):
    """Raised when an adapter cannot be used.

    Carries the provider status so the pipeline can report *why* a source
    produced nothing, rather than silently returning an empty list.
    """

    def __init__(self, source: str, status: ProviderStatus, detail: str = ""):
        self.source = source
        self.status = status
        self.detail = detail
        super().__init__(f"{source}: {status.label}" + (f" ({detail})" if detail else ""))


class JobSourceAdapter(ABC):
    """Contract every job source must satisfy.

    Implementations are deliberately thin: they fetch, parse into `RawJob`, and
    hand off. Normalization, classification, deduplication and matching are
    shared so behaviour is identical across sources.
    """

    #: Stable identifier used in configuration, storage and the API.
    name: str = ""

    #: Human-readable name for the UI.
    display_name: str = ""

    @abstractmethod
    def search(self, request: SearchRequest) -> list[RawJob]:
        """Fetch listings for `request`.

        Implementations must not attempt to circumvent access controls. A 401,
        403 or 429 response means "stop", not "retry harder".
        """

    def normalize(self, raw: RawJob) -> NormalizedJob:
        """Convert a raw record into the standard representation.

        The default implementation delegates to the shared normalizer, which
        applies the employment classifier and location parsing. Adapters only
        override this when a source needs genuinely different handling.
        """

        from jobs.sources.normalization import normalize_raw_job

        return normalize_raw_job(raw)

    def health_check(self) -> SourceHealth:
        """Report whether this adapter may be used, without making a request."""

        from jobs.sources.registry import get_provider_status

        return SourceHealth(source=self.name, status=get_provider_status(self.name))

    # -- helpers shared by adapters ---------------------------------------- #

    @staticmethod
    def source_url_is_safe(url: str) -> bool:
        """Guard against non-http(s) URLs arriving from upstream payloads."""

        return url.startswith("http://") or url.startswith("https://")
