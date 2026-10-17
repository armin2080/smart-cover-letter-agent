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
        """Fetch one city page per requested location and merge.

        Only the first location used to be fetched, so a user who added a
        second city to their preferences got identical results either way.
        Stellenwerk serves a card list per city with no keyword parameter, so
        the only way to cover more ground is to ask for more cities.
        """

        locations = request.locations or ["Dortmund"]
        limit = min(request.max_results or settings.SOURCE_MAX_RESULTS, settings.SOURCE_MAX_RESULTS)
        # Split the allowance so a busy first city cannot leave the others
        # unsearched.
        per_location = max(1, limit // len(locations))

        jobs: list[RawJob] = []
        seen: set[str] = set()
        failures: list[Exception] = []

        for location in locations:
            city = parser.resolve_city(location)
            if city is None:
                # Never substitute another city: the user would be shown jobs
                # from somewhere they never asked for, with nothing saying so.
                logger.info(
                    "Stellenwerk does not cover %r; skipping it for this source", location
                )
                continue

            try:
                response = self.client.get(f"{parser.BASE_URL}{parser.CITY_URL.format(city=city)}")
            except Exception as exc:  # noqa: BLE001 - reported below if nothing works
                logger.warning("Stellenwerk request failed for %s: %s", location, exc)
                failures.append(exc)
                continue

            for job in parser.parse_city_page(response.text, city=city)[:per_location]:
                key = job.external_id or job.url or job.title.lower()
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)

        # A block or outage must still reach the pipeline as a source failure,
        # but only when it stopped us collecting anything at all. Discarding
        # the cities that did work would be worse than reporting a partial run.
        if not jobs and failures:
            raise failures[0]

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
