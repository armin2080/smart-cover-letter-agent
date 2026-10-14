"""Tests for authentication, profile, CV, preferences and notifications."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Profile, ProfileSection, User

VALID_PASSWORD = "test-pass-123"


class AuthTests(APITestCase):
    def test_register_creates_user_with_defaults_and_tokens(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "fullName": "Armin Keller",
                "email": "Armin@Example.com",
                "password": VALID_PASSWORD,
                "passwordConfirm": VALID_PASSWORD,
                "acceptedTerms": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("tokens", response.data)
        self.assertTrue(response.data["tokens"]["access"])
        self.assertEqual(response.data["user"]["email"], "armin@example.com")

        user = User.objects.get(email="armin@example.com")
        # Related rows are created by the post_save signal.
        self.assertTrue(hasattr(user, "profile"))
        self.assertTrue(hasattr(user, "preferences"))
        self.assertTrue(hasattr(user, "notification_settings"))
        self.assertEqual(user.profile_sections.count(), len(ProfileSection._meta.model._meta.get_field("key").choices))

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "fullName": "Armin",
                "email": "a@b.com",
                "password": VALID_PASSWORD,
                "passwordConfirm": "something-else",
                "acceptedTerms": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("passwordConfirm", str(response.data))

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="dup@example.com", password=VALID_PASSWORD)
        response = self.client.post(
            reverse("auth-register"),
            {
                "fullName": "Dup",
                "email": "dup@example.com",
                "password": VALID_PASSWORD,
                "passwordConfirm": VALID_PASSWORD,
                "acceptedTerms": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", str(response.data))

    def test_register_requires_terms(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "fullName": "Armin",
                "email": "terms@example.com",
                "password": VALID_PASSWORD,
                "passwordConfirm": VALID_PASSWORD,
                "acceptedTerms": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_and_me_roundtrip(self):
        User.objects.create_user(email="login@example.com", password=VALID_PASSWORD, full_name="Login User")

        response = self.client.post(
            reverse("auth-login"), {"email": "login@example.com", "password": VALID_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access = response.data["tokens"]["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get(reverse("auth-me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "login@example.com")
        self.assertEqual(me.data["fullName"], "Login User")

    def test_login_rejects_bad_credentials(self):
        User.objects.create_user(email="bad@example.com", password=VALID_PASSWORD)
        response = self.client.post(
            reverse("auth-login"), {"email": "bad@example.com", "password": "wrong"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_access_token(self):
        User.objects.create_user(email="refresh@example.com", password=VALID_PASSWORD)
        login = self.client.post(
            reverse("auth-login"), {"email": "refresh@example.com", "password": VALID_PASSWORD}, format="json"
        )
        refresh_token = login.data["tokens"]["refresh"]

        response = self.client.post(reverse("auth-refresh"), {"refresh": refresh_token}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_logout_blacklists_refresh_token(self):
        User.objects.create_user(email="logout@example.com", password=VALID_PASSWORD)
        login = self.client.post(
            reverse("auth-login"), {"email": "logout@example.com", "password": VALID_PASSWORD}, format="json"
        )
        access = login.data["tokens"]["access"]
        refresh = login.data["tokens"]["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(reverse("auth-logout"), {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        # The blacklisted refresh token can no longer be used.
        self.client.credentials()
        reuse = self.client.post(reverse("auth-refresh"), {"refresh": refresh}, format="json")
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_account_changes_name_and_password(self):
        user = User.objects.create_user(email="patch@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(user)

        response = self.client.patch(
            reverse("auth-me"),
            {
                "fullName": "New Name",
                "currentPassword": VALID_PASSWORD,
                "newPassword": "brand-new-pass-456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertEqual(user.full_name, "New Name")
        self.assertTrue(user.check_password("brand-new-pass-456"))

    def test_update_account_rejects_wrong_current_password(self):
        user = User.objects.create_user(email="wrongpw@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(user)

        response = self.client.patch(
            reverse("auth-me"),
            {"currentPassword": "not-the-password", "newPassword": "brand-new-pass-456"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="profile@example.com", password=VALID_PASSWORD, full_name="Profile User"
        )
        self.client.force_authenticate(self.user)

    def test_get_profile_returns_sections_and_contact(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fullName"], "Profile User")
        self.assertEqual(response.data["email"], "profile@example.com")
        self.assertEqual(len(response.data["sections"]), 8)
        self.assertIsNone(response.data["cv"])

    def test_patch_profile_updates_user_and_profile(self):
        response = self.client.patch(
            reverse("profile"),
            {"phone": "+49 30 000", "location": "Berlin", "summary": "Designer.", "fullName": "Renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+49 30 000")
        self.assertEqual(response.data["fullName"], "Renamed")

        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Renamed")

    def test_update_section_by_key(self):
        response = self.client.patch(
            reverse("profile-section", kwargs={"section_id": "skills"}),
            {"content": "Figma, Python"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        section = self.user.profile_sections.get(key="skills")
        self.assertEqual(section.content, "Figma, Python")

    def test_update_missing_section_returns_404(self):
        response = self.client.patch(
            reverse("profile-section", kwargs={"section_id": "nope"}), {"content": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_rejects_unsupported_extension(self):
        upload = SimpleUploadedFile("cv.txt", b"hello", content_type="text/plain")
        response = self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)

    def test_upload_requires_a_file(self):
        response = self.client.post(reverse("profile-cv"), {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_pdf_succeeds_and_only_one_cv_is_kept(self):
        # A minimal but structurally valid PDF is not required: extraction is
        # best-effort and failure must not break the upload.
        upload = SimpleUploadedFile("cv.pdf", b"%PDF-1.4\n%stub\n", content_type="application/pdf")
        response = self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["fileName"], "cv.pdf")

        second = SimpleUploadedFile("cv2.pdf", b"%PDF-1.4\n%stub2\n", content_type="application/pdf")
        self.client.post(reverse("profile-cv"), {"file": second}, format="multipart")

        self.assertEqual(self.user.cv_documents.count(), 1)
        self.assertEqual(self.user.cv_documents.first().file_name, "cv2.pdf")

    def test_delete_cv(self):
        upload = SimpleUploadedFile("cv.pdf", b"%PDF-1.4\n", content_type="application/pdf")
        self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")

        response = self.client.delete(reverse("profile-cv"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.user.cv_documents.count(), 0)


class CvExtractionTests(APITestCase):
    """Uploading a real document must populate the profile sections."""

    def setUp(self):
        self.user = User.objects.create_user(email="cv@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(self.user)

    @staticmethod
    def build_docx() -> bytes:
        """Create a DOCX with recognisable section headings and content."""

        import docx
        from io import BytesIO

        document = docx.Document()
        for line in (
            "Alex Rivera",
            "alex.rivera@example.com | +49 30 1234567 | Berlin, Germany",
            "",
            "Professional Summary",
            "Backend engineer with 6 years building data-heavy services.",
            "",
            "Skills",
            "Python, Django, PostgreSQL, Docker",
            "",
            "Education",
            "B.Sc. Computer Science, TU Berlin 2018",
        ):
            document.add_paragraph(line)

        buffer = BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    def test_docx_upload_extracts_sections_and_contact(self):
        upload = SimpleUploadedFile(
            "alex-rivera.docx",
            self.build_docx(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "ready")

        sections = {section.key: section.content for section in self.user.profile_sections.all()}
        self.assertIn("Python", sections["skills"])
        self.assertIn("TU Berlin", sections["education"])
        self.assertIn("Backend engineer", sections["summary"])

        # Re-read the profile: the request ran in a separate instance, and the
        # post_save signal cached `user.profile` on this test's object.
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.phone, "+49 30 1234567")
        self.assertIn("Backend engineer", profile.summary)

    def test_upload_does_not_overwrite_the_account_email(self):
        upload = SimpleUploadedFile(
            "cv.docx",
            self.build_docx(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")

        self.user.refresh_from_db()
        # The CV contains alex.rivera@example.com, but the account email is authoritative.
        self.assertEqual(self.user.email, "cv@example.com")

    def test_unextractable_document_still_reports_ready(self):
        """A malformed document must not fail the upload."""

        upload = SimpleUploadedFile(
            "broken.docx", b"this is not a real docx", content_type="application/octet-stream"
        )
        response = self.client.post(reverse("profile-cv"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(response.data["status"], {"ready", "error"})

    def test_parser_maps_known_headings(self):
        from .cv_parser import parse_sections

        text = (
            "Alex Rivera\n\n"
            "Work Experience\nSenior Engineer at Acme 2020 - Present\n\n"
            "Skills\nPython, Django\n"
        )
        sections = parse_sections(text)
        self.assertIn("experience", sections)
        self.assertIn("skills", sections)
        self.assertIn("Acme", sections["experience"])


class PreferencesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="prefs@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(self.user)

    def test_get_defaults(self):
        response = self.client.get(reverse("profile-preferences"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["radiusKm"], 50)
        self.assertEqual(response.data["employmentTypes"], ["full-time"])

    def test_put_replaces_preferences_and_deduplicates(self):
        payload = {
            "desiredRoles": ["Product Designer", "Product Designer", "UX Designer"],
            "locations": ["Berlin"],
            "radiusKm": 25,
            "employmentTypes": ["part-time"],
            "sources": ["LinkedIn"],
            "keywords": ["SaaS"],
        }
        response = self.client.put(reverse("profile-preferences"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["desiredRoles"], ["Product Designer", "UX Designer"])
        self.assertEqual(response.data["radiusKm"], 25)

    def test_rejects_invalid_employment_type(self):
        response = self.client.put(
            reverse("profile-preferences"),
            {"employmentTypes": ["not-a-real-type"], "desiredRoles": [], "locations": [], "radiusKm": 10,
             "sources": [], "keywords": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="notif@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(self.user)

    def test_defaults_are_enabled(self):
        response = self.client.get(reverse("settings-notifications"))
        self.assertEqual(response.data, {"newMatches": True, "searchCompleted": True, "searchFailures": True})

    def test_partial_update(self):
        response = self.client.put(reverse("settings-notifications"), {"newMatches": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["newMatches"])
        self.assertTrue(response.data["searchCompleted"])


class AccountDeletionTests(APITestCase):
    def test_delete_account_removes_user(self):
        user = User.objects.create_user(email="delete@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(user)

        response = self.client.delete(reverse("account-delete"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(email="delete@example.com").exists())
