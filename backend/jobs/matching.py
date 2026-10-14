"""Explainable job matching.

The matching engine is deliberately rule-based and inspectable: every verdict is
backed by individual `MatchLine` entries the UI renders as plain language. No
opaque score is ever exposed — only the qualitative categories
``strong`` / ``good`` / ``potential``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from jobs.sources.normalization import extract_skills

STOPWORDS = {
    "and", "or", "the", "a", "an", "for", "with", "of", "to", "in", "on", "at",
    "is", "are", "be", "as", "by", "from", "that", "this", "you", "your", "we",
    "our", "will", "have", "has", "experience", "years", "work", "working",
    "role", "job", "team", "teams", "using", "strong", "good", "plus",
}

# Tokens that carry no discriminating power for a skill comparison.
GENERIC_TERMS = {"design", "developer", "engineer", "manager", "product", "software", "senior", "junior"}


@dataclass(frozen=True)
class MatchLine:
    positive: bool
    title: str
    detail: str

    def as_dict(self) -> dict:
        return {"positive": self.positive, "title": self.title, "detail": self.detail}


@dataclass(frozen=True)
class Insight:
    """The complete explainable verdict for one job/user pair."""

    match: str
    cv_alignment: list[MatchLine]
    preference_fit: list[MatchLine]
    score: float

    @property
    def cv_dicts(self) -> list[dict]:
        return [line.as_dict() for line in self.cv_alignment]

    @property
    def preference_dicts(self) -> list[dict]:
        return [line.as_dict() for line in self.preference_fit]


# --------------------------------------------------------------------------- #
# Text helpers                                                                #
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def tokenize(text: str | None) -> list[str]:
    """Lower-case word tokens with stopwords removed."""

    if not text:
        return []
    return [
        token.lower().strip(".-+#")
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in STOPWORDS and len(token) > 1
    ]


def normalise_terms(values: Iterable[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for token in tokenize(value):
            if token and token not in GENERIC_TERMS:
                terms.add(token)
    return terms


def _display_labels(job_skills: Iterable[str], matched_terms: set[str]) -> list[str]:
    """Return original-cased skill labels for terms that matched.

    Matching operates on normalised tokens, but the UI must show the posting's
    own wording (e.g. "Design systems", not "systems").
    """

    labels: list[str] = []
    for skill in job_skills:
        if not skill or not skill.strip():
            continue
        terms = normalise_terms([skill]) or set(tokenize(skill))
        if terms & matched_terms:
            label = skill.strip()
            if label not in labels:
                labels.append(label)
    return labels


def _titles_overlap(candidate: str, targets: Iterable[str]) -> str | None:
    """Return the first target title that meaningfully overlaps with `candidate`."""

    candidate_tokens = set(tokenize(candidate))
    if not candidate_tokens:
        return None
    for target in targets:
        target_tokens = set(tokenize(target))
        if not target_tokens:
            continue
        if target_tokens <= candidate_tokens or candidate_tokens <= target_tokens:
            return target
    return None


def _location_matches(job_location: str, locations: Iterable[str]) -> str | None:
    lowered = (job_location or "").lower()
    if not lowered:
        return None
    for location in locations:
        needle = location.lower().strip()
        if not needle:
            continue
        if needle in lowered or lowered in needle:
            return location
        # "Remote (Germany)" should match a listing that only says "Remote".
        primary = needle.split("(")[0].strip()
        if primary and primary in lowered:
            return location
    if "remote" in lowered:
        for location in locations:
            if "remote" in location.lower():
                return location
    return None


# --------------------------------------------------------------------------- #
# Engine                                                                      #
# --------------------------------------------------------------------------- #


def build_insight(
    *,
    job_title: str,
    company: str,
    location: str,
    employment_type: str,
    source: str,
    job_skills: Iterable[str],
    job_requirements: Iterable[str],
    job_summary: str = "",
    desired_roles: Iterable[str],
    preferred_locations: Iterable[str],
    employment_types: Iterable[str],
    preferred_sources: Iterable[str],
    keywords: Iterable[str],
    profile_sections: dict[str, str],
    profile_summary: str = "",
) -> Insight:
    """Compare one job against a user's CV qualifications and preferences."""

    cv_lines: list[MatchLine] = []
    pref_lines: list[MatchLine] = []

    # ------------------------------------------------------------------ CV --
    cv_text = " ".join(
        [
            profile_summary or "",
            profile_sections.get("summary", ""),
            profile_sections.get("skills", ""),
            profile_sections.get("experience", ""),
            profile_sections.get("projects", ""),
            profile_sections.get("certificates", ""),
            profile_sections.get("education", ""),
        ]
    )
    cv_skills = normalise_terms([profile_sections.get("skills", "")])
    cv_tokens = set(tokenize(cv_text))

    # Canonicalise the CV through the same extractor used on postings, so both
    # sides speak one vocabulary. The extractor maps every language and spelling
    # to a single label ("Softwareentwicklung" and "software development" both
    # become "Software development"). Comparing raw tokens instead made a
    # German CV unable to match an identically-meaning posting, because the
    # label's English tokens never appear in German prose.
    cv_skill_labels = set(extract_skills(cv_text))
    job_skill_labels = {label for label in job_skills if label and label.strip()}
    label_matches = job_skill_labels & cv_skill_labels

    # Skills and requirements drive matching *and* gap detection.
    requirement_terms = normalise_terms([*job_skills, *job_requirements])
    # Free-text prose broadens matching but must never be reported as a missing
    # requirement — describing a role in a sentence is not a criterion.
    match_terms = requirement_terms | normalise_terms([job_summary])

    matched_skills = sorted(requirement_terms & cv_skills)
    if not matched_skills:
        # Fall back to any CV token overlap so we still explain partial matches.
        matched_skills = sorted((match_terms & cv_tokens) - GENERIC_TERMS)[:6]

    if matched_skills or label_matches:
        # Prefer the posting's own wording for readability.
        if matched_skills:
            labels = _display_labels(job_skills, set(matched_skills)) or matched_skills
            count = len(matched_skills)
        else:
            labels = sorted(label_matches)
            count = len(label_matches)
        shown = ", ".join(labels[:5])
        cv_lines.append(
            MatchLine(
                True,
                f"{count} requirement{'s' if count != 1 else ''} found in your CV",
                f"Matching: {shown}.",
            )
        )
    else:
        cv_lines.append(
            MatchLine(
                False,
                "No direct skill overlap found",
                "None of the listed requirements appear in your CV — consider adding relevant skills.",
            )
        )

    # A skill that matched by canonical label must not also be reported as
    # missing. Its tokens are not in the CV verbatim ("Software development"
    # never appears in a German CV), but the skill demonstrably does. Without
    # this the UI told users they were missing requirements they actually had.
    covered = set()
    for label in label_matches:
        covered |= normalise_terms([label]) | set(tokenize(label))

    missing = sorted(requirement_terms - cv_skills - cv_tokens - covered)[:5]
    if missing:
        cv_lines.append(
            MatchLine(
                False,
                f"{len(missing)} requirement{'s' if len(missing) != 1 else ''} not evidenced",
                f"Not found in your CV: {', '.join(missing)}.",
            )
        )

    # Experience / seniority signal.
    experience_text = profile_sections.get("experience", "")
    experience_years = _extract_years(experience_text) or _extract_years(cv_text)
    required_years = _extract_years(" ".join(job_requirements)) or _extract_years(job_summary)
    if required_years:
        if experience_years and experience_years >= required_years:
            cv_lines.append(
                MatchLine(
                    True,
                    f"Meets the {required_years}+ year expectation",
                    f"Your CV indicates around {experience_years} years of experience.",
                )
            )
        elif experience_years:
            cv_lines.append(
                MatchLine(
                    False,
                    f"Below the {required_years}+ year expectation",
                    f"Your CV indicates around {experience_years} years of experience.",
                )
            )
        else:
            cv_lines.append(
                MatchLine(
                    False,
                    f"Requires {required_years}+ years of experience",
                    "Your CV does not state a total duration of experience.",
                )
            )

    # Education signal.
    education_text = profile_sections.get("education", "")
    if education_text.strip():
        cv_lines.append(
            MatchLine(
                True,
                "Education on file",
                _first_line(education_text, fallback="Your CV includes an education section."),
            )
        )
    elif any("degree" in term or "bachelor" in term or "master" in term for term in requirement_terms):
        cv_lines.append(
            MatchLine(
                False,
                "Degree requested",
                "The posting mentions a degree, but your CV has no education section.",
            )
        )

    # ---------------------------------------------------------- Preferences --
    role_hit = _titles_overlap(job_title, desired_roles)
    if role_hit:
        pref_lines.append(
            MatchLine(True, "Matches a target role", f"“{role_hit}” is one of your desired job titles.")
        )
    elif list(desired_roles):
        pref_lines.append(
            MatchLine(
                False,
                "Outside your target roles",
                f"Your desired titles are: {', '.join(list(desired_roles)[:4])}.",
            )
        )

    location_hit = _location_matches(location, preferred_locations)
    if location_hit:
        pref_lines.append(MatchLine(True, "Location is compatible", f"{location} fits “{location_hit}”."))
    elif list(preferred_locations):
        pref_lines.append(
            MatchLine(
                False,
                "Location is outside your preferences",
                f"This role is in {location or 'an unlisted location'}; you preferred "
                f"{', '.join(list(preferred_locations)[:3])}.",
            )
        )

    employment_values = list(employment_types)
    if employment_type:
        if employment_type in employment_values:
            pref_lines.append(
                MatchLine(True, "Employment type matches", f"You are open to {employment_type.replace('-', ' ')} roles.")
            )
        elif employment_values:
            pref_lines.append(
                MatchLine(
                    False,
                    "Different employment type",
                    f"This is a {employment_type.replace('-', ' ')} role; you selected "
                    f"{', '.join(value.replace('-', ' ') for value in employment_values[:3])}.",
                )
            )

    source_values = list(preferred_sources)
    if source:
        if not source_values or source in source_values:
            pref_lines.append(MatchLine(True, "Source is enabled", f"{source} is among your preferred sources."))
        else:
            pref_lines.append(
                MatchLine(False, "Source is not enabled", f"{source} is not in your preferred sources.")
            )

    keyword_values = list(keywords)
    if keyword_values:
        haystack = f"{job_title} {job_summary} {' '.join(job_skills)} {' '.join(job_requirements)}".lower()
        keyword_hits = [keyword for keyword in keyword_values if keyword.lower() in haystack]
        if keyword_hits:
            pref_lines.append(
                MatchLine(True, "Matches your keywords", f"Found: {', '.join(keyword_hits[:4])}.")
            )
        else:
            pref_lines.append(
                MatchLine(False, "No keyword overlap", "None of your saved keywords appear in this posting.")
            )

    # ------------------------------------------------------------- Scoring --
    #
    # `score` is a flat positive ratio used only as a coarse signal.
    # The verdict itself is driven by two things that actually matter:
    #   1. `skill_signal` — how much of the posting's *skill list* is evidenced
    #      in the CV. Requirement prose is excluded because words such as
    #      "working" or "knowledge" are not skills and would dilute the ratio.
    #   2. `pref_ratio`   — how well preferences line up.
    #
    # A role outside the user's domain must never be "strong", no matter how
    # well its location and employment type happen to fit.

    total = len(cv_lines) + len(pref_lines)
    positive = sum(1 for line in cv_lines + pref_lines if line.positive)
    score = (positive / total) if total else 0.0

    pref_positive = sum(1 for line in pref_lines if line.positive)
    pref_ratio = pref_positive / len(pref_lines) if pref_lines else 1.0

    skill_terms = normalise_terms(job_skills) or requirement_terms
    if job_skill_labels:
        # Labelled skills are canonical, so compare label to label. This is the
        # most reliable signal available and is language-independent.
        skill_signal = len(label_matches) / len(job_skill_labels)
    elif skill_terms:
        skill_signal = len(skill_terms & (cv_skills | cv_tokens)) / len(skill_terms)
    else:
        # Nothing to compare against; treat as neutral rather than as a match.
        skill_signal = 0.5 if not cv_skills else 0.0

    if skill_signal >= 0.5 and pref_ratio >= 0.75:
        level = "strong"
    elif skill_signal >= 0.3 or (role_hit and pref_ratio >= 0.5):
        level = "good"
    else:
        level = "potential"

    return Insight(match=level, cv_alignment=cv_lines, preference_fit=pref_lines, score=score)


def _first_line(text: str, fallback: str = "") -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return fallback


_YEAR_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_RANGE_RE = re.compile(r"(\d{4})\s*[-–—]\s*(?:(\d{4})|present|current)", re.IGNORECASE)


def _extract_years(text: str | None) -> int:
    """Best-effort estimate of relevant years of experience."""

    if not text:
        return 0

    explicit = [int(match) for match in _YEAR_RE.findall(text)]
    if explicit:
        return max(explicit)

    # Derive from date ranges such as "2019 - 2022" or "2021 - Present".
    current_year = 2026
    spans = _RANGE_RE.findall(text)
    total = 0
    for start, end in spans:
        start_year = int(start)
        end_year = int(end) if end else current_year
        if 1970 < start_year <= current_year and start_year <= end_year:
            total += end_year - start_year
    return total
