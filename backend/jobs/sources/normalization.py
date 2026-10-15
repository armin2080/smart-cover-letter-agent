"""Normalization: turn a source-specific `RawJob` into a `NormalizedJob`.

Kept separate from parsing so every adapter gets identical treatment for
location parsing, date parsing, employment classification and skill extraction.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from django.utils import timezone

from jobs.sources.base import EmploymentType, NormalizedJob, RawJob, WorkModel
from jobs.sources.classification import classify
from jobs.sources.language import detect_language_profile

# --------------------------------------------------------------------------- #
# Location                                                                    #
# --------------------------------------------------------------------------- #

_GERMAN_STATES = (
    "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg",
    "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen",
    "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt",
    "Schleswig-Holstein", "Thüringen",
)

_STATE_ALIASES = {
    "nrw": "Nordrhein-Westfalen",
    "north rhine-westphalia": "Nordrhein-Westfalen",
    "lower saxony": "Niedersachsen",
    "bavaria": "Bayern",
    "hesse": "Hessen",
    "saxony": "Sachsen",
    "rhineland-palatinate": "Rheinland-Pfalz",
}

_REMOTE_PATTERNS = (
    r"\bhome[\s\-]?office\b",
    r"\bremote\b",
    r"\btelearbeit\b",
    r"\bmobiles?\s+arbeiten\b",
    r"\bwork\s+from\s+home\b",
)

_HYBRID_PATTERNS = (
    r"\bhybrid\b",
    r"\bteilweise\s+home[\s\-]?office\b",
    r"\bmobiles?\s+arbeiten\s+teilweise\b",
)


def parse_location(location: str, *, country_default: str = "Germany") -> dict[str, str]:
    """Split a free-text location into city / region / country.

    Handles the shapes these boards actually produce::

        "Berlin"                          -> city
        "Köln, Nordrhein-Westfalen"       -> city + region
        "Remote (Germany)"                -> remote marker, country
        "Bremen, Köln, Berlin, München"   -> multiple cities (kept as-is)
    """

    result = {"city": "", "region": "", "country": country_default}
    text = (location or "").strip()
    if not text:
        return result

    # Strip a trailing country in parentheses, e.g. "Remote (Germany)".
    country_match = re.search(r"\(([^)]+)\)", text)
    if country_match:
        result["country"] = country_match.group(1).strip()
        text = text[: country_match.start()].strip(" ,·|-") or text

    parts = [part.strip() for part in re.split(r"[,·|]", text) if part.strip()]
    if not parts:
        return result

    # Berlin, Hamburg and Bremen are both cities and federal states. For a job
    # listing the city is the useful reading, so they are handled as cities.
    CITY_STATES = {"berlin", "hamburg", "bremen"}

    remaining: list[str] = []
    for part in parts:
        if part.lower() in CITY_STATES:
            remaining.append(part)
            continue

        canonical_state = next(
            (state for state in _GERMAN_STATES if state.lower() == part.lower()), None
        ) or _STATE_ALIASES.get(part.lower())

        if canonical_state:
            result["region"] = canonical_state
        elif part.lower() in {"deutschland", "germany"}:
            result["country"] = "Germany"
        elif part.lower() in {"österreich", "austria"}:
            result["country"] = "Austria"
        elif part.lower() in {"schweiz", "switzerland"}:
            result["country"] = "Switzerland"
        else:
            remaining.append(part)

    if remaining:
        # Multiple cities are common ("Bremen, Köln, Berlin"); keep them joined so
        # nothing is lost, and use the first as the primary city.
        result["city"] = ", ".join(remaining)

    return result


def detect_work_model(*texts: str) -> WorkModel:
    """Infer on-site / hybrid / remote from listing text."""

    haystack = " ".join(text or "" for text in texts).lower()
    if not haystack.strip():
        return WorkModel.UNKNOWN

    for pattern in _HYBRID_PATTERNS:
        if re.search(pattern, haystack):
            return WorkModel.HYBRID
    for pattern in _REMOTE_PATTERNS:
        if re.search(pattern, haystack):
            return WorkModel.REMOTE
    return WorkModel.ON_SITE


# --------------------------------------------------------------------------- #
# Dates                                                                       #
# --------------------------------------------------------------------------- #

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_GERMAN_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_RELATIVE_RE = re.compile(
    r"(?:vor\s+)?(\d+)\s*(stunde|stunden|tag|tagen|woche|wochen|monat|monaten|hour|hours|day|days|week|weeks|month|months)",
    re.IGNORECASE,
)


def parse_posted_at(value: str | datetime | None) -> datetime | None:
    """Parse an ISO date, a German date, or a relative phrase ("vor 3 Tagen")."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, UTC)

    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"heute", "today", "gerade eben", "just now"}:
        return timezone.now()
    if lowered in {"gestern", "yesterday"}:
        return timezone.now() - timedelta(days=1)

    iso = _ISO_RE.search(text)
    if iso:
        try:
            return timezone.make_aware(
                datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), UTC
            )
        except ValueError:
            pass

    german = _GERMAN_DATE_RE.search(text)
    if german:
        try:
            return timezone.make_aware(
                datetime(int(german.group(3)), int(german.group(2)), int(german.group(1))),
                UTC,
            )
        except ValueError:
            pass

    relative = _RELATIVE_RE.search(lowered)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        if unit.startswith(("stunde", "hour")):
            delta = timedelta(hours=amount)
        elif unit.startswith(("tag", "day")):
            delta = timedelta(days=amount)
        elif unit.startswith(("woche", "week")):
            delta = timedelta(weeks=amount)
        else:
            delta = timedelta(days=amount * 30)
        return timezone.now() - delta

    return None


