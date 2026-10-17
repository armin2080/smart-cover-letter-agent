"""Cross-language vocabulary for job titles and search terms.

The problem
-----------
The listings this system collects are overwhelmingly German, while the terms a
user types are usually English. Left alone, the two never meet:

    "Webentwickler"   vs  "Web Development"   -> no match
    "KI-Ingenieur"    vs  "AI Engineer"       -> no match
    "Datenanalyst"    vs  "Data Science"      -> no match

That is not a cosmetic miss. A German posting for exactly the role someone
wants is discarded, and the search reports nothing found. The same applies in
the other direction: searching a German board for "web development" returns
nothing, because no German posting uses that phrase.

How this fixes it
-----------------
Two mappings, both applied to search terms and to job titles:

1. **Language aliases** — every spelling, in either language, resolves to one
   canonical English concept. `webentwicklung`, `webentwickler` and
   `web development` all become `web development`.
2. **Light stemming** — a shared prefix for tokens of five characters or more,
   which is enough for the morphology that actually occurs here
   (`science`/`scientist`, `engineer`/`engineering`, `develop`/`developer`)
   without pulling in a stemmer dependency or over-collapsing distinct words.

Acronyms are deliberately left alone. `IT`, `HR` and `AI` mean the same thing in
both languages and translating them invents errors rather than removing them.

Scope note: this is a curated list, not a translation service. It covers the
roles and skills this product targets, and grows by adding an entry.
"""

from __future__ import annotations

import re

#: Minimum shared prefix length before two tokens are treated as the same word.
#:
#: Five is chosen so `science`/`scientist` and `engineer`/`engineering` match
#: while genuinely different words stay apart. Four would start collapsing
#: unrelated pairs such as `data`/`date`.
_STEM_PREFIX = 5

#: Canonical concept -> its spellings, tagged by language.
#:
#: One source of truth. `ALIASES` and `LANGUAGES` are derived from this, so a
#: spelling cannot end up known to one and unknown to the other.
#:
#: Language is tagged explicitly rather than guessed from the characters:
#: "webentwicklung" is German but contains no umlaut, so an ASCII heuristic
#: would classify it as English and expansion would never offer it.
_CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "software development": {
        "en": ("software development", "software developer", "software engineer",
               "software engineering"),
        "de": ("softwareentwicklung", "softwareentwickler", "softwareentwicklerin",
               "anwendungsentwicklung", "anwendungsentwickler", "programmierung",
               "programmierer", "entwickler"),
    },
    "web development": {
        # "web" on its own is a real thing people type into a role field, and
        # without it a user asking for "Web" matched nothing German: the
        # compound "webentwicklung" maps to this concept, but the bare word
        # does not appear as a token in it, and "web" is too short to be
        # treated as a compound prefix (which would wrongly accept "webdesign").
        "en": ("web development", "web developer", "frontend", "frontend developer",
               "full stack", "fullstack", "web"),
        "de": ("webentwicklung", "webentwickler", "webentwicklerin",
               "frontendentwickler", "frontend-entwickler"),
    },
    "data science": {
        "en": ("data science", "data scientist", "data analyst", "data analytics"),
        "de": ("datenanalyse", "datenanalyst", "datenanalytiker", "datenauswertung",
               "datenwissenschaft"),
    },
    "database development": {
        "en": ("database development", "database developer", "database administration"),
        "de": ("datenbank", "datenbankentwicklung", "datenbankentwickler",
               "datenbankadministrator"),
    },
    "artificial intelligence": {
        "en": ("artificial intelligence", "ai", "ai engineer"),
        "de": ("ki", "künstliche intelligenz", "kuenstliche intelligenz",
               "ki-engineer", "ki-entwickler"),
    },
    "machine learning": {
        "en": ("machine learning", "deep learning"),
        "de": ("maschinelles lernen",),
    },
    "automation": {
        "en": ("automation", "automation engineer", "rpa"),
        "de": ("automatisierung", "automatisierungstechnik"),
    },
    "system administration": {
        "en": ("system administration", "system administrator"),
        "de": ("systemadministration", "systemadministrator"),
    },
    "networking": {
        "en": ("networking", "network engineer"),
        "de": ("netzwerk", "netzwerktechnik", "netzwerkadministrator"),
    },
    "devops": {"en": ("devops",), "de": ()},
    "cloud": {
        "en": ("cloud", "cloud engineer"),
        "de": ("cloud-architekt",),
    },
    "it support": {
        "en": ("it support", "it-support", "itsupport"),
        "de": ("it-systeme", "fachinformatiker"),
    },
    "software testing": {
        "en": ("software testing", "quality assurance", "test engineer"),
        "de": ("softwaretest", "softwaretester", "qualitätssicherung",
               "testautomatisierung"),
    },
    "it security": {
        "en": ("it security", "cyber security", "cybersecurity", "security engineer"),
        "de": ("it-sicherheit", "informationssicherheit"),
    },
    "product design": {
        "en": ("product design", "product designer", "ux design", "ux designer",
               "ui design", "ui designer", "interaction design"),
        "de": ("produktdesign", "produktdesigner"),
    },
    "accounting": {
        "en": ("accounting",),
        "de": ("buchhaltung", "rechnungswesen"),
    },
    "controlling": {"en": ("controlling",), "de": ()},
    "sales": {
        "en": ("sales",),
        "de": ("vertrieb",),
    },
    "marketing": {
        "en": ("marketing",),
        "de": ("online-marketing",),
    },
    "human resources": {
        "en": ("human resources", "recruiting"),
        "de": ("personalwesen", "personalabteilung"),
    },
    "project management": {
        "en": ("project management", "project manager"),
        "de": ("projektmanagement", "projektleiter"),
    },
    "logistics": {
        "en": ("logistics",),
        "de": ("logistik",),
    },
    "mechanical engineering": {
        "en": ("mechanical engineering",),
        "de": ("maschinenbau",),
    },
    "electrical engineering": {
        "en": ("electrical engineering",),
        "de": ("elektrotechnik",),
    },
    "civil engineering": {
        "en": ("civil engineering",),
        "de": ("bauingenieurwesen", "hochbau", "tiefbau"),
    },
    "process engineering": {
        "en": ("process engineering",),
        "de": ("verfahrenstechnik",),
    },
}

