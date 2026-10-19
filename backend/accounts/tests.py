"""Tests for authentication, profile, CV, preferences and notifications."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from unittest.mock import patch

from .models import Profile, ProfileSection, User

VALID_PASSWORD = "test-pass-123"


def registration_open():
    """Enable self-service signup for tests that exercise the signup flow.

    Registration is off by default, so a test about *how* registration behaves
    has to state that precondition explicitly. The closed-by-default behaviour
    has its own class below.
    """

    return override_settings(REGISTRATION_ENABLED=True)


class AuthRateLimitTests(APITestCase):
    """The credential endpoints must be rate limited.

    A single password check costs ~1.5s of CPU on the production host, so an
    unthrottled login route lets anyone occupy the core that a more important
    service also runs on. These tests assert the limits exist and apply on the
    axes that matter.

    Rates are patched on the classes directly rather than through
    `override_settings`: DRF binds `THROTTLE_RATES` at class-definition time, so
    a settings override would silently have no effect and the test would pass
    without proving anything.
    """

    def setUp(self):
        from django.core.cache import caches

        caches["throttle"].clear()
        User.objects.create_user(
            email="target@example.com", password=VALID_PASSWORD, full_name="Target"
        )
        self._originals = []

    def tearDown(self):
        """Restore every patched attribute and clear the counters.

        All three attributes are restored, not just `rate`: leaving a modified
        `num_requests` or `duration` behind would leak into whichever test class
        runs next and produce confusing failures far from the cause.
        """

        from django.core.cache import caches

        for cls, attrs in self._originals:
            for name, value in attrs.items():
                setattr(cls, name, value)
        caches["throttle"].clear()

    def _set_rate(self, cls, rate: str):
        """Pin one throttle's rate, recording the originals for restoration.

        `parse_rate` is an instance method in DRF, so an instance is used to
        convert the rate string — keeping the parsing in DRF's hands rather
        than duplicating its format here.
        """

        self._originals.append(
            (
                cls,
                {
                    "rate": getattr(cls, "rate", None),
                    "num_requests": getattr(cls, "num_requests", None),
                    "duration": getattr(cls, "duration", None),
                },
            )
        )
        cls.rate = rate
        cls.num_requests, cls.duration = cls().parse_rate(rate)

    def _login(self, email: str = "target@example.com", password: str = "wrong"):
        return self.client.post(
            reverse("auth-login"), {"email": email, "password": password}, format="json"
        )

    def test_login_is_rate_limited(self):
        from config.throttling import AuthBurstThrottle

        self._set_rate(AuthBurstThrottle, "3/min")

        codes = [self._login().status_code for _ in range(5)]
        self.assertEqual(codes[:3], [status.HTTP_400_BAD_REQUEST] * 3)
        self.assertEqual(codes[3:], [status.HTTP_429_TOO_MANY_REQUESTS] * 2)

    def test_a_blocked_attempt_is_rejected_before_the_password_check(self):
        """The limit must save CPU, not merely report a limit.

        DRF checks throttles in `initial()`, before the handler runs. If that
        ever regressed, the endpoint would still answer 429 while doing the
        expensive work first — which is the whole thing we are preventing.
        """

        from config.throttling import AuthBurstThrottle

        self._set_rate(AuthBurstThrottle, "2/min")

        self._login()
        self._login()

        with patch(
            "django.contrib.auth.hashers.check_password",
            side_effect=AssertionError("password hashing ran despite the throttle"),
        ):
            response = self._login()

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_limits_apply_per_targeted_account(self):
        """A distributed attempt on one account must still be capped.

        The IP throttles are disabled here so this measures the identity
        throttle alone — otherwise a passing test could just be the IP limit
        firing, which would prove nothing about per-account isolation.
        """

        from config.throttling import (
            AuthBurstThrottle,
            AuthSustainedThrottle,
            LoginIdentityThrottle,
        )

        self._set_rate(AuthBurstThrottle, "1000/min")
        self._set_rate(AuthSustainedThrottle, "1000/hour")
        self._set_rate(LoginIdentityThrottle, "2/hour")

        codes = [self._login().status_code for _ in range(4)]
        self.assertEqual(codes[:2], [status.HTTP_400_BAD_REQUEST] * 2)
        self.assertEqual(codes[2:], [status.HTTP_429_TOO_MANY_REQUESTS] * 2)

    def test_one_account_being_attacked_does_not_block_another(self):
        """Per-account keying must not become a shared lock."""

        from config.throttling import (
            AuthBurstThrottle,
            AuthSustainedThrottle,
            LoginIdentityThrottle,
        )

        self._set_rate(AuthBurstThrottle, "1000/min")
        self._set_rate(AuthSustainedThrottle, "1000/hour")
        self._set_rate(LoginIdentityThrottle, "2/hour")

        for _ in range(2):
            self._login(email="target@example.com")
        self.assertEqual(self._login(email="target@example.com").status_code, 429)

        # A different account, same client, must still be served.
        self.assertEqual(
            self._login(email="someone.else@example.com").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_the_identity_throttle_does_not_store_the_raw_email(self):
        """A cache dump must not read as a list of targeted accounts."""

        from config.throttling import LoginIdentityThrottle

        class _Request:
            data = {"email": "Target@Example.com"}

        key = LoginIdentityThrottle().get_cache_key(_Request(), None)
        self.assertIsNotNone(key)
        self.assertNotIn("target", key.lower())
        self.assertNotIn("@", key)

    def test_the_same_account_hashes_to_the_same_key(self):
        from config.throttling import LoginIdentityThrottle

        def key_for(email):
            class _Request:
                data = {"email": email}

            return LoginIdentityThrottle().get_cache_key(_Request(), None)

        self.assertEqual(key_for("a@b.com"), key_for("A@B.com"))
        self.assertNotEqual(key_for("a@b.com"), key_for("c@d.com"))

    def test_refresh_is_rate_limited(self):
        from config.throttling import AuthSustainedThrottle

        self._set_rate(AuthSustainedThrottle, "2/hour")

        codes = [
            self.client.post(reverse("auth-refresh"), {"refresh": "not-a-token"}, format="json").status_code
            for _ in range(4)
        ]
        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codes)

    def test_the_shipped_limits_are_configured(self):
        """Guards against the rates being dropped from settings."""

        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("auth-burst", "auth-sustained", "auth-identity"):
            self.assertIn(scope, rates)
            self.assertTrue(rates[scope])


@registration_open()
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


class RegistrationGateTests(APITestCase):
    """Self-service registration is closed unless it is switched on.

    The pilot is invitation-only: accounts are created deliberately through the
    admin panel, and an open signup form would let anyone who finds the URL in.
    These tests run with the shipped defaults, so they fail if that default is
    ever changed to allow open signup.
    """

    PAYLOAD = {
        "fullName": "Curious Visitor",
        "email": "visitor@example.com",
        "password": VALID_PASSWORD,
        "passwordConfirm": VALID_PASSWORD,
        "acceptedTerms": True,
    }

    def test_registration_is_disabled_by_default(self):
        from django.conf import settings

        self.assertFalse(settings.REGISTRATION_ENABLED)

    def test_register_is_refused_when_disabled(self):
        response = self.client.post(reverse("auth-register"), self.PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "registration_disabled")
        self.assertFalse(User.objects.filter(email="visitor@example.com").exists())

    def test_register_returns_no_tokens_when_disabled(self):
        response = self.client.post(reverse("auth-register"), self.PAYLOAD, format="json")
        self.assertNotIn("tokens", response.data)

    def test_register_succeeds_when_enabled(self):
        with override_settings(REGISTRATION_ENABLED=True):
            response = self.client.post(reverse("auth-register"), self.PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="visitor@example.com").exists())

    def test_config_endpoint_is_public_and_reports_the_flag(self):
        response = self.client.get(reverse("public-config"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["registrationEnabled"])

    def test_config_endpoint_reflects_the_enabled_state(self):
        with override_settings(REGISTRATION_ENABLED=True):
            response = self.client.get(reverse("public-config"))

        self.assertTrue(response.data["registrationEnabled"])

    def test_config_endpoint_needs_no_authentication(self):
        """The login screen has to read it before any session exists."""

        response = self.client.get(reverse("public-config"))
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_config_exposes_nothing_beyond_the_public_flag(self):
        response = self.client.get(reverse("public-config"))
        self.assertEqual(set(response.data), {"registrationEnabled"})

    def test_login_still_works_while_registration_is_closed(self):
        """Closing signup must not lock existing users out."""

        User.objects.create_user(email="existing@example.com", password=VALID_PASSWORD)
        response = self.client.post(
            reverse("auth-login"),
            {"email": "existing@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tokens", response.data)


class TourStateTests(APITestCase):
    """The guided tour is offered once per account.

    State lives on the account, not in browser storage, so signing in from a
    second device does not replay it.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="tour@example.com", password=VALID_PASSWORD, full_name="Tour User"
        )
        self.client.force_authenticate(self.user)

    def test_new_account_has_not_seen_the_tour(self):
        response = self.client.get(reverse("auth-me"))
        self.assertIsNone(response.data["tourCompletedAt"])

    def test_marking_complete_records_a_timestamp(self):
        response = self.client.post(reverse("profile-tour-completed"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["tourCompletedAt"])

        self.user.profile.refresh_from_db()
        self.assertIsNotNone(self.user.profile.tour_completed_at)

    def test_marking_complete_is_idempotent(self):
        """A double-click or a retry must not move the original timestamp."""

        first = self.client.post(reverse("profile-tour-completed")).data["tourCompletedAt"]
        second = self.client.post(reverse("profile-tour-completed")).data["tourCompletedAt"]
        self.assertEqual(first, second)

    def test_the_state_survives_a_later_me_request(self):
        self.client.post(reverse("profile-tour-completed"))
        self.assertIsNotNone(self.client.get(reverse("auth-me")).data["tourCompletedAt"])

    def test_it_requires_authentication(self):
        self.client.force_authenticate(None)
        response = self.client.post(reverse("profile-tour-completed"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_it_returns_the_updated_user(self):
        """The client replaces its cached user from this response."""

        response = self.client.post(reverse("profile-tour-completed"))
        for field in ("id", "email", "fullName", "tourCompletedAt"):
            self.assertIn(field, response.data)

    def test_one_users_tour_state_does_not_affect_another(self):
        self.client.post(reverse("profile-tour-completed"))

        other = User.objects.create_user(email="other@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(other)
        self.assertIsNone(self.client.get(reverse("auth-me")).data["tourCompletedAt"])

    def test_login_payload_carries_the_tour_state(self):
        """The tour decision is made from the session payload, not a second call."""

        self.client.post(reverse("profile-tour-completed"))
        self.client.force_authenticate(None)

        response = self.client.post(
            reverse("auth-login"),
            {"email": "tour@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        self.assertIsNotNone(response.data["user"]["tourCompletedAt"])


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

    def test_language_preference_defaults_to_any(self):
        """Narrowing to one language costs results, so it must be opt-in.

        The boards searched are overwhelmingly German; silently defaulting to
        German-only would hide English postings a user never asked to exclude.
        """

        response = self.client.get(reverse("profile-preferences"))
        self.assertEqual(response.data["languageFilter"], "any")

    def test_language_preference_can_be_set_and_read_back(self):
        for value in ("german", "english", "any"):
            response = self.client.patch(
                reverse("profile-preferences"), {"languageFilter": value}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["languageFilter"], value)

    def test_rejects_an_unknown_language_preference(self):
        response = self.client.patch(
            reverse("profile-preferences"), {"languageFilter": "klingon"}, format="json"
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