# --------------------------------------------------------------------------- #
# Skills                                                                      #
# --------------------------------------------------------------------------- #

#: Curated vocabulary. Matching is word-bounded, so short entries such as "R"
#: and "Go" cannot match inside unrelated words.
SKILL_VOCABULARY: dict[str, str] = {
    "python": "Python", "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "javascript": "JavaScript", "typescript": "TypeScript", "react": "React",
    "vue": "Vue", "angular": "Angular", "node.js": "Node.js", "next.js": "Next.js",
    "java": "Java", "kotlin": "Kotlin", "swift": "Swift", "php": "PHP",
    "laravel": "Laravel", "ruby": "Ruby", "golang": "Go", "rust": "Rust",
    "c++": "C++", "c#": "C#", ".net": ".NET",
    "sql": "SQL", "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
    "redis": "Redis", "sqlite": "SQLite", "oracle": "Oracle", "snowflake": "Snowflake",
    "docker": "Docker", "kubernetes": "Kubernetes", "terraform": "Terraform",
    "ansible": "Ansible", "jenkins": "Jenkins", "git": "Git", "linux": "Linux",
    "aws": "AWS", "azure": "Azure", "gcp": "GCP", "rest": "REST", "graphql": "GraphQL",
    "microservices": "Microservices", "api": "API", "ci/cd": "CI/CD",
    "figma": "Figma", "sketch": "Sketch", "adobe xd": "Adobe XD",
    "design systems": "Design systems", "user research": "User research",
    "prototyping": "Prototyping", "accessibility": "Accessibility",
    "wireframes": "Wireframes", "usability": "Usability",
    "machine learning": "Machine learning", "deep learning": "Deep learning",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "pandas": "pandas",
    "numpy": "NumPy", "scikit-learn": "scikit-learn", "nlp": "NLP",
    "tableau": "Tableau", "power bi": "Power BI", "excel": "Excel",
    "etl": "ETL", "data analysis": "Data analysis", "statistics": "Statistics",
    "agile": "Agile", "scrum": "Scrum", "kanban": "Kanban", "jira": "Jira",
    "confluence": "Confluence", "sap": "SAP", "salesforce": "Salesforce",
    "marketing": "Marketing", "seo": "SEO", "sem": "SEM",
    "google analytics": "Google Analytics", "social media": "Social media",
    "german": "German", "english": "English", "french": "French", "spanish": "Spanish",
    "communication": "Communication", "teamwork": "Teamwork",
    "leadership": "Leadership", "project management": "Project management",

    # -- German-language terms -------------------------------------------------
    # The product targets the German market, so a vocabulary that only reads
    # English misses the single most common way these skills are written. A
    # posting titled "Werkstudent Softwareentwicklung" matched nothing before
    # these were added, which left the "strong match" tier unreachable for
    # exactly the roles the product exists to find.
    "softwareentwicklung": "Software development",
    "softwareentwickler": "Software development",
    "anwendungsentwicklung": "Application development",
    "webentwicklung": "Web development",
    "programmierung": "Programming",
    "informatik": "Computer science",
    "wirtschaftsinformatik": "Business informatics",
    "datenbank": "Databases", "datenbanken": "Databases",
    "datenanalyse": "Data analysis", "datenauswertung": "Data analysis",
    "datenverarbeitung": "Data processing",
    "künstliche intelligenz": "Artificial intelligence",
    "maschinelles lernen": "Machine learning",
    "automatisierung": "Automation", "testautomatisierung": "Test automation",
    "softwaretest": "Software testing", "qualitätssicherung": "Quality assurance",
    "it-sicherheit": "IT security", "informationssicherheit": "IT security",
    "datenschutz": "Data protection", "dsgvo": "GDPR",
    "netzwerk": "Networking", "netzwerktechnik": "Networking",
    "virtualisierung": "Virtualisation", "serveradministration": "Server administration",
    "cloud": "Cloud",
    "buchhaltung": "Accounting", "rechnungswesen": "Accounting",
    "controlling": "Controlling", "finanzbuchhaltung": "Accounting",
    "personalwesen": "HR", "personalabteilung": "HR",
    "recruiting": "Recruiting", "vertrieb": "Sales", "einkauf": "Procurement",
    "logistik": "Logistics", "produktion": "Production",
    "maschinenbau": "Mechanical engineering", "elektrotechnik": "Electrical engineering",
    "konstruktion": "Design engineering", "bauwesen": "Civil engineering",
    "hochbau": "Structural engineering", "tiefbau": "Civil engineering",
    "projektleitung": "Project management",
    "kundenbetreuung": "Customer service", "kundenservice": "Customer service",
    "redaktion": "Editorial", "content-erstellung": "Content creation",
}

