"""German/English employment-type classification.

Design goals
------------
1. **Never force a category.** An ambiguous listing stays `UNKNOWN` rather than
   being assigned a type the evidence does not support.
2. **Context matters.** A title match is stronger evidence than the same word
   buried in a long description.
3. **"student" alone is not a working-student job.** Generic student words are
   low-specificity and cannot decide a category on their own.
4. **Explainable.** Every verdict returns the terms that produced it, so the UI
   and the audit log can show why.

The classifier is deliberately rule-based: it is auditable, deterministic and
testable, which matters more here than statistical sophistication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobs.sources.base import EmploymentType


@dataclass(frozen=True)
class _Term:
    """A single recognition pattern."""

    category: EmploymentType
    pattern: str
    #: 0..1 — how conclusively this term identifies the category on its own.
    specificity: float
    label: str

    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE | re.UNICODE)


def _t(category: EmploymentType, pattern: str, specificity: float, label: str) -> _Term:
    return _Term(category=category, pattern=pattern, specificity=specificity, label=label)


# --------------------------------------------------------------------------- #
# Term tables                                                                 #
# --------------------------------------------------------------------------- #
#
# Specificity guidance:
#   0.90-1.00  unambiguous, category-defining (Werkstudent, Praktikum, HiWi)
#   0.70-0.89  strong but occasionally contextual
#   0.45-0.69  indicative; needs corroboration
#   0.10-0.44  weak/generic; never decides alone

TERMS: tuple[_Term, ...] = (
    # ---------------------------------------------------------- WORKING STUDENT --
    # The umlaut-free and common misspellings are included because job boards
    # frequently contain "Werksstudent".
    _t(EmploymentType.WORKING_STUDENT, r"\bwerk(?:s)?student(?:in|en|innen|entätigkeit|entatigkeit|enstelle|enstelle)?\b", 0.97, "Werkstudent"),
    _t(EmploymentType.WORKING_STUDENT, r"\bwerkstudierende[rn]?\b", 0.97, "Werkstudierende"),
    _t(EmploymentType.WORKING_STUDENT, r"\bworking[\s\-]?student\b", 0.95, "Working Student"),
    _t(EmploymentType.WORKING_STUDENT, r"\bstudentische[\s\-]?aushilfe\b", 0.90, "Studentische Aushilfe"),
    _t(EmploymentType.WORKING_STUDENT, r"\bstudentische[rn]?[\s\-]?mitarbeiter(?:in)?\b", 0.85, "Studentische Mitarbeiter"),
    _t(EmploymentType.WORKING_STUDENT, r"\bstudienbegleitend\w*\b", 0.70, "Studienbegleitend"),
    _t(EmploymentType.WORKING_STUDENT, r"\bneben\s+dem\s+studium\b", 0.65, "Neben dem Studium"),
    _t(EmploymentType.WORKING_STUDENT, r"\bneben\s+dem\s+studieren\b", 0.65, "Neben dem Studieren"),

    # Job-board category badges. These mark a posting as student-facing but do
    # NOT establish Werkstudent status, which in Germany is a specific legal
    # classification (enrolment-linked, ~20h/week during term, distinct tax and
    # social-security treatment). Hence the deliberately lower specificity: the
    # listing is treated as student employment, and the confidence value tells
    # the UI how strong that claim actually is.
    _t(EmploymentType.WORKING_STUDENT, r"\bstudentenjobs?\b", 0.60, "Studentenjob"),
    _t(EmploymentType.WORKING_STUDENT, r"\bstudierendenjobs?\b", 0.60, "Studierendenjob"),
    _t(EmploymentType.WORKING_STUDENT, r"\bstudentische[rn]?[\s\-]?(?:neben)?jobs?\b", 0.60, "Studentischer Job"),
    _t(EmploymentType.WORKING_STUDENT, r"\bnebenjobs?\b", 0.45, "Nebenjob"),

    # -------------------------------------------------------- STUDENT ASSISTANT --
    # University research/teaching roles. Grouped with working-student work for
    # search purposes (see STUDENT_EMPLOYMENT_TYPES) but kept distinct because
    # the terms are specific and users benefit from the precision.
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bwissenschaftliche[rn]?[\s\-]?hilfskraft\b", 0.95, "Wissenschaftliche Hilfskraft"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bstudentische[rn]?[\s\-]?hilfskraft\b", 0.95, "Studentische Hilfskraft"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bhilfskraft\b", 0.55, "Hilfskraft"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bhiwi\b", 0.92, "HiWi"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bstudent[\s\-]?assistant\b", 0.85, "Student Assistant"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\bteaching[\s\-]?assistant\b", 0.80, "Teaching Assistant"),
    _t(EmploymentType.STUDENT_ASSISTANT, r"\btutor(?:in)?\b", 0.45, "Tutor"),

    # ---------------------------------------------------------------- INTERNSHIP --
    # NOTE: `intern` must be word-bounded, otherwise "internal" and
    # "international" are misclassified as internships.
    _t(EmploymentType.INTERNSHIP, r"\bpflichtpraktikum\b", 0.98, "Pflichtpraktikum"),
    _t(EmploymentType.INTERNSHIP, r"\bfreiwilliges?[\s\-]?praktikum\b", 0.98, "Freiwilliges Praktikum"),
    _t(EmploymentType.INTERNSHIP, r"\bpraktikum\b", 0.95, "Praktikum"),
    _t(EmploymentType.INTERNSHIP, r"\bpraktikant(?:in|en)?\b", 0.93, "Praktikant"),
    _t(EmploymentType.INTERNSHIP, r"\bpraxissemester\b", 0.90, "Praxissemester"),
    _t(EmploymentType.INTERNSHIP, r"\binternship\b", 0.95, "Internship"),
    _t(EmploymentType.INTERNSHIP, r"\bintern\b", 0.80, "Intern"),

    # ---------------------------------------------------------------- PART TIME --
    _t(EmploymentType.PART_TIME, r"\bteilzeit\b", 0.92, "Teilzeit"),
    _t(EmploymentType.PART_TIME, r"\bpart[\s\-]?time\b", 0.92, "Part-time"),
    _t(EmploymentType.PART_TIME, r"\bparttime\b", 0.90, "Parttime"),
    _t(EmploymentType.PART_TIME, r"\bgeringfügig\w*\b", 0.55, "Geringfügig"),
    _t(EmploymentType.PART_TIME, r"\b\d{1,2}\s*(?:std\.?|stunden)\s*/\s*woche\b", 0.50, "Weekly hours"),

    # ---------------------------------------------------------------- FULL TIME --
    _t(EmploymentType.FULL_TIME, r"\bvollzeit\b", 0.92, "Vollzeit"),
    _t(EmploymentType.FULL_TIME, r"\bfull[\s\-]?time\b", 0.92, "Full-time"),
    _t(EmploymentType.FULL_TIME, r"\bfulltime\b", 0.90, "Fulltime"),
    _t(EmploymentType.FULL_TIME, r"\b40\s*(?:std\.?|stunden)\s*/\s*woche\b", 0.60, "40 hours/week"),

    # ------------------------------------------------------------------ MINI JOB --
    _t(EmploymentType.MINI_JOB, r"\bmini[\s\-]?job\b", 0.95, "Minijob"),
    _t(EmploymentType.MINI_JOB, r"\b450[\s\-]?(?:€|euro|eur)\b", 0.85, "450-Euro"),
    _t(EmploymentType.MINI_JOB, r"\b538[\s\-]?(?:€|euro|eur)\b", 0.85, "538-Euro"),

    # ----------------------------------------------------------------- TEMPORARY --
    _t(EmploymentType.TEMPORARY, r"\bzeitarbeit\b", 0.90, "Zeitarbeit"),
    _t(EmploymentType.TEMPORARY, r"\bleiharbeit\b", 0.90, "Leiharbeit"),
    _t(EmploymentType.TEMPORARY, r"\barbeitnehmerüberlassung\b", 0.90, "Arbeitnehmerüberlassung"),
    _t(EmploymentType.TEMPORARY, r"\bbefristet\w*\b", 0.65, "Befristet"),
    _t(EmploymentType.TEMPORARY, r"\btemporary\b", 0.80, "Temporary"),
    _t(EmploymentType.TEMPORARY, r"\bfixed[\s\-]?term\b", 0.80, "Fixed-term"),

    # ------------------------------------------------------------ APPRENTICESHIP --
    _t(EmploymentType.APPRENTICESHIP, r"\bausbildung\b", 0.92, "Ausbildung"),
    _t(EmploymentType.APPRENTICESHIP, r"\bauszubildende[rn]?\b", 0.95, "Auszubildende"),
    _t(EmploymentType.APPRENTICESHIP, r"\bazubi\b", 0.92, "Azubi"),
    _t(EmploymentType.APPRENTICESHIP, r"\bduales?\s+studium\b", 0.85, "Duales Studium"),
    _t(EmploymentType.APPRENTICESHIP, r"\bapprenticeship\b", 0.92, "Apprenticeship"),

    # --------------------------------------------------------------------- OTHER --
    _t(EmploymentType.OTHER, r"\bwerkvertrag\b", 0.85, "Werkvertrag"),
    _t(EmploymentType.OTHER, r"\bfreelance\b", 0.85, "Freelance"),
    _t(EmploymentType.OTHER, r"\bfreiberuflich\w*\b", 0.80, "Freiberuflich"),
    _t(EmploymentType.OTHER, r"\bhonorar\w*\b", 0.70, "Honorar"),

    # ----------------------------------------- generic student words (weak only) --
    # These exist purely to corroborate a stronger signal. On their own they
    # must never decide the category, which is why specificity is so low.
    _t(EmploymentType.UNKNOWN, r"\bstudent(?:en|in|innen)?\b", 0.15, "Student (generic)"),
    _t(EmploymentType.UNKNOWN, r"\bstudierende[rn]?\b", 0.15, "Studierende (generic)"),
    _t(EmploymentType.UNKNOWN, r"\bstudium\b", 0.12, "Studium (generic)"),
)

_COMPILED: tuple[tuple[_Term, re.Pattern[str]], ...] = tuple((term, term.regex()) for term in TERMS)

#: Field weights: the same word is stronger evidence in a title than in a long
#: description, where it may appear in an unrelated sentence.
FIELD_WEIGHT = {
    "title": 1.0,
    "employment_type_hint": 1.0,
    "description": 0.62,
}

#: Below this score we refuse to commit to a category.
MIN_CONFIDENCE = 0.35

#: If a competing category scores at least this fraction of the winner, the
#: listing is treated as ambiguous.
AMBIGUITY_RATIO = 0.80


@dataclass
class Classification:
    """Outcome of classifying one listing."""

    employment_type: EmploymentType
    confidence: float
    matched_terms: list[str] = field(default_factory=list)
    #: Which field produced the winning evidence ("title" or "description").
    evidence_field: str = ""
    #: Set when two categories competed and we declined to choose.
    ambiguous: bool = False
    #: The categories that actually had evidence, strongest first.
    #:
    #: Empty for a listing with no employment-type signal at all. For an
    #: ambiguous listing it holds every near-tied category, which is what lets a
    #: caller decide whether the ambiguity is acceptable — "Werkstudent or
    #: internship" is fine when both were requested, "Werkstudent or full-time"
    #: is not.
    candidates: tuple[EmploymentType, ...] = ()

    def as_dict(self) -> dict:
        return {
            "employment_type": self.employment_type.value,
            "employment_type_label": self.employment_type.label,
            "confidence": round(self.confidence, 3),
            "matched_terms": self.matched_terms,
            "evidence_field": self.evidence_field,
            "ambiguous": self.ambiguous,
            "candidates": [category.value for category in self.candidates],
        }


def _score_fields(title: str, description: str, hint: str) -> dict[EmploymentType, tuple[float, list[str], str]]:
    """Return the best score per category across all provided fields."""

    scores: dict[EmploymentType, tuple[float, list[str], str]] = {}

    fields = (
        ("title", title or ""),
        ("employment_type_hint", hint or ""),
        ("description", description or ""),
    )

    for field_name, text in fields:
        if not text:
            continue
        multiplier = FIELD_WEIGHT[field_name]

        for term, pattern in _COMPILED:
            if not pattern.search(text):
                continue
            score = term.specificity * multiplier
            current = scores.get(term.category)
            if current is None:
                scores[term.category] = (score, [term.label], field_name)
            else:
                best_score, labels, best_field = current
                labels = [*labels, term.label] if term.label not in labels else labels
                if score > best_score:
                    scores[term.category] = (score, labels, field_name)
                else:
                    scores[term.category] = (best_score, labels, best_field)

    return scores


def classify(
    title: str = "",
    description: str = "",
    employment_type_hint: str = "",
) -> Classification:
    """Classify a listing into an `EmploymentType`.

    Args:
        title: The listing title — the strongest signal.
        description: Optional description text, used for corroboration.
        employment_type_hint: A structured type supplied by the source (for
            example a badge on the job card). Treated as title-strength.

    Returns:
        A `Classification`. When the evidence is absent or contradictory the
        result is `EmploymentType.UNKNOWN`.
    """

    scores = _score_fields(title, description, employment_type_hint)

    if not scores:
        return Classification(EmploymentType.UNKNOWN, 0.0)

    # The generic "student" bucket is a corroborator, never a verdict.
    generic = scores.pop(EmploymentType.UNKNOWN, None)

    if not scores:
        # Only generic student words were found. Without a specific signal we
        # must not claim this is a working-student role.
        return Classification(
            EmploymentType.UNKNOWN,
            0.0,
            matched_terms=generic[1] if generic else [],
            evidence_field=generic[2] if generic else "",
        )

    ranked = sorted(scores.items(), key=lambda item: item[1][0], reverse=True)
    winner_category, (winner_score, winner_terms, winner_field) = ranked[0]

    # Corroboration: generic student words raise confidence slightly when a
    # specific category already won, because the listing really is student-facing.
    if generic is not None:
        winner_score = min(1.0, winner_score + 0.03 * len(generic[1]))

    ambiguous = False
    if len(ranked) > 1:
        runner_up_score = ranked[1][1][0]
        if runner_up_score >= winner_score * AMBIGUITY_RATIO:
            # Two categories are equally well supported; refuse to guess. Every
            # near-tied category is recorded so a caller filtering by type can
            # judge whether the ambiguity still satisfies the request.
            threshold = winner_score * AMBIGUITY_RATIO
            candidates = tuple(
                category for category, (score, _, _) in ranked if score >= threshold
            )
            return Classification(
                EmploymentType.UNKNOWN,
                round(min(winner_score, runner_up_score), 3),
                matched_terms=[*winner_terms, *ranked[1][1][1]],
                evidence_field=winner_field,
                ambiguous=True,
                candidates=candidates,
            )

    if winner_score < MIN_CONFIDENCE:
        return Classification(
            EmploymentType.UNKNOWN,
            round(winner_score, 3),
            matched_terms=winner_terms,
            evidence_field=winner_field,
            candidates=(winner_category,),
        )

    return Classification(
        winner_category,
        round(min(1.0, winner_score), 3),
        matched_terms=winner_terms,
        evidence_field=winner_field,
        candidates=(winner_category,),
    )


def classify_with_hint(hint: str) -> Classification:
    """Classify from a structured source hint only.

    Some sources expose a machine-readable employment type on the search result
    (for example a "Werkstudentenstelle" badge). That is more reliable than
    guessing from prose.
    """

    return classify(title="", description="", employment_type_hint=hint)
