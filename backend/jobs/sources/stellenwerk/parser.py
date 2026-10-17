"""Stellenwerk parsing.

Stellenwerk is a SvelteKit application. The city pages are server-rendered, so
the job cards are present in the initial HTML.

Card shape (verified against the live markup)::

    <a href="/dortmund/<slug>-<DDMMYY>-<id>">
      <p class="... font-bold">Job title</p>
      <p class="text-base text-gray-700">Company · City, Country</p>
      <span class="... rounded-full">Werkstudentenstelle</span>
      <p class="... text-sm">vor 5 Stunden</p>
    </a>

Detail pages carry the description in a deeply nested layout container, so the
description is located by descending to the densest content block rather than by
guessing a wrapper class.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from jobs.sources.base import RawJob

SOURCE_NAME = "Stellenwerk"

BASE_URL = "https://www.stellenwerk.de"
CITY_URL = "/{city}"

#: Job detail URLs look like `/dortmund/<slug>-<DDMMYY>-<id>`.
JOB_PATH_RE = re.compile(r"^/(?P<city>[a-z\-]+)/(?P<slug>[a-z0-9\-]+-\d{6}-\d+)$")

#: Chrome that must never be mistaken for a job description.
_CHROME_SELECTORS = ("nav", "header", "footer", "script", "style", "noscript", "aside")

#: Stellenwerk city slugs we know how to address.
KNOWN_CITIES = (
    "dortmund", "berlin", "hamburg", "muenchen", "muenster", "koeln",
    "frankfurt", "stuttgart", "duesseldorf", "leipzig", "dresden", "bochum",
    "essen", "bielefeld", "bonn", "aachen", "karlsruhe", "mannheim",
)

_CITY_ALIASES = {
    "munich": "muenchen",
    "cologne": "koeln",
    "dusseldorf": "duesseldorf",
    "münster": "muenster",
    "köln": "koeln",
    "münchen": "muenchen",
}

#: German characters folded to their ASCII transliteration before matching.
#: `KNOWN_CITIES` uses slugs like "duesseldorf", so without this "Düsseldorf"
#: matched nothing at all.
_UMLAUT_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _fold(text: str) -> str:
    return (text or "").lower().strip().translate(_UMLAUT_FOLD)


def resolve_city(location: str) -> str | None:
    """Map a user location label onto a Stellenwerk city slug.

    Returns `None` when the location cannot be addressed. Callers must not
    substitute a default city: quietly returning another city's jobs is worse
    than returning none, because nothing in the result reveals the swap. That
    is exactly what used to happen — "Düsseldorf" failed to match the known
    slug and every Düsseldorf search was answered with Dortmund.
    """

    folded = _fold(location)
    if not folded:
        return None

    for alias, slug in _CITY_ALIASES.items():
        if alias in folded:
            return slug
    for city in KNOWN_CITIES:
        if city in folded:
            return city
    return None


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def parse_city_page(html: str, *, city: str) -> list[RawJob]:
    """Parse a Stellenwerk city page into `RawJob` records."""

    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[RawJob] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        match = JOB_PATH_RE.match(anchor["href"])
        if not match:
            continue

        url = f"{BASE_URL}{anchor['href']}"
        if url in seen:
            continue
        seen.add(url)

        title_el = anchor.select_one("p.font-bold") or anchor.select_one("p")
        title = _clean(title_el.get_text(" ", strip=True)) if title_el else ""
        if not title:
            continue

        company = ""
        location = city.title()
        meta_el = anchor.select_one("p[class*='text-gray-700']")
        if meta_el:
            meta = _clean(meta_el.get_text(" ", strip=True))
            head, _, tail = meta.partition("·")
            company = head.strip()
            if tail.strip():
                location = tail.strip()

        # The rounded badge carries a structured employment hint such as
        # "Werkstudentenstelle" or "Absolvent:innenjob".
        badge_el = anchor.select_one("span[class*='rounded-full']")
        badge = _clean(badge_el.get_text(" ", strip=True)) if badge_el else ""

        time_el = anchor.select_one("p[class*='text-sm']")

        jobs.append(
            RawJob(
                source=SOURCE_NAME,
                external_id=match.group("slug"),
                title=title,
                company=company,
                location=location,
                url=url,
                employment_type_raw=badge,
                posted_at_raw=_clean(time_el.get_text(" ", strip=True)) if time_el else "",
                payload={"badge": badge, "slug": match.group("slug")},
            )
        )

    return jobs


def densest_content_block(html: str, *, min_chars: int = 200):
    """Return the tightest element holding the page's real content.

    Layout wrappers nest deeply, so selecting a parent would also capture
    navigation and footers. This strips chrome first, then repeatedly descends
    into the child that retains most of the parent's text.
    """

    soup = BeautifulSoup(html or "", "html.parser")
    for selector in _CHROME_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    root = soup.body or soup
    best = root
    best_len = len(_clean(root.get_text(" ", strip=True)))

    if best_len < min_chars:
        return root

    changed = True
    while changed:
        changed = False
        for child in best.find_all(["div", "section", "article"], recursive=False):
            child_len = len(_clean(child.get_text(" ", strip=True)))
            if child_len >= best_len * 0.6 and child_len >= min_chars:
                best, best_len = child, child_len
                changed = True
                break

    return best


def parse_job_detail(html: str) -> dict:
    """Extract the description from a Stellenwerk detail page."""

    block = densest_content_block(html)
    text = _clean(block.get_text(" ", strip=True))
    if not text:
        return {}
    return {"description": text[:4000]}
