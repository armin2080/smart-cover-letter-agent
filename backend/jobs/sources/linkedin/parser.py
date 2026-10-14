"""LinkedIn parsing.

The public guest endpoint returns server-rendered HTML job cards. These
selectors were verified against the live markup and independently corroborated
by the equivalent implementation in the MIT-licensed `alwedo/jobber` project
(`scrape/linkedin/linkedin.go`), which uses the same structure.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from jobs.sources.base import RawJob

SOURCE_NAME = "LinkedIn"

BASE_URL = "https://www.linkedin.com"
SEARCH_ENDPOINT = "/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_ENDPOINT = "/jobs-guest/jobs/api/jobPosting/{job_id}"

#: Stable identifier embedded in each card as `data-entity-urn="urn:li:jobPosting:<id>"`.
URN_RE = re.compile(r"urn:li:jobPosting:(\d+)")
#: Job id also appears in the canonical view URL.
VIEW_ID_RE = re.compile(r"/view/(?:[^/]*-)?(\d{6,})")


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def strip_tracking(url: str) -> str:
    """Remove tracking query parameters from a LinkedIn job URL."""

    return (url or "").split("?")[0].split("#")[0]


def parse_search_page(html: str) -> list[RawJob]:
    """Parse one page of guest search results into `RawJob` records."""

    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[RawJob] = []

    for card in soup.select("li"):
        card_element = card.select_one(".base-search-card") or card
        title_el = card_element.select_one(".base-search-card__title")
        title = _clean(title_el.get_text(" ", strip=True)) if title_el else ""
        if not title:
            continue

        company_el = card_element.select_one(".base-search-card__subtitle")
        location_el = card_element.select_one(".job-search-card__location")
        time_el = card_element.select_one("time")
        link_el = card_element.select_one("a.base-card__full-link")

        urn_match = URN_RE.search(str(card_element))
        external_id = urn_match.group(1) if urn_match else ""

        url = strip_tracking(link_el.get("href", "")) if link_el else ""
        if not url and external_id:
            url = f"{BASE_URL}/jobs/view/{external_id}"

        # `datetime` is an ISO date; the element text is a relative phrase.
        posted_raw = ""
        if time_el is not None:
            posted_raw = time_el.get("datetime", "") or _clean(time_el.get_text(" ", strip=True))

        jobs.append(
            RawJob(
                source=SOURCE_NAME,
                external_id=external_id,
                title=title,
                company=_clean(company_el.get_text(" ", strip=True)) if company_el else "",
                location=_clean(location_el.get_text(" ", strip=True)) if location_el else "",
                url=url,
                posted_at_raw=posted_raw,
                payload={"urn": external_id, "card_text": _clean(card_element.get_text(" ", strip=True))[:400]},
            )
        )

    return jobs


def parse_job_detail(html: str) -> dict:
    """Extract the description and structured fields from a detail page."""

    soup = BeautifulSoup(html or "", "html.parser")
    result: dict[str, str] = {}

    description = soup.select_one(".description__text, .show-more-less-html__markup")
    if description:
        result["description"] = _clean(description.get_text(" ", strip=True))[:4000]

    for label, selector in (
        ("seniority", ".description__job-criteria-subheader"),
        ("employment_type", ".description__job-criteria-text"),
    ):
        element = soup.select_one(selector)
        if element:
            text = _clean(element.get_text(" ", strip=True))
            if text and label == "employment_type":
                result["employment_type_raw"] = text

    return result
