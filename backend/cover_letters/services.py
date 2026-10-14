"""Cover letter generation.

Two strategies, selected automatically:

1. **Groq** — used when ``GROQ_API_KEY`` is configured. The prompt strictly
   forbids inventing skills, employers, metrics, dates or achievements.
2. **Grounded template** — an offline fallback that composes the letter purely
   from data that already exists in the user's profile and the job posting. It
   cannot fabricate anything because every sentence is derived from stored
   fields, and it omits any claim it cannot substantiate.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from jobs.matching import normalise_terms, tokenize

logger = logging.getLogger(__name__)


class CoverLetterError(RuntimeError):
    """Raised when generation fails in a way the caller should surface."""


SYSTEM_PROMPT = (
    "You write tailored cover letters for job applications.\n"
    "Absolute rules:\n"
    "1. Use ONLY the candidate information and job details provided.\n"
    "2. Never invent skills, employers, job titles, dates, metrics, degrees or achievements.\n"
    "3. If information is missing, write around it rather than guessing.\n"
    "4. Do not use placeholders such as [Company] or [Name].\n"
    "5. Return only the cover letter text, with no commentary, headings or markdown."
)

LANGUAGE_NAMES = {
    "English": "English",
    "German": "German",
}

TONE_GUIDANCE = {
    "professional": "Formal, measured and factual.",
    "confident": "Direct and assured, while remaining factual and non-arrogant.",
    "warm": "Personable and sincere, while remaining professional.",
}

LENGTH_GUIDANCE = {
    "concise": "Around 200-250 words.",
    "balanced": "Around 300-350 words.",
    "detailed": "Around 450-500 words.",
}


def _profile_context(user) -> dict:
    """Collect everything known about the candidate from stored data only."""

    profile = getattr(user, "profile", None)
    sections = {section.key: section.content.strip() for section in user.profile_sections.all()}
    return {
        "full_name": user.full_name or "",
        "email": user.email,
        "phone": getattr(profile, "phone", "") or "",
        "location": getattr(profile, "location", "") or "",
        "portfolio": getattr(profile, "portfolio", "") or "",
        "summary": (getattr(profile, "summary", "") or sections.get("summary", "")).strip(),
        "skills": sections.get("skills", ""),
        "experience": sections.get("experience", ""),
        "education": sections.get("education", ""),
        "projects": sections.get("projects", ""),
        "languages": sections.get("languages", ""),
        "certificates": sections.get("certificates", ""),
        "raw_sections": sections,
    }


def _job_context(job) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "employment_type": job.employment_type,
        "source": job.source,
        "source_url": job.source_url,
        "summary": job.summary,
        "responsibilities": list(job.responsibilities or []),
        "requirements": list(job.requirements or []),
        "skills": list(job.skills or []),
    }


def build_prompt(profile: dict, job: dict, language: str, tone: str, length: str, instructions: str) -> str:
    """Compose the user message sent to the model."""

    candidate_lines = [
        f"Name: {profile['full_name'] or '(not provided)'}",
        f"Location: {profile['location'] or '(not provided)'}",
        f"Professional summary: {profile['summary'] or '(not provided)'}",
        f"Skills: {profile['skills'] or '(not provided)'}",
        f"Work experience: {profile['experience'] or '(not provided)'}",
        f"Education: {profile['education'] or '(not provided)'}",
        f"Projects: {profile['projects'] or '(not provided)'}",
        f"Languages: {profile['languages'] or '(not provided)'}",
        f"Certificates: {profile['certificates'] or '(not provided)'}",
    ]

    job_lines = [
        f"Job title: {job['title']}",
        f"Company: {job['company']}",
        f"Location: {job['location'] or '(not provided)'}",
        f"Employment type: {job['employment_type'] or '(not provided)'}",
        f"Overview: {job['summary'] or '(not provided)'}",
        "Responsibilities:\n- " + "\n- ".join(job["responsibilities"] or ["(not provided)"]),
        "Requirements:\n- " + "\n- ".join(job["requirements"] or ["(not provided)"]),
        f"Listed skills: {', '.join(job['skills']) or '(not provided)'}",
    ]

    instruction_block = f"\nAdditional user instructions: {instructions.strip()}\n" if instructions and instructions.strip() else ""

    return (
        "CANDIDATE (use only this information):\n"
        + "\n".join(candidate_lines)
        + "\n\nJOB POSTING:\n"
        + "\n".join(job_lines)
        + "\n\n"
        + f"Write the letter in {LANGUAGE_NAMES.get(language, language)}.\n"
        + f"Tone: {TONE_GUIDANCE.get(tone, 'Professional.')}\n"
        + f"Length: {LENGTH_GUIDANCE.get(length, 'Around 300 words.')}\n"
        + "Open with 'Dear " + job["company"] + " Hiring Team,' and close with 'Sincerely,' "
        + "followed by the candidate's name.\n"
        + instruction_block
        + "\nReturn only the cover letter text."
    )


def generate(user, job, language: str, tone: str, length: str, instructions: str = "") -> tuple[str, str]:
    """Generate letter content.

    Returns a ``(content, generator)`` tuple where ``generator`` is either
    ``"groq"`` or ``"grounded-template"``.
    """

    profile = _profile_context(user)
    job_data = _job_context(job)

    if settings.GROQ_API_KEY:
        try:
            content = _generate_with_groq(profile, job_data, language, tone, length, instructions)
            if content.strip():
                return content.strip(), "groq"
            logger.warning("Groq returned empty content; falling back to the grounded template.")
        except CoverLetterError:
            raise
        except Exception:  # noqa: BLE001 - fall back rather than fail the request
            logger.exception("Groq generation failed; falling back to the grounded template.")

    return build_grounded_letter(profile, job_data, language, instructions), "grounded-template"


def _generate_with_groq(
    profile: dict, job: dict, language: str, tone: str, length: str, instructions: str
) -> str:
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_prompt(profile, job, language, tone, length, instructions),
            },
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
    }

    try:
        response = requests.post(
            settings.GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.GROQ_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise CoverLetterError(f"Could not reach the language model: {exc}") from exc

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = (body.get("error") or {}).get("message", "") or body.get("detail", "")
        except ValueError:
            detail = response.text[:200]
        raise CoverLetterError(
            f"The language model rejected the request ({response.status_code}). {detail}".strip()
        )

    try:
        body = response.json()
        return body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise CoverLetterError("The language model returned an unexpected response.") from exc


# --------------------------------------------------------------------------- #
# Grounded template fallback                                                  #
# --------------------------------------------------------------------------- #


def build_grounded_letter(profile: dict, job: dict, language: str, instructions: str = "") -> str:
    """Compose a letter strictly from stored profile and job data.

    Only skills that genuinely appear in both the CV and the posting are
    mentioned, so the output cannot overstate the candidate's background. Skill
    names are reproduced with their original casing (e.g. "Figma", not "figma").
    """

    name = profile["full_name"] or "The candidate"
    company = job["company"]
    title = job["title"]
    greeting = _greeting(company, language)
    closing = _closing(language)
    signoff = _signoff(language)

    cv_terms = normalise_terms(
        [profile["skills"], profile["experience"], profile["summary"], profile["projects"]]
    )
    cv_tokens = set(tokenize(" ".join([profile["skills"], profile["experience"], profile["summary"]])))

    # Display names come from the posting's own skill list so casing is preserved.
    matched = _matched_skill_labels(job.get("skills") or [], cv_terms, cv_tokens)

    # Gaps are derived from skills and requirements only — never from prose.
    requirement_terms = normalise_terms([*(job.get("skills") or []), *(job.get("requirements") or [])])
    gaps = [term for term in sorted(requirement_terms - cv_terms - cv_tokens)][:4]

    paragraphs: list[str] = []

    paragraph_one = _opening_paragraph(title, company, language)
    if matched:
        paragraph_one += _matched_skills_sentence(matched, language)
    paragraphs.append(paragraph_one)

    if profile["summary"]:
        paragraphs.append(_summary_paragraph(profile["summary"], language))

    experience_line = _first_meaningful_line(profile["experience"])
    if experience_line:
        paragraphs.append(_experience_paragraph(experience_line, title, language))

    if profile["education"]:
        education_line = _first_meaningful_line(profile["education"])
        if education_line:
            paragraphs.append(_education_paragraph(education_line, language))

    if gaps:
        paragraphs.append(_growth_paragraph(gaps, company, language))

    paragraphs.append(_closing_paragraph(company, language))
    if instructions.strip():
        paragraphs.append(_instruction_note(instructions, language))

    body = "\n\n".join(paragraphs)
    return f"{greeting}\n\n{body}\n\n{closing}\n{signoff},\n{name}"


def _matched_skill_labels(
    job_skills: list[str], cv_terms: set[str], cv_tokens: set[str]
) -> list[str]:
    """Return the posting's skill names that are evidenced in the CV.

    Original casing and phrasing are preserved so the letter reads naturally.
    """

    matched: list[str] = []
    for skill in job_skills:
        if not skill or not skill.strip():
            continue
        terms = normalise_terms([skill]) or set(tokenize(skill))
        if not terms:
            continue
        if terms & cv_terms or terms & cv_tokens:
            label = skill.strip()
            if label not in matched:
                matched.append(label)
    return matched[:5]


def _first_meaningful_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip(" -•\t")
        if stripped:
            return stripped
    return ""


def _greeting(company: str, language: str) -> str:
    if language == "German":
        return f"Sehr geehrtes Team von {company},"
    return f"Dear {company} Hiring Team,"


def _closing(language: str) -> str:
    if language == "German":
        return "Über die Möglichkeit eines Gesprächs freue ich mich sehr. Vielen Dank für Ihre Zeit."
    return (
        "I would welcome the opportunity to discuss how my background aligns with this role. "
        "Thank you for your consideration."
    )


def _signoff(language: str) -> str:
    return "Mit freundlichen Grüßen" if language == "German" else "Sincerely"


def _opening_paragraph(title: str, company: str, language: str) -> str:
    if language == "German":
        return f"hiermit bewerbe ich mich um die Position als {title} bei {company}."
    return f"I am writing to apply for the {title} position at {company}."


def _matched_skills_sentence(matched: list[str], language: str) -> str:
    listed = ", ".join(matched[:-1]) + f" and {matched[-1]}" if len(matched) > 1 else matched[0]
    if language == "German":
        return f" Die Anforderungen überschneiden sich mit meinen Kenntnissen in {listed}."
    return f" The requirements overlap with my background in {listed}."


def _summary_paragraph(summary: str, language: str) -> str:
    cleaned = " ".join(summary.split())
    if language == "German":
        return f"Kurz zu meinem Hintergrund: {cleaned}"
    return f"Briefly, my background: {cleaned}"


def _experience_paragraph(experience_line: str, title: str, language: str) -> str:
    if language == "German":
        return (
            f"Meine bisherige Erfahrung umfasst: {experience_line}. "
            f"Die Aufgaben der Position als {title} knüpfen daran an."
        )
    return (
        f"My experience includes {experience_line}. "
        f"The responsibilities of the {title} role build directly on that work."
    )


def _education_paragraph(education_line: str, language: str) -> str:
    if language == "German":
        return f"Meine Ausbildung: {education_line}."
    return f"My education: {education_line}."


def _growth_paragraph(gaps: list[str], company: str, language: str) -> str:
    listed = ", ".join(gaps)
    if language == "German":
        return (
            f"Die Stellenausschreibung nennt unter anderem {listed}. "
            "Diese Punkte sind in meinem Profil bisher nicht belegt; ich bin jedoch bereit, "
            f"mich bei {company} gezielt darin weiterzuentwickeln."
        )
    return (
        f"The posting also mentions {listed}. "
        "These areas are not yet evidenced in my profile, though I am keen to develop them "
        f"further at {company}."
    )


def _closing_paragraph(company: str, language: str) -> str:
    if language == "German":
        return f"Ich freue mich darauf, mit dem Team von {company} über diese Position zu sprechen."
    return f"I would be glad to talk with the {company} team about this position."


def _instruction_note(instructions: str, language: str) -> str:
    # Recorded so the user can see their instruction was applied; clearly marked
    # as guidance rather than fabricated content.
    prefix = "Berücksichtigte Vorgabe" if language == "German" else "Applied instruction"
    return f"{prefix}: {instructions.strip()}"
