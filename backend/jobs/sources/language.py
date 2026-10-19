"""Detect what language a posting is written in, and what it asks of you.

Two separate questions, and the second is the one that actually matters to a
user:

1. **What language is this posting in?** German listings are the norm on the
   boards this product searches, so a job written entirely in German is useful
   information before you open it.

2. **What language does the employer expect from you?** A German-language
   posting that says "fließend Deutsch" is a different proposition from one
   that says "gute Englischkenntnisse" — and a reader who does not speak German
   needs to know which, without translating the whole advert.

Deliberately rule-based rather than a language-detection library. The text is
short (a title plus a few hundred characters), the candidate set is two
languages, and a dependency would be less accurate than counting the signals
that are unambiguous in this domain.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Language(str, Enum):
    """The language a posting is written in."""

    GERMAN = "german"
    ENGLISH = "english"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            Language.GERMAN: "German",
            Language.ENGLISH: "English",
            Language.UNKNOWN: "Unknown",
        }[self]


class LanguageRequirement(str, Enum):
    """What language ability a posting asks for."""

    GERMAN_REQUIRED = "german-required"
    ENGLISH_REQUIRED = "english-required"
    BOTH_REQUIRED = "both-required"
    GERMAN_HELPFUL = "german-helpful"
    ENGLISH_HELPFUL = "english-helpful"
    NONE_STATED = "none-stated"

    @property
    def label(self) -> str:
        return {
            LanguageRequirement.GERMAN_REQUIRED: "German required",
            LanguageRequirement.ENGLISH_REQUIRED: "English required",
            LanguageRequirement.BOTH_REQUIRED: "German and English",
            LanguageRequirement.GERMAN_HELPFUL: "German helpful",
            LanguageRequirement.ENGLISH_HELPFUL: "English helpful",
            LanguageRequirement.NONE_STATED: "Not stated",
        }[self]

    @property
    def is_requirement(self) -> bool:
        """True when the posting states the language as a requirement."""

        return self in {
            LanguageRequirement.GERMAN_REQUIRED,
            LanguageRequirement.ENGLISH_REQUIRED,
            LanguageRequirement.BOTH_REQUIRED,
        }


class LanguageFilter(str, Enum):
    """Which postings a user wants to see, by the language they are written in.

    Kept separate from `Language` because "any" is a legitimate preference and
    "unknown" is not: a user can ask for every language, but nobody wants to
    filter *for* postings whose language could not be determined. `UNKNOWN` is
    an outcome of detection, not something to search on.
    """

    ANY = "any"
    GERMAN = "german"
    ENGLISH = "english"

    @property
    def label(self) -> str:
        return {
            LanguageFilter.ANY: "Any language",
            LanguageFilter.GERMAN: "German",
            LanguageFilter.ENGLISH: "English",
        }[self]


def matches_language_filter(language: Language | str, wanted: LanguageFilter | str) -> bool:
    """True when a posting's language satisfies the preference."""

    try:
        wanted_filter = LanguageFilter(wanted)
    except ValueError:
        # An unrecognised preference is treated as "no preference" rather than
        # hiding everything, which would look like the search was broken.
        return True

    if wanted_filter is LanguageFilter.ANY:
        return True

    return str(getattr(language, "value", language)) == wanted_filter.value


# --------------------------------------------------------------------------- #
# Language of the text                                                        #
# --------------------------------------------------------------------------- #

#: Characters that occur in German and essentially never in English.
_GERMAN_CHARS = set("äöüßÄÖÜ")

#: Words frequent in German prose and rare or absent in English job adverts.
#: Chosen for low ambiguity: each is a whole word, so "in" and "die" cannot
#: match inside an English one.
_GERMAN_WORDS = frozenset(
    """
    und oder der die das den dem des ein eine einen einem eines
    für mit von bei sich sind wird werden ist sind nicht auch
    als auf aus im in zur zum sie ihre ihren wir unsere
    kenntnisse erfahrung aufgaben profil benefits bewerbung
    stellenangebot mitarbeiter team kollegen bereich
    """.split()
)

#: Whole words that are English and not also German.
_ENGLISH_WORDS = frozenset(
    """
    and or the of for with from your you we our are is will
    experience skills requirements responsibilities about
    role team benefits apply job position company
    """.split()
)


