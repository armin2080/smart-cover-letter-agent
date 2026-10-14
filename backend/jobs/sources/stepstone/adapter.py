"""StepStone adapter.

GATED: requires an explicit enable **and** a recorded written authorization.
See `jobs/sources/registry.py`.
"""

from __future__ import annotations

import logging
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
        """Search once per keyword and merge the results.

        Only the first keyword used to be searched, so a user whose desired
        roles are `["AI", "Data", "Web"]` had every source queried for the
        literal string "AI" — which returns nothing, and looked like the
        sources were broken rather than the query.

        The number of queries is capped: each one costs a request, and this
        adapter talks to a real platform.
        """

        jobs: list[RawJob] = []
        seen: set[str] = set()
        limit = min(request.max_results or settings.SOURCE_MAX_RESULTS, settings.SOURCE_MAX_RESULTS)

        for term in _search_terms(request):
            if len(jobs) >= limit:
                break
            for job in self._search_term(term, request, limit - len(jobs)):
                key = job.external_id or job.url or job.title.lower()
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)

        return jobs

    def _search_term(self, term: str, request: SearchRequest, remaining: int) -> list[RawJob]:
        jobs: list[RawJob] = []
        location = request.locations[0] if request.locations else "Deutschland"

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
