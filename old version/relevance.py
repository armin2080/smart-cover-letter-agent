import re


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "you", "your", "our",
    "are", "was", "were", "will", "would", "could", "should", "about", "into",
    "over", "under", "between", "within", "also", "than", "then", "have", "has",
    "had", "not", "but", "can", "may", "job", "jobs", "work", "working", "role",
    "position", "company", "team", "based", "required", "requirements", "responsible",
    "responsibilities", "student", "students", "experience", "skills", "education",
    "language", "languages", "project", "projects", "certificate", "certificates",
    "degree", "year", "years", "time", "full", "part", "time", "remote", "hybrid",
}


RELEVANT_SECTION_HEADINGS = {
    "contact", "skills", "education", "languages", "work experience", "projects", "certificates"
}


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower())


def _add_tokens(bucket: set[str], text: str):
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", text.lower()):
        token = token.strip(".-_+")
        if token and token not in STOPWORDS:
            bucket.add(token)


def extract_resume_terms(resume_text: str) -> tuple[set[str], set[str]]:
    strong_terms: set[str] = set()
    broad_terms: set[str] = set()
    current_section = ""

    for raw_line in (resume_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lower = line.lower()
        if lower in RELEVANT_SECTION_HEADINGS:
            current_section = lower
            continue

        if current_section == "skills":
            for part in re.split(r"[,;/•|\-]", line):
                cleaned = normalize_text(part).strip()
                if cleaned:
                    strong_terms.add(cleaned)

        _add_tokens(broad_terms, line)

    return strong_terms, broad_terms


def job_matches_resume(job_text: str, resume_text: str, min_broad_matches: int = 1) -> bool:
    if not resume_text:
        return True

    job_norm = normalize_text(job_text)
    strong_terms, broad_terms = extract_resume_terms(resume_text)

    for term in strong_terms:
        if len(term) >= 3 and term in job_norm:
            return True

    matches = sum(1 for term in broad_terms if len(term) >= 4 and term in job_norm)
    return matches >= min_broad_matches