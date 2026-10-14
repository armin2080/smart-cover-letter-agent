"""Deterministic sample listings.

This provider exists so the seed command and the automated test suite can
exercise the full pipeline without performing any third-party access. It is
**not** a job source: it contacts nothing and its listings are synthetic.

Live collection lives in `jobs/sources/` behind the authorization gate.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.utils import timezone

from jobs.sources.base import EmploymentType, RawJob, SearchRequest

SOURCE_NAME = "Sample data"

# Skills and requirements per professional domain, so a generated listing is
# internally coherent (a "Backend Engineer" post never advertises Figma).
_DOMAIN_SKILLS: dict[str, list[str]] = {
    "design": ["Figma", "Design systems", "User research", "Prototyping"],
    "frontend": ["React", "TypeScript", "CSS", "Accessibility"],
    "engineering": ["Python", "Django", "PostgreSQL", "Docker", "REST"],
    "data": ["SQL", "Python", "pandas", "Tableau"],
    "product": ["Roadmapping", "Analytics", "Discovery", "Stakeholder management"],
    "marketing": ["SEO", "Campaigns", "Analytics", "Content"],
    "generic": ["Communication", "Planning", "Documentation"],
}

_ADJACENT_DOMAIN = {
    "design": "product", "frontend": "design", "engineering": "data",
    "data": "engineering", "product": "design", "marketing": "generic",
    "generic": "product",
}

_DOMAIN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("design", ("design", "ux", "ui", "creative", "graphic")),
    ("frontend", ("frontend", "front-end", "react", "web", "javascript")),
    ("data", ("data", "analyst", "analytics", "scientist", "statistic")),
    ("engineering", ("engineer", "developer", "backend", "software", "devops")),
    ("product", ("product", "project", "programme", "scrum", "delivery")),
    ("marketing", ("market", "growth", "seo", "content", "brand")),
)

#: (title template, company, employment type, tier)
_TIERS: tuple[tuple[str, str, EmploymentType, str], ...] = (
    ("Senior {role}", "Northstar Labs", EmploymentType.FULL_TIME, "close"),
    ("{role}", "Morrow", EmploymentType.FULL_TIME, "close"),
    ("{role} (Werkstudent)", "Aperture Software", EmploymentType.WORKING_STUDENT, "close"),
    ("{role} — Growth", "Ledgerly", EmploymentType.FULL_TIME, "partial"),
    ("{role} (Working Student)", "Halcyon Studio", EmploymentType.WORKING_STUDENT, "partial"),
    ("Praktikum {role}", "Cobalt Analytics", EmploymentType.INTERNSHIP, "partial"),
)

_UNRELATED: tuple[tuple[str, str, EmploymentType, str], ...] = (
    ("Clinical Data Analyst", "Orbit Health", EmploymentType.FULL_TIME, "data"),
    ("Field Marketing Manager", "Brightpath", EmploymentType.FULL_TIME, "marketing"),
    ("Logistics Coordinator", "Nordlog", EmploymentType.PART_TIME, "generic"),
)

#: Employment hint text the classifier reads, mirroring what real cards carry.
_HINTS = {
    EmploymentType.WORKING_STUDENT: "Werkstudentenstelle",
    EmploymentType.INTERNSHIP: "Praktikum",
    EmploymentType.STUDENT_ASSISTANT: "Studentische Hilfskraft",
    EmploymentType.PART_TIME: "Teilzeit",
    EmploymentType.FULL_TIME: "Vollzeit",
}


def _detect_domain(role: str) -> str:
    lowered = (role or "").lower()
    for domain, hints in _DOMAIN_HINTS:
        if any(hint in lowered for hint in hints):
            return domain
    return "generic"


def _format_title(template: str, role: str) -> str:
    role = role.strip()
    if template.startswith("Senior ") and "senior" in role.lower():
        return role
    return template.format(role=role)


def _tier_skills(tier: str, domain: str) -> list[str]:
    primary = _DOMAIN_SKILLS.get(domain, _DOMAIN_SKILLS["generic"])
    adjacent = _DOMAIN_SKILLS.get(_ADJACENT_DOMAIN.get(domain, "generic"), _DOMAIN_SKILLS["generic"])
    if tier == "close":
        return list(primary)
    if tier == "partial":
        return [*primary[:1], *adjacent[:2]]
    return list(primary)


def generate_sample_jobs(
    keywords: list[str] | None = None,
    locations: list[str] | None = None,
    limit: int = 40,
) -> list[RawJob]:
    """Produce deterministic synthetic listings."""

    roles = [role for role in (keywords or []) if role.strip()] or ["Product Designer"]
    places = [place for place in (locations or []) if place.strip()] or ["Berlin"]

    jobs: list[RawJob] = []
    index = 0

    for role in roles[:3]:
        domain = _detect_domain(role)

        for template, company, employment, tier in _TIERS:
            title = _format_title(template, role)
            skills = _tier_skills(tier, domain)
            digest = hashlib.sha1(f"{role}|{company}|{index}".encode()).hexdigest()[:10]

            jobs.append(
                RawJob(
                    source=SOURCE_NAME,
                    external_id=f"sample-{digest}",
                    title=title,
                    company=company,
                    location=places[index % len(places)],
                    url=f"https://example.invalid/sample/{digest}",
                    description=(
                        f"{company} is hiring a {title}. "
                        f"Required skills: {', '.join(skills)}. "
                        "This is synthetic sample data used for development and testing."
                    ),
                    employment_type_raw=_HINTS.get(employment, ""),
                    posted_at_raw=(timezone.now() - timedelta(hours=(index + 1) * 7)).isoformat(),
                    payload={"sample": True, "tier": tier, "domain": domain},
                )
            )
            index += 1
            if len(jobs) >= limit:
                return jobs

        for title, company, employment, other_domain in _UNRELATED[: 1 if index % 3 else 2]:
            digest = hashlib.sha1(f"{title}|{company}|{index}".encode()).hexdigest()[:10]
            skills = _DOMAIN_SKILLS.get(other_domain, _DOMAIN_SKILLS["generic"])
            jobs.append(
                RawJob(
                    source=SOURCE_NAME,
                    external_id=f"sample-{digest}",
                    title=title,
                    company=company,
                    location=places[index % len(places)],
                    url=f"https://example.invalid/sample/{digest}",
                    description=f"{company} is hiring a {title}. Skills: {', '.join(skills)}.",
                    employment_type_raw=_HINTS.get(employment, ""),
                    posted_at_raw=(timezone.now() - timedelta(hours=(index + 1) * 9)).isoformat(),
                    payload={"sample": True, "domain": other_domain},
                )
            )
            index += 1
            if len(jobs) >= limit:
                return jobs

    return jobs


class SampleJobProvider:
    """Adapter-shaped wrapper so the sample path flows through the pipeline."""

    name = "sample"
    display_name = "Sample data"

    def fetch(self, request: SearchRequest) -> list[RawJob]:
        return generate_sample_jobs(
            keywords=request.keywords,
            locations=request.locations,
            limit=request.max_results or 40,
        )
