"""LinkedIn adapter.

GATED: this adapter only runs when the registry reports `ProviderStatus.READY`,
which requires both an explicit enable and a recorded written authorization.
See `jobs/sources/registry.py`.
"""

from __future__ import annotations

import logging
import math

from django.conf import settings

from jobs.sources.base import JobSourceAdapter, RawJob, SearchRequest, _search_terms
from jobs.sources.http import SourceBlocked, SourceHttpClient
from jobs.sources.linkedin import parser

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_OFFSET = 40


class LinkedInAdapter(JobSourceAdapter):
    name = "linkedin"
    display_name = "LinkedIn"

    def __init__(self, client: SourceHttpClient | None = None):
        self.client = client or SourceHttpClient(
            timeout=settings.SOURCE_HTTP_TIMEOUT_SECONDS,
        )

    def search(self, request: SearchRequest) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        limit = min(request.max_results or settings.SOURCE_MAX_RESULTS, settings.SOURCE_MAX_RESULTS)
        locations = request.locations or ["Deutschland"]

        # Same two-loop shape as the other adapters: every term, in every
        # requested location. Using the shared helper also means the search
        # gets the cross-language expansions instead of a hardcoded slice of
        # the raw keyword list.
        per_location = max(1, limit // len(locations))

        # The same split between terms: one broad term can otherwise fill the
        # whole allowance and leave the specific ones unqueried.
        terms = _search_terms(request)
        per_term = max(1, math.ceil(per_location / max(1, len(terms))))

        for location in locations:
            if len(jobs) >= limit:
                break

            found_here = 0
            for keyword in terms:
                if found_here >= per_location or len(jobs) >= limit:
                    break

                offset = 0
                term_ceiling = min(per_term, per_location)
                while (
                    found_here < term_ceiling
                    and len(jobs) < limit
                    and offset < MAX_OFFSET
                ):
                    try:
                        response = self.client.get(
                            f"{parser.BASE_URL}{parser.SEARCH_ENDPOINT}",
                            params={"keywords": keyword, "location": location, "start": offset},
                        )
                    except SourceBlocked:
                        # Surface to the pipeline: rate limited or forbidden. Never retried.
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("LinkedIn search failed at offset %s: %s", offset, exc)
                        break

                    page = parser.parse_search_page(response.text)
                    if not page:
                        break

                    added = 0
                    for job in page:
                        key = job.external_id or job.url or job.title.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        jobs.append(job)
                        added += 1
                        found_here += 1
                        if found_here >= term_ceiling or len(jobs) >= limit:
                            break

                    if added == 0:
                        break
                    offset += PAGE_SIZE

        return jobs

    def enrich(self, job: RawJob) -> RawJob:
        """Fetch the posting description to improve classification and matching."""

        match = parser.VIEW_ID_RE.search(job.url) or parser.URN_RE.search(job.external_id or "")
        if not match:
            return job

        job_id = match.group(1)
        detail_url = f"{parser.BASE_URL}{parser.DETAIL_ENDPOINT.format(job_id=job_id)}"
        try:
            response = self.client.get(detail_url)
        except SourceBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
            logger.debug("LinkedIn enrichment failed for %s: %s", job_id, exc)
            return job

        detail = parser.parse_job_detail(response.text)
        if detail.get("description"):
            job.description = detail["description"]
        if detail.get("employment_type_raw"):
            job.employment_type_raw = detail["employment_type_raw"]
        job.payload = {**job.payload, "enriched": True}
        return job