#: Acronyms whose casing carries the meaning. Matched case-sensitively, because
#: a case-insensitive "it" or "hr" would match ordinary German and English words.
#: The surrounding lookarounds still apply, so "LogProIT" does not register
#: as "IT" — the T is preceded by a word character.
SKILL_ACRONYMS: dict[str, str] = {
    "IT": "IT", "AI": "Artificial intelligence", "KI": "Artificial intelligence",
    "ML": "Machine learning", "BI": "Business intelligence",
    "ERP": "ERP", "CRM": "CRM", "UX": "UX", "UI": "UI",
    "SEO": "SEO", "KPI": "KPIs", "HR": "HR", "CAD": "CAD",
}

_SKILL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"(?<![\w.]){re.escape(key)}(?![\w])", re.IGNORECASE), label)
    for key, label in SKILL_VOCABULARY.items()
) + tuple(
    (re.compile(rf"(?<![\w.]){re.escape(key)}(?![\w])"), label)
    for key, label in SKILL_ACRONYMS.items()
)


def extract_skills(*texts: str, limit: int = 12) -> list[str]:
    """Find recognised skills in the supplied text.

    Word-bounded so that e.g. the German word "der" cannot register as the skill
    "R", and "international" cannot register as "intern".
    """

    haystack = " ".join(text or "" for text in texts)
    if not haystack.strip():
        return []

    found: list[str] = []
    for pattern, label in _SKILL_PATTERNS:
        if pattern.search(haystack):
            found.append(label)
        if len(found) >= limit:
            break
    return found


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def normalize_raw_job(raw: RawJob) -> NormalizedJob:
    """Convert a `RawJob` into the standard representation."""

    from jobs.sources.base import EmploymentType as ET  # local alias for clarity

    location = parse_location(raw.location)

    classification = classify(
        title=raw.title,
        description=raw.description,
        employment_type_hint=raw.employment_type_raw,
    )

    # Language is read from the title and description together: a German title
    # with an English body is common, and the requirement is usually stated in
    # the body regardless of which language the title uses.
    language_profile = detect_language_profile(raw.title, raw.description)

    # If prose gave us nothing but the source supplied a structured type, trust
    # the structured hint instead of leaving the record UNKNOWN.
    if classification.employment_type is ET.UNKNOWN and raw.employment_type_raw:
        classification = classify(employment_type_hint=raw.employment_type_raw)

    work_model = detect_work_model(raw.work_model_raw, raw.title, raw.location, raw.description)

    skills = extract_skills(raw.title, raw.description)

    return NormalizedJob(
        source=raw.source,
        source_url=raw.url,
        title=raw.title,
        company=raw.company,
        external_id=raw.external_id,
        location=raw.location,
        city=location["city"],
        region=location["region"],
        country=location["country"],
        description=raw.description,
        employment_type=classification.employment_type,
        employment_type_confidence=classification.confidence,
        employment_type_evidence=classification.matched_terms,
        employment_type_candidates=list(classification.candidates),
        language=language_profile.language.value,
        language_requirement=language_profile.requirement.value,
        language_evidence=language_profile.evidence,
        work_model=work_model,
        posted_at=parse_posted_at(raw.posted_at_raw),
        collected_at=timezone.now(),
        required_skills=skills,
        keywords=skills[:6],
        raw_source_data=raw.payload,
    )
