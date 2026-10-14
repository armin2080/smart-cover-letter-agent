"""Tests for cover letter generation, editing and PDF export."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from jobs.models import ActivityEntry, Job, job_fingerprint

from .models import CoverLetter
from .services import build_grounded_letter, generate

User = get_user_model()
PASSWORD = "test-pass-123"


def make_job(user, title="Product Designer", company="Northstar Labs", **overrides) -> Job:
    defaults = {
        "title": title,
        "company": company,
        "location": "Berlin, Germany",
        "employment_type": "full-time",
        "posted_at": timezone.now(),
        "source": "LinkedIn",
        "source_url": f"https://example.com/{title}",
        "match": Job.Match.STRONG,
        "skills": ["Figma", "Design systems"],
        "requirements": ["3+ years of experience"],
        "summary": "Design thoughtful products.",
        "fingerprint": job_fingerprint("LinkedIn", f"https://example.com/{title}", title, company),
    }
    defaults.update(overrides)
    return Job.objects.create(user=user, **defaults)


class GroundedGenerationTests(APITestCase):
    """The offline fallback must never invent facts."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="grounded@example.com", password=PASSWORD, full_name="Armin Keller"
        )
        self.user.profile_sections.filter(key="skills").update(content="Figma, Design systems, User research")
        self.user.profile_sections.filter(key="experience").update(
            content="Senior Product Designer at Studio Nord · 2021 - Present"
        )
        self.job = make_job(self.user)

    def test_generation_uses_grounded_template_without_api_key(self):
        with override_settings(GROQ_API_KEY=""):
            content, generator = generate(self.user, self.job, "English", "professional", "balanced")
        self.assertEqual(generator, "grounded-template")
        self.assertTrue(content.strip())

    def test_letter_contains_only_real_profile_facts(self):
        with override_settings(GROQ_API_KEY=""):
            content, _ = generate(self.user, self.job, "English", "professional", "balanced")

        self.assertIn("Armin Keller", content)
        self.assertIn("Figma", content)
        self.assertIn("Northstar Labs", content)
        self.assertIn("Product Designer", content)

        # No fabricated metrics, percentages or date claims.
        for forbidden in ("22%", "40,000", "increased", "grew by"):
            self.assertNotIn(forbidden, content)

    def test_letter_is_addressed_to_the_company(self):
        with override_settings(GROQ_API_KEY=""):
            content, _ = generate(self.user, self.job, "English", "professional", "balanced")
        self.assertTrue(content.startswith("Dear Northstar Labs Hiring Team,"))

    def test_german_language_produces_german_greeting(self):
        with override_settings(GROQ_API_KEY=""):
            content, _ = generate(self.user, self.job, "German", "professional", "balanced")
        self.assertIn("Sehr geehrtes Team", content)
        self.assertIn("Mit freundlichen Grüßen", content)

    def test_empty_profile_still_produces_a_valid_letter(self):
        self.user.profile_sections.all().update(content="")
        with override_settings(GROQ_API_KEY=""):
            content, _ = generate(self.user, self.job, "English", "professional", "balanced")
        self.assertTrue(content.strip())
        self.assertIn("Sincerely", content)

    def test_instructions_are_recorded_not_fabricated(self):
        profile = {
            "full_name": "Armin Keller",
            "email": "a@b.com",
            "phone": "",
            "location": "",
            "portfolio": "",
            "summary": "",
            "skills": "",
            "experience": "",
            "education": "",
            "projects": "",
            "languages": "",
            "certificates": "",
        }
        job = {
            "title": "Designer",
            "company": "Acme",
            "location": "",
            "employment_type": "",
            "source": "",
            "source_url": "",
            "summary": "",
            "responsibilities": [],
            "requirements": [],
            "skills": [],
        }
        content = build_grounded_letter(profile, job, "English", "Emphasise design systems")
        self.assertIn("Applied instruction: Emphasise design systems", content)

    def test_unknown_requirements_are_acknowledged_as_gaps(self):
        profile = {
            "full_name": "Armin Keller",
            "email": "",
            "phone": "",
            "location": "",
            "portfolio": "",
            "summary": "",
            "skills": "Figma",
            "experience": "",
            "education": "",
            "projects": "",
            "languages": "",
            "certificates": "",
        }
        job = {
            "title": "Engineer",
            "company": "Acme",
            "location": "",
            "employment_type": "",
            "source": "",
            "source_url": "",
            "summary": "",
            "responsibilities": [],
            "requirements": ["kubernetes"],
            "skills": [],
        }
        content = build_grounded_letter(profile, job, "English")
        self.assertIn("not yet evidenced", content)


class CoverLetterApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="cover@example.com", password=PASSWORD, full_name="Armin Keller"
        )
        self.other = User.objects.create_user(email="other-cover@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

        self.user.profile_sections.filter(key="skills").update(content="Figma, Design systems")
        self.job = make_job(self.user)
        self.foreign_job = make_job(self.other, title="Other Job")

        self.groq_off = override_settings(GROQ_API_KEY="")
        self.groq_off.enable()

    def tearDown(self):
        self.groq_off.disable()

    # -- preview ---------------------------------------------------------- #

    def test_preview_returns_job_and_cv_label(self):
        response = self.client.get(reverse("cover-letter-preview"), {"job": self.job.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["job"]["id"], self.job.id)
        self.assertEqual(response.data["cvLabel"], "No CV uploaded")
        self.assertEqual(response.data["language"], "English")

    def test_preview_requires_a_valid_job(self):
        self.assertEqual(
            self.client.get(reverse("cover-letter-preview"), {"job": "abc"}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get(reverse("cover-letter-preview"), {"job": self.foreign_job.id}).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # -- lookup ----------------------------------------------------------- #

    def test_for_job_returns_null_when_absent(self):
        response = self.client.get(reverse("cover-letter-list-create"), {"job": self.job.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    # -- generate --------------------------------------------------------- #

    def test_generate_creates_letter_and_marks_the_job(self):
        response = self.client.post(
            reverse("cover-letter-list-create"),
            {"jobId": self.job.id, "language": "English", "tone": "professional", "length": "balanced"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["jobId"], self.job.id)
        self.assertTrue(response.data["content"])

        self.job.refresh_from_db()
        self.assertTrue(self.job.has_cover_letter)
        self.assertTrue(ActivityEntry.objects.filter(user=self.user, kind="cover-letter").exists())

    def test_generate_serialises_camel_case_contract(self):
        self.client.post(reverse("cover-letter-list-create"), {"jobId": self.job.id}, format="json")
        response = self.client.get(reverse("cover-letter-list-create"), {"job": self.job.id})
        for key in ("id", "jobId", "content", "language", "tone", "length", "status", "updatedAt", "savedAt"):
            self.assertIn(key, response.data)

    def test_generate_twice_updates_in_place(self):
        first = self.client.post(
            reverse("cover-letter-list-create"), {"jobId": self.job.id}, format="json"
        )
        second = self.client.post(
            reverse("cover-letter-list-create"),
            {"jobId": self.job.id, "tone": "warm"},
            format="json",
        )
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second.data["tone"], "warm")
        self.assertEqual(CoverLetter.objects.filter(user=self.user).count(), 1)

    def test_generate_rejects_another_users_job(self):
        response = self.client.post(
            reverse("cover-letter-list-create"), {"jobId": self.foreign_job.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- edit and save ---------------------------------------------------- #

    def _generate(self):
        return self.client.post(reverse("cover-letter-list-create"), {"jobId": self.job.id}, format="json")

    def test_patch_saves_content_and_marks_saved(self):
        letter_id = self._generate().data["id"]

        response = self.client.patch(
            reverse("cover-letter-detail", args=[letter_id]),
            {"content": "Dear team,\n\nEdited body."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "saved")
        self.assertIsNotNone(response.data["savedAt"])
        self.assertIn("Edited body", response.data["content"])

    def test_regenerate_replaces_content_and_clears_saved(self):
        letter_id = self._generate().data["id"]
        self.client.patch(
            reverse("cover-letter-detail", args=[letter_id]), {"content": "edited"}, format="json"
        )

        response = self.client.post(
            reverse("cover-letter-regenerate", args=[letter_id]),
            {"tone": "confident"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "draft")
        self.assertIsNone(response.data["savedAt"])
        self.assertEqual(response.data["tone"], "confident")

    def test_cannot_access_another_users_letter(self):
        other_job = make_job(self.other, title="Foreign")
        letter = CoverLetter.objects.create(user=self.other, job=other_job, content="secret")

        self.assertEqual(
            self.client.get(reverse("cover-letter-detail", args=[letter.id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(reverse("cover-letter-pdf", args=[letter.id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # -- pdf -------------------------------------------------------------- #

    def test_pdf_returns_valid_pdf_bytes(self):
        letter_id = self._generate().data["id"]

        response = self.client.get(reverse("cover-letter-pdf", args=[letter_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")

        payload = b"".join(response.streaming_content) if response.streaming else response.content
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", payload)
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_all_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(reverse("cover-letter-list-create")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
