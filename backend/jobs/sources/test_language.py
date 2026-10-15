"""Tests for language detection and requirement extraction.

Two separate questions, and the second is the one that affects whether someone
can apply:

* what language is the posting written in;
* what language does the employer expect from the reader.

The negatives matter here. A detector that labels everything "German" would
look fine against a German-only corpus and be useless on a mixed one, so each
positive case is paired with a case that must not match.
"""

from __future__ import annotations

from django.test import TestCase

from jobs.sources.language import (
    Language,
    LanguageRequirement,
    detect_language,
    detect_language_profile,
)


class LanguageDetectionTests(TestCase):
    def test_german_prose_is_detected(self):
        text = (
            "Du suchst einen Nebenjob für die Weihnachtszeit? Wir bieten "
            "flexible Arbeitszeiten und ein tolles Team im Bereich Verkauf."
        )
        self.assertEqual(detect_language(text), Language.GERMAN)

    def test_english_prose_is_detected(self):
        text = (
            "We are looking for an experienced engineer to join our team. "
            "You will build scalable systems and work with the product team."
        )
        self.assertEqual(detect_language(text), Language.ENGLISH)

    def test_umlauts_are_strong_evidence(self):
        """German job adverts often carry English terms; marks decide it."""

        self.assertEqual(detect_language("Werkstudent für Büroorganisation"), Language.GERMAN)

    def test_an_english_title_with_a_german_body_is_german(self):
        """The body is longer and carries the marks, which is the right call."""

        profile = detect_language_profile(
            title="Working Student - Software Development",
            description=(
                "Wir suchen Dich! Zu Deinen Aufgaben gehört die Unterstützung "
                "unseres Teams. Wir bieten flexible Arbeitszeiten."
            ),
        )
        self.assertEqual(profile.language, Language.GERMAN)

    def test_empty_text_is_unknown(self):
        self.assertEqual(detect_language(""), Language.UNKNOWN)
        self.assertEqual(detect_language(None), Language.UNKNOWN)  # type: ignore[arg-type]

    def test_text_without_signals_is_unknown(self):
        """Refusing to guess is better than a confident wrong answer."""

        self.assertEqual(detect_language("Werkstudent"), Language.UNKNOWN)

    def test_mixed_language_text_is_not_forced(self):
        """Evenly balanced signals should not produce a confident verdict."""

        self.assertEqual(detect_language("experience kenntnisse"), Language.UNKNOWN)


class LanguageRequirementTests(TestCase):
    def test_german_required_phrases(self):
        for text in (
            "Fließend Deutsch in Wort und Schrift ist Voraussetzung.",
            "Wir erwarten Deutschkenntnisse auf hohem Niveau.",
            "Sehr gute Deutschkenntnisse erforderlich.",
            "Fluent German is required for this role.",
        ):
            with self.subTest(text=text):
                profile = detect_language_profile(description=text)
                self.assertEqual(profile.requirement, LanguageRequirement.GERMAN_REQUIRED)

    def test_english_required_phrases(self):
        for text in (
            "Very good English skills are essential.",
            "Fluent English required.",
            "Wir suchen jemanden mit sehr guten Englischkenntnissen.",
            "Business English is a must.",
        ):
            with self.subTest(text=text):
                profile = detect_language_profile(description=text)
                self.assertEqual(profile.requirement, LanguageRequirement.ENGLISH_REQUIRED)

    def test_both_languages_requested(self):
        profile = detect_language_profile(
            description="Sehr gute Deutschkenntnisse und gute Englischkenntnisse erforderlich."
        )
        self.assertEqual(profile.requirement, LanguageRequirement.BOTH_REQUIRED)

    def test_a_language_mentioned_without_being_required(self):
        """"Deutsch von Vorteil" is not the same as "Deutsch erforderlich"."""

        profile = detect_language_profile(
            description="Deutschkenntnisse von Vorteil, aber nicht zwingend."
        )
        self.assertEqual(profile.requirement, LanguageRequirement.GERMAN_HELPFUL)
        self.assertFalse(profile.requirement.is_requirement)

    def test_no_mention_is_reported_as_not_stated(self):
        profile = detect_language_profile(
            title="Werkstudent Verkauf", description="Flexible Arbeitszeiten, gutes Team."
        )
        self.assertEqual(profile.requirement, LanguageRequirement.NONE_STATED)
        self.assertFalse(profile.requirement.is_requirement)

    def test_the_matched_phrase_is_returned_as_evidence(self):
        """The claim has to be checkable, not taken on trust."""

        profile = detect_language_profile(description="Wir verlangen Deutschkenntnisse.")
        self.assertIn("deutschkenntnisse", profile.evidence.lower())

    def test_a_requirement_in_the_title_is_found(self):
        """Not every advert puts it in the body."""

        profile = detect_language_profile(title="Werkstudent (Deutschkenntnisse erforderlich)")
        self.assertEqual(profile.requirement, LanguageRequirement.GERMAN_REQUIRED)

    def test_an_unrelated_word_containing_deutsch_does_not_match(self):
        """A bare mention must not be read as a requirement."""

        profile = detect_language_profile(description="Unser Team spricht Deutsch und Englisch.")
        self.assertEqual(profile.requirement, LanguageRequirement.NONE_STATED)


class RequirementLabelTests(TestCase):
    def test_requirements_are_distinguishable_from_mentions(self):
        self.assertTrue(LanguageRequirement.GERMAN_REQUIRED.is_requirement)
        self.assertTrue(LanguageRequirement.BOTH_REQUIRED.is_requirement)
        self.assertFalse(LanguageRequirement.GERMAN_HELPFUL.is_requirement)
        self.assertFalse(LanguageRequirement.NONE_STATED.is_requirement)

    def test_every_state_has_a_label(self):
        for state in LanguageRequirement:
            with self.subTest(state=state):
                self.assertTrue(state.label)

    def test_the_summary_prefers_the_requirement(self):
        """What the employer asks for matters more than the advert's language."""

        profile = detect_language_profile(
            title="Werkstudent", description="Fließend Deutsch erforderlich."
        )
        self.assertIn("German", profile.summary)
        self.assertIn("required", profile.summary)
