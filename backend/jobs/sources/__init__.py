"""Job source adapters.

Each external job platform is wrapped in an adapter that returns a **standardised**
job representation, so the matching engine and the API never depend on
source-specific parsing.

Layout::

    jobs/sources/
        base.py            shared types, adapter interface, provider status
        registry.py        adapter lookup + authorization gate
        classification.py  German/English employment-type classifier
        normalization.py   raw record -> NormalizedJob
        dedup.py           cross-source deduplication
        http.py            safe HTTP client (timeouts, backoff, Retry-After)
        linkedin/          adapter + parser + fixtures + tests
        stepstone/         adapter + parser + fixtures + tests
        stellenwerk/       adapter + parser + fixtures + tests
        manual/            user-provided import (always available)
"""

from jobs.sources.base import (
    EmploymentType,
    JobSourceAdapter,
    NormalizedJob,
    ProviderStatus,
    RawJob,
    SearchRequest,
    SourceHealth,
)

__all__ = [
    "EmploymentType",
    "JobSourceAdapter",
    "NormalizedJob",
    "ProviderStatus",
    "RawJob",
    "SearchRequest",
    "SourceHealth",
]
