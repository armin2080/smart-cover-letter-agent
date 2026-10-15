"""Tests for the cross-language role vocabulary.

These cover the gap that made the product miss its own target market: German
postings for exactly the roles a user asked for, discarded because the two
sides were written in different languages.

Every case here is a real example. The negative cases matter as much as the
positive ones — a matcher that returns True for everything would look
successful while being useless.
"""

from __future__ import annotations

from django.test import TestCase

from jobs.sources.roles import (
    ALIASES,
    LANGUAGES,
    _CONCEPTS,
    canonical_terms,
    expand_for_search,
    titles_are_equivalent,
)


class VocabularyIntegrityTests(TestCase):
    """The data itself must stay coherent as entries are added."""

    def test_every_spelling_is_tagged_with_a_language(self):
        """ALIASES and LANGUAGES are derived together and must not diverge."""

        self.assertEqual(set(ALIASES), set(LANGUAGES))

    def test_every_spelling_maps_to_its_own_concept(self):
        for languages in _CONCEPTS.values():
            for spellings in languages.values():
                for spelling in spellings:
                    self.assertEqual(ALIASES[spelling], _concept_of(spelling))

    def test_spellings_are_lowercase(self):
        """Matching lowercases input, so a capitalised key would never match."""

        for spelling in ALIASES:
            self.assertEqual(spelling, spelling.lower(), spelling)

    def test_no_spelling_is_claimed_by_two_concepts(self):
        seen: dict[str, str] = {}
        for concept, languages in _CONCEPTS.items():
            for spellings in languages.values():
                for spelling in spellings:
                    self.assertNotIn(spelling, seen, f"{spelling} is in two concepts")
                    seen[spelling] = concept

    def test_german_spellings_are_tagged_german(self):
        """Language drives search expansion, so a wrong tag loses results."""

        for spelling in ("webentwicklung", "datenanalyse", "maschinelles lernen", "ki"):
            with self.subTest(spelling=spelling):
                self.assertEqual(LANGUAGES[spelling], "de")

    def test_english_spellings_are_tagged_english(self):
        for spelling in ("web development", "data science", "machine learning", "ai"):
            with self.subTest(spelling=spelling):
                self.assertEqual(LANGUAGES[spelling], "en")


def _concept_of(spelling: str) -> str:
    for concept, languages in _CONCEPTS.items():
        for spellings in languages.values():
            if spelling in spellings:
                return concept
    raise AssertionError(f"{spelling} is in no concept")


class CanonicalTermTests(TestCase):
    def test_german_and_english_resolve_to_one_concept(self):
        for text in ("Webentwickler", "web development", "Web Developer", "frontend"):
            with self.subTest(text=text):
                self.assertIn("web development", canonical_terms(text))

    def test_a_phrase_is_one_concept_not_two_words(self):
        self.assertIn("artificial intelligence", canonical_terms("artificial intelligence"))

    def test_an_acronym_resolves(self):
        self.assertIn("artificial intelligence", canonical_terms("AI"))
        self.assertIn("artificial intelligence", canonical_terms("KI"))

    def test_a_term_inside_a_sentence_is_found(self):
        """Job titles are phrases, not bare keywords."""

        self.assertIn("web development", canonical_terms("Webentwickler (m/w/d) gesucht"))
        self.assertIn("data science", canonical_terms("Praktikum im Bereich Datenanalyse"))

    def test_unrelated_text_yields_nothing(self):
        self.assertEqual(canonical_terms("Call Center Agent"), set())
        self.assertEqual(canonical_terms(""), set())