def _words(text: str) -> list[str]:
    """Lowercase word tokens."""

    return [t for t in re.split(r"[^a-zäöüß]+", (text or "").lower()) if t]


def detect_language(*texts: str) -> Language:
    """Guess the language of a posting from its title and description.

    Weighted rather than a simple count: an umlaut is strong evidence and a
    common word is weak, because German job adverts routinely carry English
    terms like "Software Engineer" in an otherwise German sentence.
    """

    combined = " ".join(t for t in texts if t)
    if not combined.strip():
        return Language.UNKNOWN

    words = _words(combined)
    if not words:
        return Language.UNKNOWN

    # Umlauts and ß are near-conclusive.
    german_marks = sum(1 for ch in combined if ch in _GERMAN_CHARS)
    german_score = german_marks * 3

    english_score = 0
    for word in words:
        if word in _GERMAN_WORDS:
            german_score += 1
        elif word in _ENGLISH_WORDS:
            english_score += 1

    # Ratio-based, so a long English description with one German word does not
    # flip the verdict, and a short German title still registers.
    total = german_score + english_score
    if total == 0:
        return Language.UNKNOWN
    if german_score / total >= 0.6:
        return Language.GERMAN
    if english_score / total >= 0.6:
        return Language.ENGLISH
    return Language.UNKNOWN


# --------------------------------------------------------------------------- #
# What the posting asks of the reader                                         #
# --------------------------------------------------------------------------- #

#: A mention of a language ability, in either language.
#:
#: Matches the mention only — whether it is *required* is decided by the cues
#: around it, not by the phrase itself. "Deutschkenntnisse" appears in both
#: "Deutschkenntnisse erforderlich" and "Deutschkenntnisse von Vorteil", so a
#: single pattern cannot classify it.
_LANGUAGE_MENTION = re.compile(
    r"("
    # German nouns, with any preceding adjective: "sehr guten Englischkenntnissen"
    r"(?:\w+\s+){0,3}(?:deutsch|englisch)(?:kenntnisse|sprachkenntnisse)"
    r"|(?:\w+\s+){0,3}(?:deutsch|englisch)\s+in\s+wort\s+und\s+schrift"
    r"|(?:flie(?:ß|ss)end(?:e|es)?|verhandlungssicher(?:es)?)\s+(?:deutsch|englisch)"
    # English equivalents
    r"|(?:german|english)\s+(?:language\s+)?(?:skills|fluency|proficiency)"
    r"|(?:fluent|native)\s+(?:in\s+)?(?:german|english)"
    r"|business\s+english"
    r")",
    re.IGNORECASE,
)

#: Wording that turns a mention into a demand.
#:
#: Includes the idiomatic German adjective phrases — "sehr gute
#: Englischkenntnisse" is a requirement even though it contains no verb
#: meaning "require".
_REQUIRING_CUE = re.compile(
    r"(erforderlich|vorausgesetzt|zwingend|notwendig|voraussetzung"
    r"|verlangen|erwarten|verf(?:ü|ue)gen\s+(?:sie\s+)?(?:ü|ue)ber"
    r"|required|essential|must\s+have|necessary|mandatory"
    r"|(?:sehr\s+)?gut(?:e|en)?\s+(?:deutsch|englisch)"
    r"|verhandlungssicher"
    # "is a must" — idiomatic and unambiguous, but "must" alone would match
    # "must not".
    r"|is\s+a\s+must)",
    re.IGNORECASE,
)

#: Wording that turns a mention into a preference.
_HELPFUL_CUE = re.compile(
    r"(von\s+vorteil|w(?:ä|ae)re\s+(?:ein\s+)?vorteil|idealerweise"
    r"|nice\s+to\s+have|is\s+a\s+plus|advantage|beneficial"
    r"|nicht\s+zwingend|nicht\s+erforderlich"
    r"|but\s+not\s+(?:required|mandatory|essential))",
    re.IGNORECASE,
)

#: How far either side of a mention to look for a cue, in characters.
#:
#: Wide enough to span "Deutschkenntnisse auf hohem Niveau sind erforderlich",
#: narrow enough not to pick up a requirement about the *other* language
#: elsewhere in the paragraph.
_CUE_WINDOW = 80


