"""StepStone parsing.

StepStone exposes a structured search API that returns JSON rather than HTML.
This is materially more reliable than screen-scraping the result page, and the
request shape below is corroborated by the MIT-licensed `alwedo/jobber`
implementation (`scrape/stepstone/stepstone.go`), which POSTs the same endpoint
and decodes the same `items` / `pagination` structure.

Compliance note
---------------
The endpoint being publicly reachable is not permission to use it. This parser
is exercised against local fixtures only; live calls happen solely through the
authorization gate in `jobs/sources/registry.py`.
"""

from __future__ import annotations

import json

from jobs.sources.base import RawJob

SOURCE_NAME = "StepStone"

BASE_URL = "https://www.stepstone.de"
RESULTLIST_ENDPOINT = "/public-api/resultlist/unifiedResultlist"
SEARCH_PATH_TEMPLATE = "/work/{keywords}/in-{location}"

#: Search parameters understood by the result-list endpoint.
PARAM_PAGE = "page"
PARAM_SORT = "sort"
PARAM_SORT_BY_AGE = "2"
PARAM_AGE = "ag"
PARAM_AGE_ONE_DAY = "age_1"
PARAM_AGE_ONE_WEEK = "age_7"

#: `siteId` 250 is the German StepStone site.
SITE_ID = 250


def build_search_url(keywords: str, location: str) -> str:
    """Build the search path segment (unencoded; callers URL-encode)."""

    return SEARCH_PATH_TEMPLATE.format(keywords=keywords, location=location)


def build_request_body(search_url: str, *, session_id: str) -> dict:
    """Build the POST body for the result-list endpoint.

    `userHashId` is a required field of the endpoint. We send a single stable,
    non-identifying value supplied by configuration. **Rotating it per request
    would be an evasion technique and is deliberately not done.**
    """

    return {
        "url": search_url,
        "lang": "en",
        "siteId": SITE_ID,
        "userData": {"userHashId": session_id},
        "fields": ["items", "pagination"],
    }


def parse_result_list(payload: str | dict) -> tuple[list[RawJob], dict]:
    """Parse a result-list response.

    Returns the parsed jobs and the pagination block, so the adapter can decide
    whether to continue.
    """

    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except ValueError:
            return [], {}
    else:
        data = payload or {}

    items = data.get("items") or []
    pagination = data.get("pagination") or {}

    jobs: list[RawJob] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = (item.get("title") or "").strip()
        if not title:
            continue

        relative_url = (item.get("url") or "").strip()
        if relative_url.startswith("/"):
            url = f"{BASE_URL}{relative_url}"
        elif relative_url.startswith("http"):
            url = relative_url
        else:
            url = ""

        jobs.append(
            RawJob(
                source=SOURCE_NAME,
                external_id=str(item.get("id") or ""),
                title=title,
                company=(item.get("companyName") or "").strip(),
                location=(item.get("location") or "").strip(),
                url=url,
                description=(item.get("textSnippet") or "").strip(),
                posted_at_raw=str(item.get("datePosted") or ""),
                payload=item,
            )
        )

    return jobs, pagination


def total_pages(pagination: dict) -> int:
    try:
        return int(pagination.get("pageCount") or 0)
    except (TypeError, ValueError):
        return 0
