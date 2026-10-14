"""Stellenwerk adapter.

GATED: requires an explicit enable **and** a recorded written authorization.
See `jobs/sources/registry.py`.
"""

from __future__ import annotations

import logging

from django.conf import settings

from jobs.sources.base import JobSourceAdapter, RawJob, SearchRequest
from jobs.sources.http import SourceHttpClient
from jobs.sources.stellenwerk import parser

logger = logging.getLogger(__name__)


class StellenwerkAdapter(JobSourceAdapter):
    name = "stellenwerk"
    display_name = "Stellenwerk"

    def __init__(self, client: SourceHttpClient | None = None):
        self.client = client or SourceHttpClient(timeout=settings.SOURCE_HTTP_TIMEOUT_SECONDS)

    def search(self, request: SearchRequest) -> list[RawJob]:
        location = request.locations[0] if request.locations else "Dortmund"
        city = parser.resolve_city(location)
        limit = min(request.max_results or settings.SOURCE_MAX_RESULTS, settings.SOURCE_MAX_RESULTS)

        response = self.client.get(f"{parser.BASE_URL}{parser.CITY_URL.format(city=city)}")
        jobs = parser.parse_city_page(response.text, city=city)

        # Stellenwerk exposes a single page of cards per city; results are then
        # filtered by the shared pipeline rather than by extra requests.
        return jobs[:limit]

    def enrich(self, job: RawJob) -> RawJob:
        """Fetch the detail page so the classifier can use the full description."""

        if not job.url:
            return job

        try:
            response = self.client.get(job.url)
        except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
            logger.debug("Stellenwerk enrichment failed for %s: %s", job.url, exc)
            return job

        detail = parser.parse_job_detail(response.text)
        if detail.get("description"):
            job.description = detail["description"]
        job.payload = {**job.payload, "enriched": True}
        return job