#: Leading filler to strip from captured evidence.
#:
#: The mention pattern allows up to three preceding words so it can catch
#: "sehr guten Englischkenntnissen", but that also swallows conjunctions —
#: producing evidence like "und Englischkenntnisse", which reads oddly when
#: shown to a user as the reason for the verdict.
_EVIDENCE_FILLER = re.compile(
    r"^(?:und|oder|sowie|mit|von|für|fur|the|and|or|with|of|in|a|an)\s+",
    re.IGNORECASE,
)


def _clean_evidence(text: str) -> str:
    """Trim leading filler from a captured mention."""

    cleaned = (text or "").strip()
    while True:
        trimmed = _EVIDENCE_FILLER.sub("", cleaned, count=1).strip()
        if trimmed == cleaned:
            return cleaned
        cleaned = trimmed


def _mention_is_required(text: str, mention: re.Match) -> bool | None:
    """Classify one language mention as required, helpful, or unstated.

    Returns None when neither cue is present, which is the honest answer: the
    advert mentioned a language without saying what it expects.
    """

    start = max(0, mention.start() - _CUE_WINDOW)
    end = min(len(text), mention.end() + _CUE_WINDOW)
    window = text[start:end]

    # Helpful wins when both appear, because a preference is usually phrased as
    # "von Vorteil, aber nicht erforderlich" — which contains a requiring word
    # negated by the helpful one.
    if _HELPFUL_CUE.search(window):
        return False
    if _REQUIRING_CUE.search(window):
        return True
    return None


def _language_mentions(text: str, language: str) -> list[re.Match]:
    """Mentions of one specific language."""

    needles = (
        ("deutsch", "german")
        if language == "german"
        else ("englisch", "english")
    )
    return [
        m
        for m in _LANGUAGE_MENTION.finditer(text)
        if any(needle in m.group(0).lower() for needle in needles)
    ]

#: Phrases that mention a language without requiring it.
@dataclass(frozen=True)
class LanguageProfile:
    """What a posting says about language, ready for display."""

    #: The language the posting is written in.
    language: Language
    #: What it asks of the reader.
    requirement: LanguageRequirement
    #: The matched phrase, so the UI can show why it reached that conclusion.
    evidence: str = ""

    @property
    def summary(self) -> str:
        """One line for a job card."""

        if self.requirement.is_requirement:
            return self.requirement.label
        return f"Written in {self.language.label}" if self.language is not Language.UNKNOWN else ""


def detect_language_profile(
    title: str = "", description: str = "", extra: str = ""
) -> LanguageProfile:
    """Read a posting's language and what it asks of the reader.

    Requirement phrases are checked across title and description together,
    because a requirement is often in the body while the title is in the other
    language entirely.
    """

    body = " ".join(part for part in (description, extra) if part)
    everything = " ".join(part for part in (title, body) if part)

    # Each language is judged on its own mentions, with the cue wording around
    # that mention deciding whether it is a demand or a preference. A single
    # pattern cannot do this: "Deutschkenntnisse" appears in both
    # "Deutschkenntnisse erforderlich" and "Deutschkenntnisse von Vorteil".
    german_required = any(
        _mention_is_required(everything, m) is True for m in _language_mentions(everything, "german")
    )
    english_required = any(
        _mention_is_required(everything, m) is True for m in _language_mentions(everything, "english")
    )

    if german_required and english_required:
        requirement = LanguageRequirement.BOTH_REQUIRED
    elif german_required:
        requirement = LanguageRequirement.GERMAN_REQUIRED
    elif english_required:
        requirement = LanguageRequirement.ENGLISH_REQUIRED
    elif _language_mentions(everything, "german"):
        requirement = LanguageRequirement.GERMAN_HELPFUL
    elif _language_mentions(everything, "english"):
        requirement = LanguageRequirement.ENGLISH_HELPFUL
    else:
        requirement = LanguageRequirement.NONE_STATED

    # The phrase that decided it, so the claim can be checked against the
    # advert rather than taken on trust.
    evidence = ""
    if requirement is not LanguageRequirement.NONE_STATED:
        language = "german" if "german" in requirement.value or requirement.value.startswith("german") else "english"
        if requirement is LanguageRequirement.BOTH_REQUIRED:
            language = "german"
        mentions = _language_mentions(everything, language)
        if mentions:
            evidence = _clean_evidence(mentions[0].group(0))

    return LanguageProfile(
        language=detect_language(title, body),
        requirement=requirement,
        evidence=evidence.strip(),
    )
