"""Core tests for the job-source layer.

Covers the shared machinery: employment classification, normalization,
deduplication, the authorization gate, and pipeline failure isolation.

Every test here is hermetic. No test in this project performs live requests to a
third-party platform.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from config.testkit import platform_providers_disabled

from jobs.sources.base import (
    STUDENT_EMPLOYMENT_TYPES,
    EmploymentType,
    NormalizedJob,
    ProviderStatus,
    RawJob,
    SearchRequest,
    WorkModel,
)
from jobs.sources.classification import classify
from jobs.sources.dedup import (
    DeduplicatedJob,
    canonical_url,
    deduplicate,
    normalize_company,
    normalize_title,
    title_similarity,
)
from jobs.sources.normalization import (
    detect_work_model,
    extract_skills,
    normalize_raw_job,
    parse_location,
    parse_posted_at,
)
from jobs.sources.registry import (
    PROVIDERS,
    authorization_reference,
    get_adapter,
    get_provider_status,
    provider_health,
)


# --------------------------------------------------------------------------- #
# Employment classification                                                   #
# --------------------------------------------------------------------------- #


class ClassificationTests(TestCase):
    """German and English employment terminology."""

    def test_working_student_variants(self):
        for title in (
            "Werkstudent Softwareentwicklung",
            "Werkstudentin im Marketing",
            "Werkstudierende für Data Science",
            "Werkstudententätigkeit im Controlling",
            "Werksstudent (m/w/d)",  # common misspelling on job boards
            "Working Student Position",
            "Studentische Aushilfe im Büro",
            "Studienbegleitende Tätigkeit",
        ):
            with self.subTest(title=title):
                result = classify(title)
                self.assertEqual(result.employment_type, EmploymentType.WORKING_STUDENT, title)
                self.assertGreaterEqual(result.confidence, 0.6)
                self.assertTrue(result.matched_terms)

    def test_student_assistant_variants(self):
        for title in (
            "Studentische Hilfskraft (HiWi)",
            "Wissenschaftliche Hilfskraft",
            "HiWi am Lehrstuhl",
            "Student Assistant",
            "Teaching Assistant",
        ):
            with self.subTest(title=title):
                result = classify(title)
                self.assertEqual(result.employment_type, EmploymentType.STUDENT_ASSISTANT, title)

    def test_internship_variants(self):
        for title in (
            "Praktikum im Bereich Data Science",
            "Pflichtpraktikum Softwareentwicklung",
            "Freiwilliges Praktikum Marketing",
            "Praktikant (m/w/d) im Vertrieb",
            "Internship - Business Development",
            "Praxissemester Informatik",
        ):
            with self.subTest(title=title):
                result = classify(title)
                self.assertEqual(result.employment_type, EmploymentType.INTERNSHIP, title)

    def test_part_time_and_full_time(self):
        self.assertEqual(classify("Teilzeit Kraft im Büro").employment_type, EmploymentType.PART_TIME)
        self.assertEqual(classify("Part-time Support Agent").employment_type, EmploymentType.PART_TIME)
        self.assertEqual(classify("Vollzeit Softwareentwickler").employment_type, EmploymentType.FULL_TIME)
        self.assertEqual(classify("Full-time Engineer").employment_type, EmploymentType.FULL_TIME)

    def test_mini_job_temporary_apprenticeship(self):
        self.assertEqual(classify("Minijob Verkauf").employment_type, EmploymentType.MINI_JOB)
        self.assertEqual(classify("Zeitarbeit Produktionshelfer").employment_type, EmploymentType.TEMPORARY)
        self.assertEqual(classify("Ausbildung zum Fachinformatiker").employment_type, EmploymentType.APPRENTICESHIP)
        self.assertEqual(classify("Auszubildende Mechatronik").employment_type, EmploymentType.APPRENTICESHIP)
        self.assertEqual(classify("Duales Studium Informatik").employment_type, EmploymentType.APPRENTICESHIP)

    # -- traps ------------------------------------------------------------- #

    def test_generic_student_word_is_not_a_working_student_job(self):
        """The word "student" alone must never decide the category."""

        result = classify("Student Success Manager")
        self.assertEqual(result.employment_type, EmploymentType.UNKNOWN)
        self.assertIn("Student (generic)", result.matched_terms)

    def test_internal_and_international_are_not_internships(self):
        """`\\bintern\\b` must be word-bounded."""

        for title in ("Senior Internal Audit Manager", "International Sales Lead"):
            with self.subTest(title=title):
                result = classify(title, "Working with international partners.")
                self.assertNotEqual(result.employment_type, EmploymentType.INTERNSHIP, title)

    def test_no_signal_is_unknown(self):
        self.assertEqual(classify("Software Engineer").employment_type, EmploymentType.UNKNOWN)
        self.assertEqual(classify("").employment_type, EmploymentType.UNKNOWN)

    def test_conflicting_signals_stay_unknown(self):
        """Two equally supported categories must not be guessed between."""

        result = classify("Werkstudent Praktikum")
        self.assertEqual(result.employment_type, EmploymentType.UNKNOWN)
        self.assertTrue(result.ambiguous)

    def test_description_corroborates_title(self):
        result = classify("Praktikum", "Wir suchen einen Praktikanten für 6 Monate.")
        self.assertEqual(result.employment_type, EmploymentType.INTERNSHIP)
        self.assertGreater(result.confidence, 0.9)

    def test_title_outweighs_description(self):
        """A title signal beats a weaker description signal."""

        result = classify("Werkstudent Entwicklung", "Wir bieten auch Praktika an.")
        self.assertEqual(result.employment_type, EmploymentType.WORKING_STUDENT)

    def test_structured_hint_is_used(self):
        result = classify("", "", "Werkstudentenstelle")
        self.assertEqual(result.employment_type, EmploymentType.WORKING_STUDENT)

    def test_result_is_serialisable(self):
        payload = classify("Werkstudent").as_dict()
        self.assertEqual(payload["employment_type"], "working-student")
        self.assertEqual(payload["employment_type_label"], "Working student")
        self.assertIn("confidence", payload)

    def test_student_employment_group_includes_assistants(self):
        self.assertIn(EmploymentType.STUDENT_ASSISTANT, STUDENT_EMPLOYMENT_TYPES)
        self.assertIn(EmploymentType.WORKING_STUDENT, STUDENT_EMPLOYMENT_TYPES)

    def test_board_badges_are_recognised(self):
        """Job-board category badges are structured data, not prose.

        Stellenwerk labels postings with badges such as "Studierendenjob" and
        "Werkstudentenstelle". None of these contain a word boundary after the
        stem, so a bare "student" pattern misses them entirely.
        """

        for badge in ("Studierendenjob", "Studentenjob", "Werkstudentenstelle", "Nebenjob"):
            with self.subTest(badge=badge):
                result = classify(title="Aushilfe", employment_type_hint=badge, description="")
                self.assertEqual(result.employment_type, EmploymentType.WORKING_STUDENT)

    def test_board_badge_confidence_is_lower_than_werkstudent(self):
        """A category badge must not claim Werkstudent legal status.

        In Germany "Werkstudent" is a specific legal classification tied to
        enrolment, roughly 20h/week during term and distinct tax treatment. A
        generic "Studentenjob" badge does not establish that, so it is treated
        as student employment with a visibly lower confidence.
        """

        badge = classify(title="Aushilfe", employment_type_hint="Studierendenjob", description="")
        precise = classify(title="Werkstudent (m/w/d)", employment_type_hint="", description="")
        self.assertEqual(badge.employment_type, precise.employment_type)
        self.assertLess(badge.confidence, precise.confidence)
        self.assertGreaterEqual(badge.confidence, 0.35)

    def test_badge_survives_a_german_compound_title(self):
        """Regression: the real listing that exposed the gap."""

        result = classify(
            title="Studentenjob Weihnachtsmarkt 2026 – 15 €/Std. | Flexible Schichten",
            employment_type_hint="Studierendenjob",
            description="Du suchst einen Nebenjob für die Weihnachtszeit.",
        )
        self.assertEqual(result.employment_type, EmploymentType.WORKING_STUDENT)
        self.assertFalse(result.ambiguous)

    def test_graduate_badge_is_not_student_work(self):
        """"Absolvent:innenjob" targets graduates, not students."""

        result = classify(
            title="Projektingenieur (m/w/d) Hochbau",
            employment_type_hint="Absolvent:innenjob",
            description="Sie starten Ihre Karriere bei uns direkt im Projekt.",
        )
        self.assertNotIn(result.employment_type, STUDENT_EMPLOYMENT_TYPES)

    def test_candidates_are_empty_without_evidence(self):
        """A posting that never states a type must carry no candidates.

        The employment filter relies on this to tell "no idea what this is"
        apart from "could be either of two things".
        """

        result = classify(title="Projektingenieur (m/w/d) Hochbau", description="")
        self.assertEqual(result.employment_type, EmploymentType.UNKNOWN)
        self.assertEqual(result.candidates, ())

    def test_candidates_record_a_single_winner(self):
        result = classify(title="Werkstudent Softwareentwicklung", description="")
        self.assertEqual(result.candidates, (EmploymentType.WORKING_STUDENT,))

    def test_candidates_record_both_sides_of_an_ambiguity(self):
        """"Intern / Working Student" is genuinely one of the two."""

        result = classify(title="Intern / Working Student Software-Testing", description="")
        self.assertEqual(result.employment_type, EmploymentType.UNKNOWN)
        self.assertTrue(result.ambiguous)
        self.assertEqual(
            set(result.candidates),
            {EmploymentType.WORKING_STUDENT, EmploymentType.INTERNSHIP},
        )

    def test_candidates_expose_an_ambiguity_with_a_non_student_type(self):
        result = classify(title="Werkstudent oder Vollzeit", description="")
        self.assertTrue(result.candidates)
        self.assertIn(EmploymentType.WORKING_STUDENT, result.candidates)

    def test_candidates_are_serialisable(self):
        payload = classify(title="Werkstudent Softwareentwicklung").as_dict()
        self.assertEqual(payload["candidates"], ["working-student"])


# --------------------------------------------------------------------------- #
# Normalization                                                               #
# --------------------------------------------------------------------------- #


class LocationParsingTests(TestCase):
    def test_city_only(self):
        result = parse_location("Berlin")
        self.assertEqual(result["city"], "Berlin")
        self.assertEqual(result["country"], "Germany")

    def test_city_and_region(self):
        result = parse_location("Köln, Nordrhein-Westfalen")
        self.assertEqual(result["city"], "Köln")
        self.assertEqual(result["region"], "Nordrhein-Westfalen")

    def test_country_in_parentheses(self):
        result = parse_location("Remote (Germany)")
        self.assertEqual(result["country"], "Germany")

    def test_multiple_cities_are_preserved(self):
        result = parse_location("Bremen, Köln, Berlin")
        self.assertIn("Bremen", result["city"])
        self.assertIn("Berlin", result["city"])

    def test_empty_location(self):
        result = parse_location("")
        self.assertEqual(result["city"], "")
        self.assertEqual(result["country"], "Germany")


class WorkModelTests(TestCase):
    def test_remote(self):
        self.assertEqual(detect_work_model("Remote position"), WorkModel.REMOTE)
        self.assertEqual(detect_work_model("Homeoffice möglich"), WorkModel.REMOTE)

    def test_hybrid(self):
        self.assertEqual(detect_work_model("Hybrid working model"), WorkModel.HYBRID)

    def test_on_site_default(self):
        self.assertEqual(detect_work_model("Office in Berlin"), WorkModel.ON_SITE)

    def test_unknown_when_no_text(self):
        self.assertEqual(detect_work_model(""), WorkModel.UNKNOWN)


class DateParsingTests(TestCase):
    def test_iso_date(self):
        parsed = parse_posted_at("2026-10-09")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 10, 9))

    def test_german_date(self):
        parsed = parse_posted_at("09.10.2026")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 10, 9))

    def test_relative_german(self):
        parsed = parse_posted_at("vor 3 Tagen")
        self.assertIsNotNone(parsed)
        age = timezone.now() - parsed
        self.assertAlmostEqual(age.total_seconds(), 3 * 86400, delta=120)

    def test_relative_english(self):
        parsed = parse_posted_at("5 hours ago")
        self.assertIsNotNone(parsed)
        age = timezone.now() - parsed
        self.assertAlmostEqual(age.total_seconds(), 5 * 3600, delta=120)

    def test_today_and_yesterday(self):
        self.assertIsNotNone(parse_posted_at("Heute"))
        yesterday = parse_posted_at("gestern")
        age = timezone.now() - yesterday
        self.assertAlmostEqual(age.total_seconds(), 86400, delta=120)

    def test_unparseable(self):
        self.assertIsNone(parse_posted_at("keine Angabe"))
        self.assertIsNone(parse_posted_at(""))


class SkillExtractionTests(TestCase):
    def test_word_bounded_matching(self):
        """Short skill keys must not match inside ordinary words."""

        skills = extract_skills("Wir entwickeln Software für Kunden in Dortmund")
        self.assertNotIn("R", skills)
        self.assertNotIn("Go", skills)

    def test_recognises_real_skills(self):
        skills = extract_skills("Erfahrung mit Python, Django, Docker und PostgreSQL")
        for expected in ("Python", "Django", "Docker", "PostgreSQL"):
            self.assertIn(expected, skills)

    def test_display_casing(self):
        self.assertIn("JavaScript", extract_skills("javascript and typescript"))
        self.assertIn("SQL", extract_skills("gute SQL kenntnisse"))
        self.assertIn("AWS", extract_skills("Erfahrung mit AWS"))
        self.assertIn("C++", extract_skills("C++ development"))

    def test_empty_input(self):
        self.assertEqual(extract_skills(""), [])
        self.assertEqual(extract_skills(None), [])

    def test_german_terms_are_recognised(self):
        """The product targets Germany, so German wording must register.

        Regression: a listing titled "Werkstudent Softwareentwicklung" used to
        yield no skills at all, which made the "strong match" tier unreachable
        for the exact roles the product exists to find.
        """

        self.assertIn("Software development", extract_skills("Werkstudent Softwareentwicklung"))
        self.assertIn("Databases", extract_skills("Kenntnisse in Java, Python und Datenbanken"))
        self.assertIn("Machine learning", extract_skills("Maschinelles Lernen und Datenanalyse"))
        self.assertIn("Accounting", extract_skills("Schwerpunkt Rechnungswesen"))

    def test_acronyms_are_matched_case_sensitively(self):
        self.assertIn("Artificial intelligence", extract_skills("Schwerpunkt AI"))
        self.assertIn("IT", extract_skills("IT-Support für Anwender"))
        self.assertIn("HR", extract_skills("für den Bereich HR"))

    def test_acronyms_do_not_match_inside_words(self):
        """"Mai" contains "ai" and "LogProIT" contains "IT"."""

        self.assertEqual(extract_skills("Der Mai ist schön"), [])
        self.assertNotIn("IT", extract_skills("LogProIT GmbH sucht Verstärkung"))
        self.assertNotIn("IT", extract_skills("Die Qualität der Arbeit"))


class NormalizationTests(TestCase):
    def _raw(self, **overrides) -> RawJob:
        defaults = dict(
            source="Test",
            external_id="1",
            title="Werkstudent Softwareentwicklung",
            company="Acme GmbH",
            location="Dortmund, Nordrhein-Westfalen",
            url="https://example.invalid/1",
            description="Python und Django.",
            employment_type_raw="",
            posted_at_raw="2026-10-09",
        )
        defaults.update(overrides)
        return RawJob(**defaults)

    def test_full_normalization(self):
        job = normalize_raw_job(self._raw())
        self.assertEqual(job.title, "Werkstudent Softwareentwicklung")
        self.assertEqual(job.city, "Dortmund")
        self.assertEqual(job.region, "Nordrhein-Westfalen")
        self.assertEqual(job.country, "Germany")
        self.assertEqual(job.employment_type, EmploymentType.WORKING_STUDENT)
        self.assertGreater(job.employment_type_confidence, 0.6)
        self.assertIn("Python", job.required_skills)
        self.assertIsNotNone(job.posted_at)
        self.assertIsNotNone(job.collected_at)

    def test_structured_hint_used_when_prose_is_silent(self):
        job = normalize_raw_job(self._raw(title="Entwickler (m/w/d)", employment_type_raw="Werkstudentenstelle"))
        self.assertEqual(job.employment_type, EmploymentType.WORKING_STUDENT)

    def test_raw_payload_preserved(self):
        job = normalize_raw_job(self._raw(payload={"id": 42}))
        self.assertEqual(job.raw_source_data["id"], 42)

    def test_title_only_record_is_valid(self):
        job = normalize_raw_job(self._raw(title="Something", company="", location="", url=""))
        self.assertTrue(job.is_valid)

    def test_empty_title_is_invalid(self):
        job = normalize_raw_job(self._raw(title=""))
        self.assertFalse(job.is_valid)


# --------------------------------------------------------------------------- #
# Deduplication                                                               #
# --------------------------------------------------------------------------- #


class DeduplicationTests(TestCase):
    def _job(self, **overrides) -> NormalizedJob:
        defaults = dict(
            source="LinkedIn",
            source_url="https://example.invalid/job/1",
            title="Werkstudent Softwareentwicklung (m/w/d)",
            company="Acme GmbH",
            city="Dortmund",
            location="Dortmund",
        )
        defaults.update(overrides)
        return NormalizedJob(**defaults)

    def test_canonical_url_strips_tracking(self):
        left = canonical_url("https://www.example.com/job/1?utm_source=x&refId=abc")
        right = canonical_url("https://example.com/job/1")
        self.assertEqual(left, right)

    def test_canonical_url_strips_fragment_and_trailing_slash(self):
        self.assertEqual(
            canonical_url("https://example.com/job/1/#apply"),
            canonical_url("https://example.com/job/1"),
        )

    def test_normalize_title_removes_gender_and_type_markers(self):
        self.assertEqual(
            normalize_title("Werkstudent Softwareentwicklung (m/w/d)"),
            normalize_title("Softwareentwicklung"),
        )

    def test_normalize_company_strips_legal_suffix(self):
        self.assertEqual(normalize_company("Acme GmbH"), normalize_company("Acme"))
        self.assertEqual(normalize_company("Acme AG"), "acme")

    def test_identical_urls_merge(self):
        groups = deduplicate([self._job(), self._job(source="StepStone")])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].matched_by, "canonical-url")
        self.assertEqual(len(groups[0].sources), 2)

    def test_same_external_id_within_source_merges(self):
        groups = deduplicate(
            [
                self._job(source_url="https://a.invalid/1", external_id="X1"),
                self._job(source_url="https://b.invalid/2", external_id="X1"),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].matched_by, "source-external-id")

    def test_title_company_location_match_merges_across_sources(self):
        groups = deduplicate(
            [
                self._job(source_url="https://a.invalid/1", source="LinkedIn"),
                self._job(source_url="https://b.invalid/2", source="StepStone"),
            ]
        )
        self.assertEqual(len(groups), 1)

    def test_different_jobs_are_not_merged(self):
        groups = deduplicate(
            [
                self._job(title="Werkstudent Softwareentwicklung"),
                self._job(title="Werkstudent Marketing", source_url="https://x/2"),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_same_title_different_companies_are_not_merged(self):
        """Similar titles must never merge on their own."""

        groups = deduplicate(
            [
                self._job(company="Acme GmbH"),
                self._job(company="Globex GmbH", source_url="https://x/2"),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_same_company_different_locations_are_not_merged(self):
        groups = deduplicate(
            [
                self._job(city="Dortmund", location="Dortmund"),
                self._job(city="Berlin", location="Berlin", source_url="https://x/2"),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_near_identical_titles_merge_when_company_and_city_match(self):
        groups = deduplicate(
            [
                self._job(title="Werkstudent Softwareentwicklung (m/w/d)"),
                self._job(
                    title="Werkstudent Softwareentwicklung (w/m/d)",
                    source_url="https://other.invalid/9",
                    source="StepStone",
                ),
            ]
        )
        self.assertEqual(len(groups), 1)

    def test_richer_record_becomes_primary(self):
        sparse = self._job(description="", required_skills=[])
        rich = self._job(source_url="https://example.invalid/job/1", description="x" * 500, required_skills=["Python"])
        groups = deduplicate([sparse, rich])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].primary.description, "x" * 500)

    def test_provenance_records_every_source(self):
        groups = deduplicate([self._job(), self._job(source="StepStone")])
        provenance = groups[0].as_provenance()
        sources = {entry["source"] for entry in provenance}
        self.assertEqual(sources, {"LinkedIn", "StepStone"})

    def test_invalid_records_are_dropped(self):
        groups = deduplicate([self._job(title=""), self._job()])
        self.assertEqual(len(groups), 1)

    def test_similarity_helper(self):
        self.assertEqual(title_similarity("a", "a"), 1.0)
        self.assertEqual(title_similarity("", "a"), 0.0)
        self.assertLess(title_similarity("abc", "xyz"), 0.5)


# --------------------------------------------------------------------------- #
# Authorization gate                                                          #
# --------------------------------------------------------------------------- #


@platform_providers_disabled()
class AuthorizationGateTests(TestCase):
    """The compliance boundary. These tests are the reason the gate exists.

    Pinned to the fail-closed defaults so a developer's `backend/.env` cannot
    turn these assertions into a no-op.
    """

    def test_all_platform_providers_default_to_disabled(self):
        for name in ("linkedin", "stepstone", "stellenwerk"):
            with self.subTest(provider=name):
                status = get_provider_status(name)
                self.assertIn(
                    status,
                    {ProviderStatus.DISABLED_BY_CONFIG, ProviderStatus.DISABLED_AUTHORIZATION_PENDING},
                )
                self.assertFalse(status.is_operational)

    def test_enabling_without_authorization_stays_disabled(self):
        """Flipping the switch alone must not enable live collection."""

        with override_settings(
            PROVIDER_LINKEDIN_ENABLED=True,
            PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE="",
        ):
            status = get_provider_status("linkedin")
            self.assertEqual(status, ProviderStatus.DISABLED_AUTHORIZATION_PENDING)
            self.assertFalse(status.is_operational)

    def test_no_adapter_is_returned_without_authorization(self):
        with override_settings(
            PROVIDER_LINKEDIN_ENABLED=True,
            PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE="",
        ):
            self.assertIsNone(get_adapter("linkedin"))

    def test_adapter_is_returned_only_with_enable_and_authorization(self):
        with override_settings(
            PROVIDER_LINKEDIN_ENABLED=True,
            PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE="DOC-1234",
        ):
            status = get_provider_status("linkedin")
            self.assertEqual(status, ProviderStatus.READY)
            self.assertTrue(status.is_operational)
            self.assertIsNotNone(get_adapter("linkedin"))

    def test_authorization_reference_is_read(self):
        with override_settings(PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE="  CONTRACT-9  "):
            self.assertEqual(authorization_reference("stepstone"), "CONTRACT-9")

    def test_manual_import_needs_no_authorization(self):
        """The manual path performs no third-party access, so it is available."""

        status = get_provider_status("manual")
        self.assertEqual(status, ProviderStatus.READY)
        self.assertIsNotNone(get_adapter("manual"))

    def test_unknown_provider_is_an_integration_error(self):
        self.assertEqual(get_provider_status("does-not-exist"), ProviderStatus.INTEGRATION_ERROR)

    def test_health_snapshot_explains_each_provider(self):
        snapshot = {entry.source: entry for entry in provider_health()}
        self.assertEqual(set(snapshot), set(PROVIDERS))
        for entry in snapshot.values():
            self.assertTrue(entry.detail)

    def test_disabled_providers_report_a_reason(self):
        snapshot = {entry.source: entry for entry in provider_health()}
        linkedin = snapshot["linkedin"]
        self.assertFalse(linkedin.status.is_operational)
        self.assertIn(
            linkedin.status,
            {ProviderStatus.DISABLED_BY_CONFIG, ProviderStatus.DISABLED_AUTHORIZATION_PENDING},
        )


# --------------------------------------------------------------------------- #
# Pipeline                                                                    #
# --------------------------------------------------------------------------- #


@platform_providers_disabled()
class PipelineIsolationTests(TestCase):
    """A failing source must never take the run down with it."""

    def _request(self) -> SearchRequest:
        return SearchRequest(
            keywords=["Werkstudent"],
            locations=["Dortmund"],
            sources=["linkedin", "stepstone", "stellenwerk"],
            max_results=10,
        )

    def test_disabled_sources_produce_no_calls_and_are_reported(self):
        from jobs.sources.pipeline import collect_raw_jobs

        raw, outcomes = collect_raw_jobs(self._request())
        self.assertEqual(raw, [])
        self.assertEqual(len(outcomes), 3)
        for outcome in outcomes:
            self.assertEqual(outcome.fetched, 0)
            self.assertFalse(outcome.status.is_operational)

    def test_warnings_explain_why_a_source_was_skipped(self):
        from jobs.sources.pipeline import PipelineResult, SourceOutcome

        result = PipelineResult(
            outcomes=[
                SourceOutcome(
                    source="linkedin",
                    status=ProviderStatus.DISABLED_AUTHORIZATION_PENDING,
                )
            ]
        )
        self.assertTrue(any("authorization" in note.lower() for note in result.warnings))

    def test_one_failing_adapter_does_not_stop_the_others(self):
        from jobs.sources import pipeline as pipeline_module
        from jobs.sources.base import ProviderStatus as PS

        class Boom:
            name = "boom"

            def search(self, request):
                raise RuntimeError("adapter exploded")

        class Good:
            name = "good"

            def search(self, request):
                return [
                    RawJob(
                        source="Good",
                        title="Werkstudent Test",
                        company="Acme",
                        url="https://example.invalid/1",
                    )
                ]

        original_status = pipeline_module.get_provider_status
        original_adapter = pipeline_module.get_adapter
        try:
            pipeline_module.get_provider_status = lambda name: PS.READY
            pipeline_module.get_adapter = lambda name: Boom() if name == "boom" else Good()

            raw, outcomes = pipeline_module.collect_raw_jobs(
                SearchRequest(sources=["boom", "good"], keywords=["x"], locations=["y"])
            )
        finally:
            pipeline_module.get_provider_status = original_status
            pipeline_module.get_adapter = original_adapter

        self.assertEqual(len(raw), 1)
        by_source = {outcome.source: outcome for outcome in outcomes}
        self.assertEqual(by_source["boom"].status, ProviderStatus.INTEGRATION_ERROR)
        self.assertEqual(by_source["good"].fetched, 1)

    def test_blocked_source_is_reported_as_unavailable(self):
        from jobs.sources import pipeline as pipeline_module
        from jobs.sources.http import SourceBlocked

        class Blocked:
            name = "blocked"

            def search(self, request):
                raise SourceBlocked(429, "https://example.invalid", retry_after=60)

        original_status = pipeline_module.get_provider_status
        original_adapter = pipeline_module.get_adapter
        try:
            pipeline_module.get_provider_status = lambda name: ProviderStatus.READY
            pipeline_module.get_adapter = lambda name: Blocked()

            _, outcomes = pipeline_module.collect_raw_jobs(SearchRequest(sources=["blocked"]))
        finally:
            pipeline_module.get_provider_status = original_status
            pipeline_module.get_adapter = original_adapter

        self.assertEqual(outcomes[0].status, ProviderStatus.TEMPORARILY_UNAVAILABLE)
        self.assertIn("429", outcomes[0].error)


class EmploymentFilterTests(TestCase):
    def _group(
        self,
        employment_type: EmploymentType,
        candidates: tuple[EmploymentType, ...] = (),
    ) -> DeduplicatedJob:
        return DeduplicatedJob(
            primary=NormalizedJob(
                source="Test",
                source_url="https://example.invalid",
                title="Job",
                company="Acme",
                employment_type=employment_type,
                employment_type_candidates=list(candidates),
            )
        )

    def test_working_student_filter_includes_assistants(self):
        from jobs.sources.pipeline import apply_employment_filter

        groups = [
            self._group(EmploymentType.WORKING_STUDENT),
            self._group(EmploymentType.STUDENT_ASSISTANT),
            self._group(EmploymentType.FULL_TIME),
        ]
        kept = apply_employment_filter(groups, [EmploymentType.WORKING_STUDENT])
        types = {group.primary.employment_type for group in kept}
        self.assertIn(EmploymentType.WORKING_STUDENT, types)
        self.assertIn(EmploymentType.STUDENT_ASSISTANT, types)
        self.assertNotIn(EmploymentType.FULL_TIME, types)

    def test_untyped_records_are_excluded(self):
        """Regression: full-time roles used to appear in student-only results.

        A listing with no employment-type evidence at all — "Projektingenieur",
        "Trainee Ingenieur" — was previously retained for every filter, so a
        working-student search returned full-time jobs.
        """

        from jobs.sources.pipeline import apply_employment_filter

        groups = [self._group(EmploymentType.UNKNOWN)]  # no candidates
        kept = apply_employment_filter(groups, [EmploymentType.WORKING_STUDENT])
        self.assertEqual(kept, [])

    def test_ambiguous_records_are_kept_when_every_candidate_matches(self):
        """"Intern / Working Student" really is one of the two requested types."""

        from jobs.sources.pipeline import apply_employment_filter

        groups = [
            self._group(
                EmploymentType.UNKNOWN,
                candidates=(EmploymentType.WORKING_STUDENT, EmploymentType.INTERNSHIP),
            )
        ]
        kept = apply_employment_filter(
            groups, [EmploymentType.WORKING_STUDENT, EmploymentType.INTERNSHIP]
        )
        self.assertEqual(len(kept), 1)

    def test_ambiguous_records_are_excluded_when_a_candidate_is_outside_the_filter(self):
        """Ambiguous with full-time might not be the student role that was asked for."""

        from jobs.sources.pipeline import apply_employment_filter

        groups = [
            self._group(
                EmploymentType.UNKNOWN,
                candidates=(EmploymentType.WORKING_STUDENT, EmploymentType.FULL_TIME),
            )
        ]
        kept = apply_employment_filter(groups, [EmploymentType.WORKING_STUDENT])
        self.assertEqual(kept, [])

    def test_ambiguous_student_pair_matches_a_single_student_filter(self):
        """Selecting only "working student" still reaches HiWi/assistant posts."""

        from jobs.sources.pipeline import apply_employment_filter

        groups = [
            self._group(
                EmploymentType.UNKNOWN,
                candidates=(EmploymentType.WORKING_STUDENT, EmploymentType.STUDENT_ASSISTANT),
            )
        ]
        kept = apply_employment_filter(groups, [EmploymentType.WORKING_STUDENT])
        self.assertEqual(len(kept), 1)

    def test_withheld_count_is_reported(self):
        """Excluded listings must be counted, never dropped silently."""

        from jobs.sources.pipeline import split_by_employment_filter

        groups = [
            self._group(EmploymentType.WORKING_STUDENT),
            self._group(EmploymentType.UNKNOWN),
            self._group(EmploymentType.UNKNOWN),
            self._group(EmploymentType.FULL_TIME),
        ]
        kept, withheld = split_by_employment_filter(groups, [EmploymentType.WORKING_STUDENT])
        self.assertEqual(len(kept), 1)
        self.assertEqual(withheld, 2)

    def test_full_time_filter_excludes_student_roles(self):
        from jobs.sources.pipeline import apply_employment_filter

        groups = [
            self._group(EmploymentType.FULL_TIME),
            self._group(EmploymentType.WORKING_STUDENT),
            self._group(EmploymentType.UNKNOWN),
        ]
        kept = apply_employment_filter(groups, [EmploymentType.FULL_TIME])
        self.assertEqual([group.primary.employment_type for group in kept], [EmploymentType.FULL_TIME])

    def test_no_filter_keeps_everything(self):
        from jobs.sources.pipeline import apply_employment_filter

        groups = [self._group(EmploymentType.FULL_TIME)]
        self.assertEqual(len(apply_employment_filter(groups, [])), 1)


# --------------------------------------------------------------------------- #
# Response encoding                                                           #
# --------------------------------------------------------------------------- #


class ResponseEncodingTests(TestCase):
    """German job boards are the whole point, so mojibake is not cosmetic.

    A title decoded as Latin-1 arrives as "Werkstudent fÃ¼r den Bereich HR".
    The classifier matches on the title, so corruption directly degrades the
    product's core signal.
    """

    def _response(self, body: bytes, content_type: str) -> "requests.Response":
        import requests

        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = content_type
        response._content = body
        # A hand-built Response skips the adapter step that derives `encoding`
        # from the headers, so reproduce it here.
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)
        return response

    def test_missing_charset_is_corrected_to_utf8(self):
        from jobs.sources.http import _correct_encoding

        body = "Werkstudent für den Bereich HR · Dülmen".encode("utf-8")
        response = self._response(body, "text/html")
        self.assertEqual(response.encoding, "ISO-8859-1")

        fixed = _correct_encoding(response)
        self.assertEqual(fixed.text, "Werkstudent für den Bereich HR · Dülmen")
        self.assertNotIn("Ã", fixed.text)

    def test_explicit_charset_is_trusted(self):
        """A server that declares Latin-1 is taken at its word."""

        from jobs.sources.http import _correct_encoding

        body = "Werkstudent für den Bereich HR".encode("iso-8859-1")
        response = self._response(body, "text/html; charset=iso-8859-1")
        fixed = _correct_encoding(response)
        self.assertEqual(fixed.text, "Werkstudent für den Bereich HR")

    def test_utf8_declared_charset_is_untouched(self):
        from jobs.sources.http import _correct_encoding

        body = "Übergangsmanagement".encode("utf-8")
        response = self._response(body, "application/json; charset=utf-8")
        fixed = _correct_encoding(response)
        self.assertEqual(fixed.text, "Übergangsmanagement")

    def test_plain_ascii_is_unaffected(self):
        from jobs.sources.http import _correct_encoding

        body = b"Werkstudent Software Development"
        response = self._response(body, "text/html")
        self.assertEqual(_correct_encoding(response).text, "Werkstudent Software Development")


# --------------------------------------------------------------------------- #
# Enrichment                                                                  #
# --------------------------------------------------------------------------- #


class EnrichmentTests(TestCase):
    """Detail fetches are best-effort and budgeted."""

    def _job(self, n: int) -> RawJob:
        return RawJob(
            source="Test",
            title=f"Werkstudent {n}",
            company="Acme",
            url=f"https://example.invalid/{n}",
        )

    def test_enrichment_populates_descriptions(self):
        from jobs.sources.pipeline import _enrich_listings

        class Adapter:
            name = "test"
            calls = 0

            def enrich(self, job):
                Adapter.calls += 1
                job.description = f"detail-{job.url}"

        jobs = [self._job(1), self._job(2)]
        with override_settings(SOURCE_ENRICH_LIMIT=5):
            count = _enrich_listings(Adapter(), jobs)

        self.assertEqual(count, 2)
        self.assertTrue(all(job.description for job in jobs))

    def test_budget_caps_the_number_of_requests(self):
        from jobs.sources.pipeline import _enrich_listings

        class Adapter:
            name = "test"
            calls = 0

            def enrich(self, job):
                Adapter.calls += 1

        jobs = [self._job(n) for n in range(10)]
        with override_settings(SOURCE_ENRICH_LIMIT=3):
            count = _enrich_listings(Adapter(), jobs)

        self.assertEqual(count, 3)
        self.assertEqual(Adapter.calls, 3)

    def test_zero_budget_skips_enrichment_entirely(self):
        from jobs.sources.pipeline import _enrich_listings

        class Adapter:
            name = "test"

            def enrich(self, job):
                raise AssertionError("must not be called")

        with override_settings(SOURCE_ENRICH_LIMIT=0):
            self.assertEqual(_enrich_listings(Adapter(), [self._job(1)]), 0)

    def test_a_failing_detail_page_does_not_lose_the_listing(self):
        from jobs.sources.pipeline import _enrich_listings

        class Adapter:
            name = "test"

            def enrich(self, job):
                raise RuntimeError("detail page exploded")

        jobs = [self._job(1), self._job(2)]
        with override_settings(SOURCE_ENRICH_LIMIT=5):
            count = _enrich_listings(Adapter(), jobs)

        self.assertEqual(count, 0)
        self.assertEqual(len(jobs), 2)

    def test_a_block_stops_enrichment_but_keeps_collected_listings(self):
        """Enrichment must never escalate into retrying a rate limit."""

        from jobs.sources.http import SourceBlocked
        from jobs.sources.pipeline import _enrich_listings

        class Adapter:
            name = "test"
            calls = 0

            def enrich(self, job):
                Adapter.calls += 1
                raise SourceBlocked(429, job.url)

        jobs = [self._job(n) for n in range(5)]
        with override_settings(SOURCE_ENRICH_LIMIT=5):
            count = _enrich_listings(Adapter(), jobs)

        self.assertEqual(count, 0)
        self.assertEqual(Adapter.calls, 1, "must stop at the first block, not retry")
        self.assertEqual(len(jobs), 5)

    def test_adapter_without_enrich_is_tolerated(self):
        """StepStone returns descriptions inline and defines no enrich()."""

        from jobs.sources import pipeline as pipeline_module

        class Adapter:
            name = "inline"

            def search(self, request):
                return [
                    RawJob(
                        source="Test",
                        title="Werkstudent 1",
                        company="Acme",
                        url="https://example.invalid/1",
                    )
                ]

        original_status = pipeline_module.get_provider_status
        original_adapter = pipeline_module.get_adapter
        try:
            pipeline_module.get_provider_status = lambda name: ProviderStatus.READY
            pipeline_module.get_adapter = lambda name: Adapter()
            _, outcomes = pipeline_module.collect_raw_jobs(SearchRequest(sources=["inline"]))
        finally:
            pipeline_module.get_provider_status = original_status
            pipeline_module.get_adapter = original_adapter

        self.assertEqual(outcomes[0].fetched, 1)
        self.assertEqual(outcomes[0].enriched, 0)
        self.assertTrue(outcomes[0].produced_results)