#: Every spelling -> the canonical concept it expresses.
ALIASES: dict[str, str] = {
    spelling: concept
    for concept, languages in _CONCEPTS.items()
    for spellings in languages.values()
    for spelling in spellings
}

#: Every spelling -> its language code.
LANGUAGES: dict[str, str] = {
    spelling: language
    for languages in _CONCEPTS.values()
    for language, spellings in languages.items()
    for spelling in spellings
}

#: Spellings grouped by concept, for expansion.
_VARIANTS: dict[str, set[str]] = {}
for _spelling, _concept in ALIASES.items():
    _VARIANTS.setdefault(_concept, set()).add(_spelling)

#: A spelling's position within its language's tuple.
#:
#: The tuples are written most-canonical-first, so this records the authored
#: preference and lets expansion offer "webentwicklung" before
#: "frontendentwickler". Without it, ordering falls back to alphabetical, which
#: is arbitrary.
_RANK: dict[str, int] = {
    spelling: index
    for languages in _CONCEPTS.values()
    for spellings in languages.values()
    for index, spelling in enumerate(spellings)
}

#: Single-word spellings long enough to be safe as a compound prefix.
#:
#: German glues words together: "Maschinenbauingenieur" is "Maschinenbau" +
#: "Ingenieur", and "Datenbankadministrator" is two words wearing a coat.
#: Exact token matching cannot see either. Five characters is the floor because
#: shorter keys collide with ordinary words — "it" would match "item".
_COMPOUND_PREFIXES: dict[str, str] = {
    spelling: concept
    for spelling, concept in ALIASES.items()
    if " " not in spelling and "-" not in spelling and len(spelling) >= _STEM_PREFIX
}


def _tokenise(text: str) -> list[str]:
    """Lowercase word tokens, keeping digits and inner hyphens as separators."""

    return [t for t in re.split(r"[^0-9a-zäöüß]+", (text or "").lower()) if t]


