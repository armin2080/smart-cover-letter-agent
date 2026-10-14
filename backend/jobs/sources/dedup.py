"""Cross-source deduplication.

The same opening frequently appears on several boards. Merging duplicates keeps
the UI honest, but **over-merging is worse than under-merging**: showing one card
for two genuinely different jobs loses opportunities the user would otherwise
have seen.

Strategy, in decreasing order of confidence:

1. **Canonical URL** — the strongest signal. Tracking parameters are stripped
   first, so the same posting reached via two links collapses.
2. **Source + external id** — authoritative within a single source.
3. **Normalised title + company + location** — catches re-posts across boards.
4. **Conservative fuzzy title match** — only within the same company *and*
   location, and only above a high similarity threshold.

Two jobs are never merged on title alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from jobs.sources.base import NormalizedJob

#: Query parameters that identify a campaign or session, not a posting.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "refid", "referrer", "trackingid", "position", "pagenum",
    "rltr", "trk", "trkemail", "originalreferer", "ebs", "src",
}

#: Fuzzy title similarity required to merge (only ever combined with an exact
#: company *and* location match).
FUZZY_THRESHOLD = 0.93


def canonical_url(url: str) -> str:
    """Normalise a URL for comparison.

    Strips tracking parameters, the fragment, a trailing slash and the `www.`
    prefix so equivalent links compare equal.
    """

    if not url:
        return ""

    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def normalize_title(title: str) -> str:
    """Reduce a title to comparable form.

    Removes gender markers, employment-type decorations and punctuation, which
    vary between boards for the same opening.
    """

    text = (title or "").lower()
    text = re.sub(r"\((?:m|w|f|d|gn|m/w/d|w/m/d|m/w/x|all genders?)\)", " ", text)
    text = re.sub(r"\b(?:m/w/d|w/m/d|m/f/d|all genders|gn)\b", " ", text)
    text = re.sub(r"\b(?:werkstudent(?:in)?|working student|praktikant(?:in)?|intern)\b", " ", text)
    text = re.sub(r"\b(?:teilzeit|vollzeit|part[\s\-]?time|full[\s\-]?time)\b", " ", text)
    text = re.sub(r"[^\wäöüß]+", " ", text)
    return " ".join(text.split())


def normalize_company(company: str) -> str:
    """Strip common legal suffixes so "Acme GmbH" and "Acme" match."""

    text = (company or "").lower()
    text = re.sub(
        r"\b(?:gmbh|ag|kg|kgaa|ohg|gbr|se|ug|mbh|inc|ltd|llc|corp|co\.?|e\.?\s?v\.?)\b",
        " ",
        text,
    )
    text = re.sub(r"[^\wäöüß]+", " ", text)
    return " ".join(text.split())


def title_similarity(left: str, right: str) -> float:
    """Similarity of two already-normalised titles."""

    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


# --------------------------------------------------------------------------- #
# Grouping                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class DeduplicatedJob:
    """A single logical job, with every source that advertised it."""

    primary: NormalizedJob
    #: Additional representations merged into this one.
    duplicates: list[NormalizedJob] = field(default_factory=list)
    #: Which rule produced the merge, for auditing.
    matched_by: str = "unique"

    @property
    def sources(self) -> list[str]:
        return sorted({self.primary.source, *(dup.source for dup in self.duplicates)})

    @property
    def source_urls(self) -> list[str]:
        return [self.primary.source_url, *(dup.source_url for dup in self.duplicates)]

    def as_provenance(self) -> list[dict]:
        """Per-source provenance, so the origin of each record stays visible."""

        entries = [
            {
                "source": self.primary.source,
                "url": self.primary.source_url,
                "external_id": self.primary.external_id,
            }
        ]
        entries.extend(
            {"source": dup.source, "url": dup.source_url, "external_id": dup.external_id}
            for dup in self.duplicates
        )
        return entries


def _merge_quality(existing: NormalizedJob, candidate: NormalizedJob) -> NormalizedJob:
    """Prefer whichever record carries more useful information.

    Descriptions and skills materially improve matching, so a record that has
    them wins over one that does not, regardless of arrival order.
    """

    def richness(job: NormalizedJob) -> tuple:
        return (
            len(job.description or ""),
            len(job.required_skills or []),
            len(job.location or ""),
        )

    return candidate if richness(candidate) > richness(existing) else existing


def deduplicate(jobs: list[NormalizedJob]) -> list[DeduplicatedJob]:
    """Group duplicate listings while preserving provenance."""

    groups: list[DeduplicatedJob] = []

    by_url: dict[str, DeduplicatedJob] = {}
    by_external: dict[tuple[str, str], DeduplicatedJob] = {}
    by_fingerprint: dict[tuple[str, str, str], DeduplicatedJob] = {}

    for job in jobs:
        if not job.is_valid:
            continue

        url_key = canonical_url(job.source_url)
        external_key = (job.source, job.external_id) if job.external_id else None
        fingerprint = (
            normalize_title(job.title),
            normalize_company(job.company),
            (job.city or job.location or "").lower().strip(),
        )

        target: DeduplicatedJob | None = None
        matched_by = "unique"

        if url_key and url_key in by_url:
            target, matched_by = by_url[url_key], "canonical-url"

        if target is None and external_key and external_key in by_external:
            target, matched_by = by_external[external_key], "source-external-id"

        if target is None and all(fingerprint):
            existing = by_fingerprint.get(fingerprint)
            if existing is not None:
                target, matched_by = existing, "title-company-location"

        if target is None:
            # Conservative fuzzy pass: same company AND same location, very
            # similar title. Never merges on title alone.
            company_key = normalize_company(job.company)
            city_key = (job.city or job.location or "").lower().strip()
            title_key = normalize_title(job.title)

            if company_key and city_key and title_key:
                for group in groups:
                    other = group.primary
                    if normalize_company(other.company) != company_key:
                        continue
                    if (other.city or other.location or "").lower().strip() != city_key:
                        continue
                    if title_similarity(normalize_title(other.title), title_key) >= FUZZY_THRESHOLD:
                        target, matched_by = group, "fuzzy-title"
                        break

        if target is None:
            group = DeduplicatedJob(primary=job, matched_by="unique")
            groups.append(group)
            target = group
        else:
            target.primary = _merge_quality(target.primary, job)
            target.duplicates.append(job)
            target.matched_by = matched_by

        if url_key:
            by_url.setdefault(url_key, target)
        if external_key:
            by_external.setdefault(external_key, target)
        if all(fingerprint):
            by_fingerprint.setdefault(fingerprint, target)

    return groups