class TitleEquivalenceTests(TestCase):
    """The user's own examples, and the negatives that keep them meaningful."""

    def test_a_broad_target_matches_a_specific_title(self):
        """Desired "AI" should reach "AI engineer", "AI automation", "AI ops"."""

        for title in ("AI Engineer", "AI Automation Engineer", "AI-Ops Engineer"):
            with self.subTest(title=title):
                self.assertTrue(titles_are_equivalent(title, "AI"))

    def test_german_titles_match_english_roles(self):
        for title, role in (
            ("Webentwickler", "Web Development"),
            ("Softwareentwickler", "Software Development"),
            ("KI-Ingenieur", "AI Engineer"),
            ("Datenanalyst", "Data Science"),
            ("Systemadministrator", "System Administration"),
            ("Maschinenbauingenieur", "Mechanical Engineering"),
        ):
            with self.subTest(title=title):
                self.assertTrue(titles_are_equivalent(title, role))

    def test_english_titles_match_german_roles(self):
        """The reverse direction, since a user may type German."""

        self.assertTrue(titles_are_equivalent("Software Developer", "Softwareentwicklung"))
        self.assertTrue(titles_are_equivalent("Data Scientist", "Datenanalyse"))

    def test_plural_and_agent_forms_match(self):
        self.assertTrue(titles_are_equivalent("Data Scientist", "Data Science"))
        self.assertTrue(titles_are_equivalent("Software Engineer", "Software Engineering"))

    def test_german_compounds_match(self):
        """German glues words together, so a term can be a prefix of a title.

        "Maschinenbauingenieur" is "Maschinenbau" + "Ingenieur"; exact token
        matching sees neither word.
        """

        for title, role in (
            ("Maschinenbauingenieur", "Mechanical Engineering"),
            ("Datenbankadministrator", "Database Development"),
            ("Netzwerktechniker", "Networking"),
            ("Elektrotechniker", "Electrical Engineering"),
        ):
            with self.subTest(title=title):
                self.assertTrue(titles_are_equivalent(title, role))

    def test_a_compound_shorter_than_the_known_term_matches(self):
        """The posting may be less specific than the term in the vocabulary.

        "Bauingenieur" is shorter than "bauingenieurwesen", so a prefix test in
        only one direction misses it.
        """

        self.assertTrue(titles_are_equivalent("Bauingenieur", "Civil Engineering"))

    def test_a_short_token_does_not_claim_a_compound(self):
        """The length floor is what keeps "it" out of "item"."""

        self.assertFalse(titles_are_equivalent("Item Manager", "IT Support"))

    def test_the_role_inside_a_longer_title_matches(self):
        self.assertTrue(
            titles_are_equivalent("Werkstudent Softwareentwicklung (m/w/d)", "Softwareentwicklung")
        )

    def test_unrelated_roles_do_not_match(self):
        """A matcher that says yes to everything would look successful."""

        for title, role in (
            ("Marketing Manager", "Data Science"),
            ("Buchhalter", "Software Development"),
            ("Call Center Agent", "AI"),
            ("Praktiker", "Web Development"),
            ("Postbote", "Softwareentwicklung"),
            ("Nachhilfelehrer", "Data Science"),
            ("Bauingenieur", "Marketing"),
        ):
            with self.subTest(title=title):
                self.assertFalse(titles_are_equivalent(title, role))

    def test_empty_input_is_not_a_match(self):
        self.assertFalse(titles_are_equivalent("", "AI"))
        self.assertFalse(titles_are_equivalent("AI Engineer", ""))
        self.assertFalse(titles_are_equivalent("   ", "AI"))


class SearchExpansionTests(TestCase):
    """A search term must reach the other language's spelling."""

    def test_the_original_always_comes_first(self):
        """The user's own wording is tried first; expansion is a fallback."""

        self.assertEqual(expand_for_search("Web Development")[0], "Web Development")

    def test_german_is_offered_for_an_english_term(self):
        self.assertIn("webentwicklung", expand_for_search("Web Development"))
        self.assertIn("datenanalyse", expand_for_search("Data Science"))
        self.assertIn("ki", expand_for_search("AI"))

    def test_english_is_offered_for_a_german_term(self):
        expanded = expand_for_search("Softwareentwicklung")
        self.assertIn("software development", expanded)

    def test_the_canonical_translation_outranks_a_synonym(self):
        """Otherwise the budget fills with English synonyms and never reaches German."""

        expanded = expand_for_search("Web Development")
        self.assertLess(
            expanded.index("webentwicklung"),
            expanded.index("frontend") if "frontend" in expanded else 99,
        )

    def test_the_limit_is_respected(self):
        self.assertLessEqual(len(expand_for_search("AI", limit=2)), 2)

    def test_an_unknown_term_expands_to_itself(self):
        self.assertEqual(expand_for_search("Werkstudent"), ["Werkstudent"])

    def test_empty_input_yields_nothing(self):
        self.assertEqual(expand_for_search(""), [])
        self.assertEqual(expand_for_search("   "), [])
