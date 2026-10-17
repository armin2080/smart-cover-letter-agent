"""StepStone adapter.

GATED: requires an explicit enable **and** a recorded written authorization.
See `jobs/sources/registry.py`.
"""

from __future__ import annotations

import logging
import math
from urllib.parse import quote

from django.conf import settings

from jobs.sources.base import JobSourceAdapter, RawJob, SearchRequest, _search_terms
from jobs.sources.http import SourceHttpClient
from jobs.sources.stepstone import parser

logger = logging.getLogger(__name__)

MAX_PAGES = 5


class StepStoneAdapter(JobSourceAdapter):
    name = "stepstone"
    display_name = "StepStone"

    def __init__(self, client: SourceHttpClient | None = None, session_id: str | None = None):
        self.client = client or SourceHttpClient(timeout=settings.SOURCE_HTTP_TIMEOUT_SECONDS)
        # A single stable, non-identifying value. Never rotated per request.
        self.session_id = session_id or getattr(
            settings, "PROVIDER_STEPSTONE_SESSION_ID", "00000000-0000-4000-8000-000000000000"
        )

    def search(self, request: SearchRequest) -> list[RawJob]:
        """Search every keyword, in every requested location, and merge.

        Both loops matter. Only the first keyword used to be searched, so a
        user whose desired roles are `["AI", "Data", "Web"]` had every source
        queried for the literal string "AI" — which returns nothing, and looked
        like the sources were broken rather than the query. Only the first
        location was used either, so adding a second city to the preferences
        silently changed nothing at all.

        The number of queries is capped: each one costs a request, and this
        adapter talks to a real platform.
        """

        jobs: list[RawJob] = []
        seen: set[str] = set()
        limit = min(request.max_results or settings.SOURCE_MAX_RESULTS, settings.SOURCE_MAX_RESULTS)
        locations = request.locations or ["Deutschland"]

        # Split the allowance between locations. Without this a rich first city
        # satisfies `limit` on its own and the later ones are never searched,
        # which is indistinguishable from the second city being ignored.
        per_location = max(1, limit // len(locations))

        # ...and split it again between terms. A broad term such as "AI" returns
        # enough listings to fill the whole location on its own, so every
        # specific term after it — "Machine Learning", "Computer Vision" — was
        # never queried. Worse, those broad results are poor: a StepStone search
        # for "AI" comes back with childcare and cleaning jobs. Covering each
        # term a little beats filling the page with one of them.
        terms = _search_terms(request)
        per_term = max(1, math.ceil(per_location / max(1, len(terms))))

        for location in locations:
            if len(jobs) >= limit:
                break

            found_here = 0
            for term in terms:
                if found_here >= per_location or len(jobs) >= limit:
                    break

                remaining = min(per_term, per_location - found_here, limit - len(jobs))
                for job in self._search_term(term, location, remaining):
                    key = job.external_id or job.url or job.title.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(job)
                    found_here += 1

        return jobs

    def _search_term(self, term: str, location: str, remaining: int) -> list[RawJob]:
        jobs: list[RawJob] = []

        # StepStone expects spaces as '+', not '%20'.
        search_path = parser.build_search_url(quote(term), quote(location))

        for page in range(1, MAX_PAGES + 1):
            params = {
                parser.PARAM_SORT: parser.PARAM_SORT_BY_AGE,
                parser.PARAM_PAGE: page,
                parser.PARAM_AGE: parser.PARAM_AGE_ONE_WEEK,
            }
            url = f"{parser.BASE_URL}{search_path}"
            body = parser.build_request_body(
                f"{search_path}?{'&'.join(f'{k}={v}' for k, v in params.items())}",
                session_id=self.session_id,
            )

            try:
                response = self.client.post(
                    f"{parser.BASE_URL}{parser.RESULTLIST_ENDPOINT}",
                    json=body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            except Exception as exc:  # noqa: BLE001 - SourceBlocked propagates to the pipeline
                logger.warning("StepStone request failed for %r on page %s: %s", term, page, exc)
                raise

            page_jobs, pagination = parser.parse_result_list(response.text)
            if not page_jobs:
                break

            added = 0
            for job in page_jobs:
                jobs.append(job)
                added += 1
                if len(jobs) >= remaining:
                    break

            if added == 0 or len(jobs) >= remaining:
                break
            if parser.total_pages(pagination) and page >= parser.total_pages(pagination):
                break

        return jobs
