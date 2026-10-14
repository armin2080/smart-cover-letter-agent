"""Tests for search runs, the pipeline runner and automatic-search settings.

Every test is hermetic: `SEARCH_RUN_ASYNC=False` runs searches inline, and the
sample-data path is used so no third-party request is ever made.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from config.testkit import platform_providers_disabled
from jobs.models import ActivityEntry, Job
from jobs.sources.base import EmploymentType

from .models import AutoSearchSettings, SearchRun, compute_next_run
from .runner import (
    build_stages,
    criteria_from_preferences,
    execute_search_sync,
    set_pacing,
    summarise_criteria,
)

User = get_user_model()
PASSWORD = "test-pass-123"


def run_sync(run: SearchRun) -> SearchRun:
    set_pacing(0)
    execute_search_sync(run.id)
    run.refresh_from_db()
    return run


class CriteriaSummaryTests(APITestCase):
    def test_summary_uses_roles_location_and_radius(self):
        summary = summarise_criteria({"roles": ["Designer"], "locations": ["Berlin"], "radius_km": 25})
        self.assertEqual(summary, "Designer · Berlin · 25 km")

    def test_summary_falls_back_when_empty(self):
        self.assertEqual(summarise_criteria({}), "Profile preferences")

    def test_criteria_from_preferences(self):
        user = User.objects.create_user(email="crit@example.com", password=PASSWORD)
        preferences = user.preferences
        preferences.desired_roles = ["Data Analyst"]
        preferences.locations = ["Munich"]
        preferences.save()

        criteria = criteria_from_preferences(user, sources=["linkedin"])
        self.assertEqual(criteria["roles"], ["Data Analyst"])
        self.assertEqual(criteria["locations"], ["Munich"])
        self.assertEqual(criteria["sources"], ["linkedin"])


@platform_providers_disabled()
class AutoSearchScheduleTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="auto@example.com", password=PASSWORD)
        self.auto = AutoSearchSettings.objects.get_or_create(user=self.user)[0]

    def test_daily_next_run_is_within_a_day(self):
        self.auto.frequency = AutoSearchSettings.Frequency.DAILY
        self.auto.time_of_day = "08:30"
        next_run = compute_next_run(self.auto)
        self.assertGreater(next_run, timezone.now())
        self.assertLessEqual(next_run - timezone.now(), timedelta(days=1))

    def test_weekly_next_run_lands_on_requested_weekday(self):
        self.auto.frequency = AutoSearchSettings.Frequency.WEEKLY
        self.auto.weekday = 2
        self.assertEqual(compute_next_run(self.auto).weekday(), 2)

    def test_disabling_clears_next_run(self):
        self.auto.enabled = False
        self.auto.save()
        self.auto.refresh_from_db()
        self.assertIsNone(self.auto.next_run_at)
        self.assertEqual(self.auto.status, AutoSearchSettings.Status.PAUSED)

    def test_error_status_when_a_failure_is_recorded(self):
        self.auto.last_error = "LinkedIn timed out"
        self.auto.save()
        self.assertEqual(self.auto.status, AutoSearchSettings.Status.ERROR)


@platform_providers_disabled()
class SearchRunApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="search@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

        for key, content in {
            "skills": "Python, Django, PostgreSQL, Docker, REST",
            "experience": "Backend Developer 2020 - Present",
            "education": "B.Sc. Computer Science",
        }.items():
            self.user.profile_sections.filter(key=key).update(content=content)

        preferences = self.user.preferences
        preferences.desired_roles = ["Werkstudent Softwareentwicklung"]
        preferences.locations = ["Dortmund"]
        preferences.employment_types = ["working-student", "full-time"]
        preferences.sources = ["linkedin", "stepstone", "stellenwerk"]
        preferences.keywords = ["python"]
        preferences.save()

        self.override = override_settings(SEARCH_RUN_ASYNC=False, SAMPLE_DATA_ENABLED=True)
        self.override.enable()
        set_pacing(0)

    def tearDown(self):
        self.override.disable()

    def _start(self, **overrides):
        payload = {
            "roles": ["Werkstudent Softwareentwicklung"],
            "locations": ["Dortmund"],
            "radiusKm": 40,
            "employmentTypes": ["working-student", "full-time"],
            "sources": ["linkedin", "stepstone", "stellenwerk"],
            "keywords": ["python"],
            "useSavedPreferences": False,
        }
        payload.update(overrides)
        response = self.client.post(reverse("search-list-create"), payload, format="json")
        return response, SearchRun.objects.get(pk=response.data["id"])

    def test_start_creates_run_with_five_stages(self):
        response, _ = self._start()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["mode"], "manual")
        self.assertEqual(len(response.data["stages"]), 5)

    def test_run_completes_with_all_stages_done(self):
        _, run = self._start()
        self.assertEqual(run.status, SearchRun.Status.COMPLETED)
        self.assertTrue(all(stage["state"] == "done" for stage in run.stages))
        self.assertGreater(run.discovered, 0)

    def test_run_persists_jobs_with_normalized_fields(self):
        _, run = self._start()

        # `discovered` counts listings found; the employment filter then removes
        # roles that do not match the request, so fewer are persisted.
        jobs = Job.objects.filter(user=self.user)
        self.assertGreater(jobs.count(), 0)
        self.assertLessEqual(jobs.count(), run.discovered)

        sample = jobs.first()
        self.assertTrue(sample.city or sample.location)
        self.assertEqual(sample.country, "Germany")
        self.assertIn(sample.employment_type, {choice.value for choice in Job.EmploymentType})

    def test_persisted_jobs_respect_the_employment_filter(self):
        self._start(employmentTypes=["working-student"])
        jobs = Job.objects.filter(user=self.user)
        self.assertTrue(jobs.exists())
        allowed = {"working-student", "student-assistant", "unknown"}
        for job in jobs:
            self.assertIn(job.employment_type, allowed, f"{job.title} was {job.employment_type}")

    def test_run_records_classification_evidence(self):
        self._start()
        job = Job.objects.filter(user=self.user, employment_type="working-student").first()
        self.assertIsNotNone(job, "the sample data includes working-student roles")
        self.assertTrue(job.employment_type_evidence)

    def test_run_reports_that_no_authorized_source_was_available(self):
        _, run = self._start()
        self.assertIn("authorization", (run.error or "").lower())

    def test_second_identical_run_does_not_duplicate_jobs(self):
        self._start()
        count_after_first = Job.objects.filter(user=self.user).count()
        self._start()
        self.assertEqual(Job.objects.filter(user=self.user).count(), count_after_first)

    def test_run_records_activity(self):
        self._start()
        self.assertTrue(ActivityEntry.objects.filter(user=self.user, kind="discovered").exists())

    def test_run_is_scoped_to_the_requesting_user(self):
        other = User.objects.create_user(email="other-search@example.com", password=PASSWORD)
        run = SearchRun.objects.create(user=other, criteria={}, sources=[], stages=build_stages())
        response = self.client.get(reverse("search-detail", args=[run.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_is_paginated(self):
        response = self.client.get(reverse("search-list-create"))
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)

    def test_cancel_marks_run_failed(self):
        run = SearchRun.objects.create(
            user=self.user,
            status=SearchRun.Status.RUNNING,
            criteria={},
            sources=[],
            stages=build_stages(),
        )
        response = self.client.post(reverse("search-cancel", args=[run.id]))
        self.assertEqual(response.data["status"], "failed")
        self.assertEqual(response.data["error"], "Search cancelled.")

    def test_gaps_are_filled_from_saved_preferences(self):
        response = self.client.post(reverse("search-list-create"), {}, format="json")
        run = SearchRun.objects.get(pk=response.data["id"])
        self.assertEqual(run.criteria["roles"], ["Werkstudent Softwareentwicklung"])
        self.assertEqual(run.criteria["locations"], ["Dortmund"])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(reverse("search-list-create"), {}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class AutoSearchSettingsApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="autosettings@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

    def test_get_creates_defaults_with_schedule(self):
        response = self.client.get(reverse("search-settings"))
        self.assertTrue(response.data["enabled"])
        self.assertIsNotNone(response.data["nextRunAt"])

    def test_put_updates_frequency_and_time(self):
        response = self.client.put(
            reverse("search-settings"),
            {"frequency": "weekly", "timeOfDay": "07:15", "weekday": 4},
            format="json",
        )
        self.assertEqual(response.data["timeOfDay"], "07:15")
        self.assertEqual(response.data["weekday"], 4)

    def test_rejects_invalid_time_format(self):
        response = self.client.put(reverse("search-settings"), {"timeOfDay": "25:99"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pausing_reports_paused_status(self):
        response = self.client.put(reverse("search-settings"), {"enabled": False}, format="json")
        self.assertEqual(response.data["status"], "paused")
        self.assertIsNone(response.data["nextRunAt"])

    def test_settings_disclose_whether_a_scheduler_is_running(self):
        """`enabled` records intent; it does not start anything.

        The application cannot schedule itself, so the UI needs to know whether
        an external scheduler is set up before it counts down to a next run.
        """

        with override_settings(AUTO_SEARCH_SCHEDULER_ENABLED=False):
            self.assertFalse(self.client.get(reverse("search-settings")).data["schedulerActive"])

        with override_settings(AUTO_SEARCH_SCHEDULER_ENABLED=True):
            self.assertTrue(self.client.get(reverse("search-settings")).data["schedulerActive"])

    def test_next_run_is_computed_even_without_a_scheduler(self):
        """The intended time is still worth reporting; it is just not a promise.

        `schedulerActive` is what distinguishes the two readings, so this stays
        populated either way.
        """

        with override_settings(AUTO_SEARCH_SCHEDULER_ENABLED=False):
            response = self.client.get(reverse("search-settings"))

        self.assertIsNotNone(response.data["nextRunAt"])
        self.assertFalse(response.data["schedulerActive"])


class RunnerRobustnessTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="runner@example.com", password=PASSWORD)
        self.override = override_settings(SEARCH_RUN_ASYNC=False)
        self.override.enable()
        set_pacing(0)

    def tearDown(self):
        self.override.disable()

    def test_runner_records_failure_when_a_stage_raises(self):
        run = SearchRun.objects.create(user=self.user, criteria={}, sources=[], stages=build_stages())

        import searches.runner as runner_module

        original = runner_module.run_pipeline

        def boom(*args, **kwargs):
            raise RuntimeError("pipeline exploded")

        runner_module.run_pipeline = boom
        try:
            with override_settings(PROVIDER_LINKEDIN_ENABLED=True, PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE="DOC-1"):
                run = SearchRun.objects.create(
                    user=self.user,
                    criteria={},
                    sources=["linkedin"],
                    stages=build_stages(),
                )
                run_sync(run)
        finally:
            runner_module.run_pipeline = original

        run.refresh_from_db()
        self.assertEqual(run.status, SearchRun.Status.FAILED)
        self.assertIn("pipeline exploded", run.error)

    def test_stage_details_are_populated(self):
        run = SearchRun.objects.create(
            user=self.user,
            criteria={"roles": ["Werkstudent"], "locations": ["Dortmund"]},
            sources=[],
            stages=build_stages(),
        )
        run = run_sync(run)
        details = [stage["detail"] for stage in run.stages]
        self.assertTrue(all(detail for detail in details), details)

    def test_employment_filter_is_applied_to_results(self):
        """A working-student-only search must not return unrelated roles."""

        run = SearchRun.objects.create(
            user=self.user,
            criteria={
                "roles": ["Softwareentwicklung"],
                "locations": ["Dortmund"],
                "employment_types": ["working-student"],
            },
            sources=[],
            stages=build_stages(),
        )
        run_sync(run)

        jobs = Job.objects.filter(user=self.user)
        self.assertTrue(jobs.exists())
        allowed = {
            EmploymentType.WORKING_STUDENT.value,
            EmploymentType.STUDENT_ASSISTANT.value,
            EmploymentType.UNKNOWN.value,
        }
        for job in jobs:
            self.assertIn(job.employment_type, allowed, f"{job.title} was {job.employment_type}")