def canonical_terms(text: str) -> set[str]:
    """Canonical concepts expressed by `text`.

    Whole phrases are checked first — "artificial intelligence" is one concept,
    not two words — then each token, then each token as a German compound.
    """

    lowered = " ".join(_tokenise(text))
    found: set[str] = set()

    for spelling, concept in ALIASES.items():
        if " " in spelling or "-" in spelling:
            if spelling.replace("-", " ") in lowered:
                found.add(concept)

    for token in _tokenise(text):
        concept = ALIASES.get(token)
        if concept:
            found.add(concept)
            continue

        # German compound, forward: "maschinenbauingenieur" begins with
        # "maschinenbau". Longest prefix first so the most specific wins.
        for prefix in sorted(_COMPOUND_PREFIXES, key=len, reverse=True):
            if token.startswith(prefix):
                found.add(_COMPOUND_PREFIXES[prefix])
                break
        else:
            # German compound, reverse: the posting is more specific than the
            # term we know — "bauingenieur" against "bauingenieurwesen". The
            # same length floor applies, so "data" cannot claim "database".
            if len(token) >= _STEM_PREFIX:
                for spelling, mapped in ALIASES.items():
                    if " " not in spelling and spelling.startswith(token):
                        found.add(mapped)
                        break

    return found


def content_tokens(text: str) -> set[str]:
    """Tokens of `text`, with any token that carries a canonical concept removed.

    Used when comparing titles: the concept is compared separately, so leaving
    the original token in as well would let "Webentwicklung" match on the raw
    word and hide a translation failure.
    """

    return {t for t in _tokenise(text) if t not in ALIASES}


def stem(token: str) -> str:
    """Crude stem: a token's first `_STEM_PREFIX` characters, or itself."""

    return token[:_STEM_PREFIX] if len(token) > _STEM_PREFIX else token


def stems(text: str) -> set[str]:
    """Stems of the tokens in `text`, for morphology-insensitive comparison."""

    return {stem(t) for t in _tokenise(text)}


def expand_for_search(term: str, *, limit: int = 3) -> list[str]:
    """Search terms to use for `term`, including its other-language spellings.

    A user typing "Web Development" should also search "Webentwicklung",
    because German postings do not use the English phrase. The original is
    always first, so the user's own wording is tried first.

    Variants in the *other* language come next. Ordering by language rather
    than alphabetically matters: the variant set for a concept includes several
    English synonyms, and alphabetical order would fill the budget with
    "frontend" and "full stack" before ever reaching the German spelling that
    is the whole point of expanding.
    """

    cleaned = (term or "").strip()
    if not cleaned:
        return []

    variants: list[str] = [cleaned]
    seen = {cleaned.lower()}
    input_language = LANGUAGES.get(cleaned.lower(), "en")

    def other_language_first(spelling: str) -> tuple[int, int, str]:
        # Other language first, then the authored preference, then alphabetical
        # so the order is at least deterministic.
        differs = LANGUAGES.get(spelling, "en") != input_language
        return (0 if differs else 1, _RANK.get(spelling, 99), spelling)

    for concept in sorted(canonical_terms(cleaned)):
        for spelling in sorted(_VARIANTS.get(concept, ()), key=other_language_first):
            if spelling in seen:
                continue
            seen.add(spelling)
            variants.append(spelling)
            if len(variants) >= limit:
                return variants

    return variants[:limit]


def titles_are_equivalent(candidate: str, target: str) -> bool:
    """True when a job title and a desired role refer to the same thing.

    Three ways to match, in decreasing confidence:

    1. A canonical concept is shared ("Webentwickler" / "Web Development").
    2. One side's tokens are a subset of the other's ("AI" / "AI Engineer").
    3. The remaining content tokens share a stem ("Data Scientist" /
       "Data Science").
    """

    if not candidate.strip() or not target.strip():
        return False

    # 1. Same concept in either language.
    if canonical_terms(candidate) & canonical_terms(target):
        return True

    candidate_tokens = content_tokens(candidate)
    target_tokens = content_tokens(target)
    if not candidate_tokens or not target_tokens:
        return False

    # 2. Subset either way, which is what makes a bare "AI" match
    #    "AI Automation Engineer".
    if target_tokens <= candidate_tokens or candidate_tokens <= target_tokens:
        return True

    # 3. Shared stem, for plural and agent-noun forms.
    return bool(stems(candidate) & stems(target))
