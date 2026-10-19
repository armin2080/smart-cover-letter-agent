"""Tests for the jobs API and the explainable matching engine."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from config.testkit import platform_providers_disabled

from .matching import build_insight, normalise_terms, tokenize
from .models import ActivityEntry, Job, company_color, job_fingerprint

User = get_user_model()
PASSWORD = "test-pass-123"


def make_job(user, **overrides) -> Job:
    defaults = {
        "title": "Product Designer",
        "company": "Northstar Labs",
        "location": "Berlin, Germany",
        "employment_type": "full-time",
        "posted_at": timezone.now(),
        "source": "LinkedIn",
        "source_url": "https://example.com/job/1",
        "match": Job.Match.STRONG,
        "status": Job.Status.NEW,
        "skills": ["Figma", "Design systems"],
        "fingerprint": job_fingerprint("LinkedIn", "https://example.com/job/1", "Product Designer", "Northstar Labs"),
    }
    defaults.update(overrides)
    return Job.objects.create(user=user, **defaults)


class JobModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="jobs@example.com", password=PASSWORD)

    def test_initials_and_colour_are_derived(self):
        job = make_job(self.user, company="Fern & Co.")
        self.assertEqual(job.company_initials, "F&")
        self.assertTrue(job.company_color.startswith("#"))

    def test_colour_is_deterministic(self):
        self.assertEqual(company_color("Morrow"), company_color("Morrow"))

    def test_fingerprint_is_stable_and_case_insensitive(self):
        first = job_fingerprint("LinkedIn", "https://x/1", "Product Designer", "Acme")
        second = job_fingerprint("linkedin", "HTTPS://X/1", "product designer", "acme")
        self.assertEqual(first, second)

    def test_fingerprint_rejects_duplicates_per_user(self):
        make_job(self.user)
        with self.assertRaises(Exception):
            make_job(self.user)


@platform_providers_disabled()
class JobApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="api@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

        self.new_job = make_job(self.user, status=Job.Status.NEW)
        self.saved_job = make_job(
            self.user,
            title="Senior UX Designer",
            company="Morrow",
            status=Job.Status.SAVED,
            match=Job.Match.GOOD,
            source="StepStone",
            location="Remote · Germany",
            fingerprint="saved-1",
        )
        self.reviewed_job = make_job(
            self.user,
            title="UX Researcher",
            company="Cobalt",
            status=Job.Status.REVIEWED,
            fingerprint="reviewed-1",
        )
        self.dismissed_job = make_job(
            self.user,
            title="Design Lead",
            company="Vertex",
            status=Job.Status.DISMISSED,
            fingerprint="dismissed-1",
        )
        self.foreign_job = make_job(self.other, title="Not Yours", fingerprint="foreign-1")

    # -- list ------------------------------------------------------------- #

    def test_list_returns_paginated_envelope(self):
        response = self.client.get(reverse("job-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["count"], 4)

    def test_list_excludes_other_users_jobs(self):
        response = self.client.get(reverse("job-list"))
        titles = [job["title"] for job in response.data["results"]]
        self.assertNotIn("Not Yours", titles)

    def test_list_filters_by_status(self):
        response = self.client.get(reverse("job-list"), {"status": "saved"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "Senior UX Designer")

    def test_list_filters_by_source(self):
        response = self.client.get(reverse("job-list"), {"source": "StepStone"})
        self.assertEqual(response.data["count"], 1)

    def test_list_filters_by_match(self):
        response = self.client.get(reverse("job-list"), {"match": "good"})
        self.assertEqual(response.data["count"], 1)

    def test_list_searches_title_company_and_location(self):
        self.assertEqual(self.client.get(reverse("job-list"), {"q": "morrow"}).data["count"], 1)
        self.assertEqual(self.client.get(reverse("job-list"), {"q": "cobalt"}).data["count"], 1)
        # Three seeded jobs sit in Berlin (only the saved one is remote).
        self.assertEqual(self.client.get(reverse("job-list"), {"q": "berlin"}).data["count"], 3)

    def test_list_orders_newest_first(self):
        response = self.client.get(reverse("job-list"), {"ordering": "newest"})
        posted = [job["postedAt"] for job in response.data["results"]]
        self.assertEqual(posted, sorted(posted, reverse=True))

    def test_list_orders_by_match_strength(self):
        response = self.client.get(reverse("job-list"), {"ordering": "match", "page_size": 10})
        first = response.data["results"][0]
        self.assertEqual(first["match"], "strong")

    def test_list_serialises_camel_case_contract(self):
        job = self.client.get(reverse("job-list")).data["results"][0]
        for key in (
            "id",
            "title",
            "company",
            "companyInitials",
            "companyColor",
            "location",
            "employmentType",
            "postedAt",
            "source",
            "sourceUrl",
            "match",
            "status",
            "skills",
            "hasCoverLetter",
        ):
            self.assertIn(key, job)

    # -- counts ----------------------------------------------------------- #

    def test_counts(self):
        response = self.client.get(reverse("job-counts"))
        self.assertEqual(
            {key: response.data[key] for key in ("new", "reviewed", "saved", "dismissed")},
            {"new": 1, "reviewed": 1, "saved": 1, "dismissed": 1},
        )

    def test_counts_include_language_tallies_for_the_tabs(self):
        """The language tabs need their own totals.

        `any` is the total rather than the sum of the parts: a posting whose
        language could not be determined still belongs in the full list but has
        no tab of its own.
        """

        make_job(self.user, fingerprint="de-1", language="german")
        make_job(self.user, fingerprint="en-1", language="english")
        # Everything created in setUp defaults to "unknown".

        response = self.client.get(reverse("job-counts"))
        languages = response.data["languages"]

        self.assertEqual(languages["german"], 1)
        self.assertEqual(languages["english"], 1)
        self.assertEqual(languages["unknown"], 4)
        self.assertEqual(languages["any"], 6)
        self.assertEqual(languages["any"], sum(languages[key] for key in ("german", "english", "unknown")))

    # -- detail ----------------------------------------------------------- #

    def test_detail_includes_analysis(self):
        make_job(
            self.user,
            fingerprint="analysis-1",
            cv_alignment=[{"positive": True, "title": "Skills", "detail": "Figma"}],
            preference_fit=[{"positive": False, "title": "Location", "detail": "Far"}],
        )
        job = Job.objects.get(fingerprint="analysis-1")

        response = self.client.get(reverse("job-detail", args=[job.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["analysis"]["cvAlignment"][0]["title"], "Skills")
        self.assertEqual(response.data["analysis"]["preferenceFit"][0]["title"], "Location")

    def test_detail_cannot_access_another_users_job(self):
        response = self.client.get(reverse("job-detail", args=[self.foreign_job.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_status_updates_and_logs_activity(self):
        response = self.client.patch(
            reverse("job-detail", args=[self.new_job.id]), {"status": "saved"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "saved")

        self.new_job.refresh_from_db()
        self.assertEqual(self.new_job.status, "saved")
        self.assertTrue(ActivityEntry.objects.filter(user=self.user, kind="saved").exists())

    def test_patch_same_status_does_not_log_duplicate_activity(self):
        self.client.patch(reverse("job-detail", args=[self.saved_job.id]), {"status": "saved"}, format="json")
        self.assertEqual(ActivityEntry.objects.filter(user=self.user, kind="saved").count(), 0)

    def test_patch_rejects_invalid_status(self):
        response = self.client.patch(
            reverse("job-detail", args=[self.new_job.id]), {"status": "nonsense"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- stats / recent / activity ---------------------------------------- #

    def test_stats_cards(self):
        response = self.client.get(reverse("job-stats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cards = {card["key"]: card["value"] for card in response.data["cards"]}
        self.assertEqual(cards["new"], 1)
        self.assertEqual(cards["saved"], 1)
        self.assertIn("automaticSearchActive", response.data)

    def test_stats_report_whether_a_scheduler_is_actually_running(self):
        """Requested and scheduled are different things.

        Nothing inside the web process triggers a search on a timer, so without
        an external scheduler `nextSearchAt` would never arrive. The API has to
        say which of the two situations applies.
        """

        with override_settings(AUTO_SEARCH_SCHEDULER_ENABLED=False):
            response = self.client.get(reverse("job-stats"))
        self.assertFalse(response.data["schedulerActive"])

        with override_settings(AUTO_SEARCH_SCHEDULER_ENABLED=True):
            response = self.client.get(reverse("job-stats"))
        self.assertTrue(response.data["schedulerActive"])

    def test_a_scheduler_is_not_claimed_by_default(self):
        from django.conf import settings

        self.assertFalse(settings.AUTO_SEARCH_SCHEDULER_ENABLED)
        response = self.client.get(reverse("job-stats"))
        self.assertFalse(response.data["schedulerActive"])

    def test_recent_excludes_dismissed_and_respects_limit(self):
        response = self.client.get(reverse("job-recent"), {"limit": 2})
        self.assertEqual(len(response.data), 2)
        self.assertNotIn("Design Lead", [job["title"] for job in response.data])

    def test_activity_feed(self):
        ActivityEntry.objects.create(user=self.user, kind="discovered", title="Found jobs")
        response = self.client.get(reverse("activity-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["title"], "Found jobs")
        self.assertIn("occurredAt", response.data[0])

    def test_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        for url in (reverse("job-list"), reverse("job-counts"), reverse("job-stats")):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    # -- language filter --------------------------------------------------- #

    def test_language_filter_narrows_to_one_language(self):
        make_job(self.user, fingerprint="de-1", title="Werkstudent Entwicklung", language="german")
        make_job(self.user, fingerprint="en-1", title="Working Student Developer", language="english")

        response = self.client.get(reverse("job-list"), {"language": "german"})
        titles = [row["title"] for row in response.data["results"]]

        self.assertIn("Werkstudent Entwicklung", titles)
        self.assertNotIn("Working Student Developer", titles)

    def test_the_any_language_filter_filters_nothing(self):
        """Undetermined languages belong in the full list."""

        response = self.client.get(reverse("job-list"), {"language": "any"})
        self.assertEqual(response.data["count"], 4)


class MatchingEngineTests(APITestCase):
    """The matching engine must be explainable and never invent a percentage."""

    def _insight(self, **overrides):
        base = dict(
            job_title="Product Designer",
            company="Northstar Labs",
            location="Berlin, Germany",
            employment_type="full-time",
            source="LinkedIn",
            job_skills=["Figma", "Design systems"],
            job_requirements=["4+ years of product design experience"],
            job_summary="Design thoughtful products.",
            desired_roles=["Product Designer"],
            preferred_locations=["Berlin"],
            employment_types=["full-time"],
            preferred_sources=["LinkedIn"],
            keywords=["design"],
            profile_sections={
                "skills": "Figma, Design systems, User research",
                "experience": "Senior Product Designer 2019 - Present",
                "education": "M.A. Interaction Design",
            },
            profile_summary="Product designer with 5 years of experience.",
        )
        base.update(overrides)
        return build_insight(**base)

    def test_strong_match_when_aligned(self):
        insight = self._insight()
        self.assertEqual(insight.match, "strong")
        self.assertTrue(all(line.positive for line in insight.cv_alignment))
        self.assertTrue(all(line.positive for line in insight.preference_fit))

    def test_potential_match_when_misaligned(self):
        insight = self._insight(
            job_title="Backend Engineer",
            desired_roles=["Product Designer"],
            preferred_locations=["Munich"],
            employment_types=["part-time"],
            preferred_sources=["StepStone"],
            job_skills=["Kubernetes", "Go"],
            job_requirements=["5+ years of backend development"],
            profile_sections={"skills": "Figma, Illustration"},
        )
        self.assertEqual(insight.match, "potential")
        self.assertTrue(any(not line.positive for line in insight.preference_fit))

    def test_preference_fit_reports_location_mismatch(self):
        insight = self._insight(preferred_locations=["Munich"])
        location_line = next(line for line in insight.preference_fit if "Location" in line.title)
        self.assertFalse(location_line.positive)

    def test_a_neighbouring_city_is_not_reported_as_a_wrong_location(self):
        """A radius search returns nearby towns; they are not mismatches.

        The boards are queried with the location and the user's radius, so a
        Dortmund search returns Bochum and Hamm. Calling those "outside your
        preferences" is false — the user already said they would travel that
        far — and it dragged the preference ratio down far enough that no such
        job could ever be rated good.
        """

        insight = self._insight(preferred_locations=["Dortmund"], radius_km=50)
        location_line = next(
            line for line in insight.preference_fit if "city" in line.title.lower()
        )
        self.assertTrue(location_line.neutral)
        self.assertFalse(location_line.positive)

    def test_an_exact_city_search_still_rejects_another_city(self):
        """With radius 0 the user asked for that city specifically."""

        insight = self._insight(preferred_locations=["Dortmund"], radius_km=0)
        location_line = next(line for line in insight.preference_fit if "Location" in line.title)
        self.assertFalse(location_line.neutral)
        self.assertFalse(location_line.positive)

    def test_a_neutral_line_does_not_change_the_preference_ratio(self):
        """An unknown must not be scored as either a pass or a fail."""

        matched = self._insight(preferred_locations=["Berlin"], radius_km=50)
        unmatched = self._insight(
            preferred_locations=["Berlin"], radius_km=50, location="Hamburg"
        )
        # Same roles, employment and source lines, so the verdict must agree;
        # only an unverifiable location differs between them.
        self.assertEqual(matched.match, unmatched.match)

    def test_a_short_role_term_matches_its_german_compound(self):
        """Regression: "Web" matched nothing on German boards.

        `webentwicklung` maps to the "web development" concept, but the bare
        word "web" did not, and at three characters it is too short to be
        treated as a compound prefix. Someone listing Web as a target role
        therefore saw every German web posting as outside their roles.
        """

        insight = self._insight(
            job_title="Werkstudent Webentwicklung (m/w/d)",
            desired_roles=["Web"],
            job_skills=[],
            job_requirements=[],
        )
        role_line = next(line for line in insight.preference_fit if "role" in line.title.lower())
        self.assertTrue(role_line.positive, role_line.as_dict())

    def test_cv_alignment_reports_missing_requirements(self):
        insight = self._insight(job_skills=["Kubernetes"], job_requirements=[])
        self.assertTrue(any(not line.positive for line in insight.cv_alignment))

    def test_lines_serialise_to_contract_shape(self):
        insight = self._insight()
        for line in insight.cv_dicts:
            self.assertEqual(set(line), {"positive", "title", "detail", "neutral"})

    def test_empty_skills_does_not_crash(self):
        insight = self._insight(profile_sections={}, job_skills=[], job_requirements=[])
        self.assertIn(insight.match, {"strong", "good", "potential"})

    def test_tokenize_removes_stopwords(self):
        self.assertNotIn("and", tokenize("Design and research"))
        self.assertIn("design", tokenize("Design and research"))

    def test_german_wording_matches_a_canonical_label(self):
        """Regression: the product's core market is German-speaking.

        A posting whose skill label is "Software development" could never match
        a CV that says "Softwareentwicklung", because comparison ran on raw
        tokens and the English label's tokens do not appear in German prose.
        Both sides are now canonicalised through the same extractor.
        """

        insight = self._insight(
            job_title="Werkstudent (m/w/d) - Softwareentwicklung",
            job_skills=["Software development"],
            job_requirements=[],
            job_summary="",
            desired_roles=["Werkstudent Softwareentwicklung"],
            employment_types=["working-student"],
            profile_sections={
                "skills": "Python, Django, TypeScript, React, SQL",
                "experience": "Werkstudent Backend Developer 2024 - heute",
                "education": "B.Sc. Informatik",
            },
            profile_summary="Werkstudent Softwareentwicklung",
            keywords=[],
        )
        self.assertEqual(insight.match, "strong")
        self.assertTrue(any(line.positive for line in insight.cv_alignment))

    def test_a_matched_skill_is_not_also_reported_as_missing(self):
        """The UI must never claim a requirement is absent when it matched.

        The label "Software development" normalises to the token
        "development", which is not in a German CV verbatim. The gap list used
        to include it anyway, contradicting the line right above it.
        """

        insight = self._insight(
            job_title="Werkstudent Softwareentwicklung",
            job_skills=["Software development"],
            job_requirements=[],
            job_summary="",
            profile_sections={"skills": "Python, Django", "experience": "", "education": ""},
            profile_summary="Werkstudent Softwareentwicklung",
        )
        matched = [line for line in insight.cv_alignment if line.positive]
        missing = [line for line in insight.cv_alignment if not line.positive]
        self.assertTrue(matched, "expected the skill to match")
        self.assertFalse(
            any("development" in line.detail.lower() for line in missing),
            f"a matched skill was reported as missing: {[line.detail for line in missing]}",
        )

    def test_genuine_gaps_are_still_reported(self):
        insight = self._insight(
            job_title="Werkstudent Data Science",
            job_skills=["Python", "Kubernetes", "Terraform"],
            job_requirements=[],
            job_summary="",
            desired_roles=[],
            preferred_locations=[],
            employment_types=[],
            preferred_sources=[],
            keywords=[],
            profile_sections={"skills": "Python, Django", "experience": "", "education": ""},
            profile_summary="",
        )
        missing = " ".join(line.detail.lower() for line in insight.cv_alignment if not line.positive)
        self.assertIn("kubernetes", missing)
        self.assertIn("terraform", missing)

    def test_normalise_terms_drops_generic_words(self):
        self.assertEqual(normalise_terms(["Product Designer"]), {"designer"})

    # -- discrimination: this is what makes the categories meaningful ------- #

    def test_unrelated_domain_is_never_strong_despite_good_preferences(self):
        """A front-end role must not be 'strong' for a design profile.

        Location, employment type and source all align here, so only the skill
        signal can prevent an incorrect 'strong' verdict.
        """

        insight = self._insight(
            job_title="Frontend Engineer",
            job_skills=["React", "TypeScript", "Node"],
            job_requirements=["5+ years of front-end development.", "Expertise in React."],
            job_summary="Build the storefront experience for a commerce platform.",
        )
        self.assertNotEqual(insight.match, "strong")
        self.assertIn(insight.match, {"good", "potential"})

    def test_matching_uses_the_skill_list_not_prose_when_available(self):
        """Prose words must not inflate the skill signal."""

        insight = self._insight(
            job_title="Clinical Data Analyst",
            job_skills=["SQL", "Python", "Healthcare"],
            job_requirements=["Degree in statistics.", "Working knowledge of regulated datasets."],
        )
        self.assertEqual(insight.match, "potential")

    def test_adjacent_strong_skills_role_can_still_be_strong(self):
        """A differently titled role can be strong when the skills genuinely fit."""

        insight = self._insight(
            job_title="Design System Lead",
            job_skills=["Design systems", "Accessibility", "Documentation"],
            job_requirements=["Experience leading a design system."],
            # The profile lists both matching skills; the title is simply different.
            profile_sections={
                "skills": "Figma, Design systems, Accessibility, User research",
                "experience": "Senior Product Designer 2019 - Present",
                "education": "M.A. Interaction Design",
            },
        )
        self.assertEqual(insight.match, "strong")

    def test_skill_labels_preserve_original_wording(self):
        insight = self._insight(job_skills=["Figma", "Design systems"])
        detail = insight.cv_alignment[0].detail
        self.assertIn("Figma", detail)
        self.assertIn("Design systems", detail)

    def test_summary_prose_is_not_reported_as_a_missing_requirement(self):
        insight = self._insight(
            job_skills=["Figma"],
            job_requirements=[],
            job_summary="Join an ambitious team across Europe building digital products.",
        )
        missing_lines = [line for line in insight.cv_alignment if not line.positive]
        joined = " ".join(line.detail for line in missing_lines).lower()
        for prose_word in ("ambitious", "across", "digital"):
            self.assertNotIn(prose_word, joined)


# --------------------------------------------------------------------------- #
# Provider status, manual import and independent job actions                   #
# --------------------------------------------------------------------------- #


@platform_providers_disabled()
class ProviderStatusApiTests(APITestCase):
    """The API must be honest about which sources are actually connected."""

    def setUp(self):
        self.user = User.objects.create_user(email="providers@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

    def test_lists_every_provider_with_a_status(self):
        response = self.client.get(reverse("job-providers"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sources = {entry["source"] for entry in response.data}
        self.assertEqual(sources, {"linkedin", "stepstone", "stellenwerk", "manual"})

    def test_platform_providers_are_not_reported_as_operational(self):
        response = self.client.get(reverse("job-providers"))
        by_source = {entry["source"]: entry for entry in response.data}
        for name in ("linkedin", "stepstone", "stellenwerk"):
            with self.subTest(provider=name):
                self.assertFalse(by_source[name]["operational"])
                self.assertNotEqual(by_source[name]["status"], "ready")

    def test_manual_import_is_operational(self):
        response = self.client.get(reverse("job-providers"))
        manual = next(entry for entry in response.data if entry["source"] == "manual")
        self.assertTrue(manual["operational"])

    def test_each_provider_explains_itself(self):
        response = self.client.get(reverse("job-providers"))
        for entry in response.data:
            self.assertTrue(entry["detail"], entry["source"])
            self.assertTrue(entry["statusLabel"])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("job-providers")).status_code, 401)


class ManualImportApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="import@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)
        self.user.profile_sections.filter(key="skills").update(content="Python, Django")
        preferences = self.user.preferences
        preferences.desired_roles = ["Werkstudent Softwareentwicklung"]
        preferences.locations = ["Dortmund"]
        preferences.save()

    def _payload(self, **overrides):
        payload = {
            "url": "https://example.invalid/jobs/1",
            "title": "Werkstudent Softwareentwicklung (m/w/d)",
            "company": "Acme GmbH",
            "location": "Dortmund, Nordrhein-Westfalen",
            "employmentType": "working-student",
            "description": "Python und Django Entwicklung.",
            "notes": "Referred by a friend.",
        }
        payload.update(overrides)
        return payload

    def test_import_creates_a_job(self):
        response = self.client.post(reverse("job-import"), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["source"], "Manual")
        self.assertTrue(response.data["isUserProvided"])
        self.assertEqual(response.data["employmentType"], "working-student")

    def test_import_runs_matching(self):
        response = self.client.post(reverse("job-import"), self._payload(), format="json")
        analysis = response.data["analysis"]
        self.assertTrue(analysis["cvAlignment"])
        self.assertTrue(analysis["preferenceFit"])

    def test_import_normalizes_location(self):
        response = self.client.post(reverse("job-import"), self._payload(), format="json")
        self.assertEqual(response.data["city"], "Dortmund")
        self.assertEqual(response.data["region"], "Nordrhein-Westfalen")
        self.assertEqual(response.data["country"], "Germany")

    def test_import_classifies_from_the_description_when_no_type_given(self):
        response = self.client.post(
            reverse("job-import"),
            self._payload(employmentType="", title="Entwickler (m/w/d)", description="Wir suchen einen Werkstudenten."),
            format="json",
        )
        self.assertEqual(response.data["employmentType"], "working-student")

    def test_import_is_marked_as_user_provided(self):
        response = self.client.post(reverse("job-import"), self._payload(), format="json")
        job = Job.objects.get(pk=response.data["id"])
        self.assertTrue(job.is_user_provided)
        self.assertTrue(job.raw_source_data.get("user_provided"))

    def test_duplicate_import_is_rejected(self):
        self.client.post(reverse("job-import"), self._payload(), format="json")
        second = self.client.post(reverse("job-import"), self._payload(), format="json")
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)

    def test_title_is_required(self):
        response = self.client.post(reverse("job-import"), self._payload(title=""), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_url_is_optional(self):
        response = self.client.post(reverse("job-import"), self._payload(url=""), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_import_is_scoped_to_the_user(self):
        self.client.post(reverse("job-import"), self._payload(), format="json")
        other = User.objects.create_user(email="other-import@example.com", password=PASSWORD)
        self.assertFalse(Job.objects.filter(user=other).exists())

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(reverse("job-import"), self._payload(), format="json").status_code, 401
        )


class JobActionApiTests(APITestCase):
    """Review, save and dismiss must be independent of one another."""

    def setUp(self):
        self.user = User.objects.create_user(email="actions@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)
        self.job = make_job(self.user)

    def _post(self, name):
        return self.client.post(reverse(name, args=[self.job.id]))

    def test_review_sets_timestamp(self):
        response = self._post("job-review")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["reviewedAt"])
        self.assertEqual(response.data["status"], "reviewed")

    def test_save_sets_timestamp(self):
        response = self._post("job-save")
        self.assertIsNotNone(response.data["savedAt"])
        self.assertEqual(response.data["status"], "saved")

    def test_dismiss_sets_timestamp(self):
        response = self._post("job-dismiss")
        self.assertIsNotNone(response.data["dismissedAt"])
        self.assertEqual(response.data["status"], "dismissed")

    def test_saving_preserves_reviewed_state(self):
        self._post("job-review")
        response = self._post("job-save")
        self.assertIsNotNone(response.data["reviewedAt"])
        self.assertIsNotNone(response.data["savedAt"])

    def test_reviewing_preserves_saved_state(self):
        self._post("job-save")
        response = self._post("job-review")
        self.assertIsNotNone(response.data["savedAt"])
        self.assertIsNotNone(response.data["reviewedAt"])

    def test_dismissing_preserves_history(self):
        self._post("job-review")
        self._post("job-save")
        response = self._post("job-dismiss")
        self.assertIsNotNone(response.data["reviewedAt"])
        self.assertIsNotNone(response.data["savedAt"])
        self.assertIsNotNone(response.data["dismissedAt"])
        self.assertEqual(response.data["status"], "dismissed")

    def test_save_toggles_off(self):
        self._post("job-save")
        response = self._post("job-save")
        self.assertIsNone(response.data["savedAt"])
        self.assertEqual(response.data["status"], "new")

    def test_restore_clears_everything(self):
        self._post("job-review")
        self._post("job-save")
        self._post("job-dismiss")
        response = self._post("job-restore")
        self.assertIsNone(response.data["reviewedAt"])
        self.assertIsNone(response.data["savedAt"])
        self.assertIsNone(response.data["dismissedAt"])
        self.assertEqual(response.data["status"], "new")

    def test_actions_are_scoped_to_the_owner(self):
        other = User.objects.create_user(email="other-actions@example.com", password=PASSWORD)
        foreign = make_job(other, title="Not Yours", fingerprint="foreign-action-1")

        self.client.force_authenticate(self.user)
        response = self.client.post(reverse("job-save", args=[foreign.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        foreign.refresh_from_db()
        self.assertIsNone(foreign.saved_at)

    def test_one_users_action_does_not_affect_another(self):
        other = User.objects.create_user(email="other-actions2@example.com", password=PASSWORD)
        other_job = make_job(other, title="Other", fingerprint="other-action-1")

        self.client.force_authenticate(self.user)
        self._post("job-save")

        other_job.refresh_from_db()
        self.assertIsNone(other_job.saved_at)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self._post("job-save").status_code, 401)
