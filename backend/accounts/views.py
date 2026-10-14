"""Views for authentication, profile, CV, preferences and notifications."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from config.serializers import EmptySerializer, LogoutSerializer, PublicConfigSerializer

from .cv_parser import parse_cv
from .models import (
    CvDocument,
    NotificationSettings,
    Preferences,
    Profile,
    ProfileSection,
    User,
    ensure_user_defaults,
)
from .serializers import (
    AccountUpdateSerializer,
    CvDocumentSerializer,
    LoginSerializer,
    NotificationSettingsSerializer,
    PreferencesSerializer,
    ProfileSerializer,
    ProfileSectionSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


def auth_payload(user: User, request=None) -> dict:
    """Issue a token pair plus the serialised user."""

    refresh = RefreshToken.for_user(user)
    return {
        "user": UserSerializer(user).data,
        "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
    }


# --------------------------------------------------------------------------- #
# Authentication                                                              #
# --------------------------------------------------------------------------- #


class PublicConfigView(APIView):
    """GET /api/config/ — feature flags the frontend needs before signing in.

    Unauthenticated by design: the login screen has to know whether to offer a
    "create account" link. Only ever exposes non-sensitive booleans.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = PublicConfigSerializer

    def get(self, request):
        return Response(
            {
                "registrationEnabled": settings.REGISTRATION_ENABLED,
            }
        )


class RegisterView(APIView):
    """POST /api/auth/register/ — create an account and return a session.

    Refused unless self-service registration is switched on. The pilot runs
    invitation-only: accounts are created deliberately through the admin panel,
    and an open signup form would let anyone who finds the URL in.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = RegisterSerializer

    def post(self, request):
        if not settings.REGISTRATION_ENABLED:
            return Response(
                {
                    "detail": "Registration is closed. Ask an administrator to create "
                    "an account for you.",
                    "code": "registration_disabled",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return self._register(request)

    @transaction.atomic
    def _register(self, request):
        serializer = RegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        ensure_user_defaults(user)
        return Response(auth_payload(user, request), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ — email + password authentication."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        ensure_user_defaults(user)
        return Response(auth_payload(user, request))


class LogoutView(APIView):
    """POST /api/auth/logout/ — best-effort refresh-token invalidation."""

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = (request.data or {}).get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except AttributeError:
                # Token blacklist app is not installed; the client clears tokens.
                pass
            except Exception:
                logger.info("Ignoring invalid refresh token during logout.")
        return Response(status=status.HTTP_205_RESET_CONTENT)


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/ — rotate the access token."""

    permission_classes = [AllowAny]
    authentication_classes: list = []


class MeView(APIView):
    """GET/PATCH /api/auth/me/ — read or update the current account."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = AccountUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        fields: list[str] = []

        if "fullName" in data:
            user.full_name = data["fullName"]
            fields.append("full_name")
        if "email" in data:
            user.email = data["email"].lower().strip()
            fields.append("email")
        if data.get("newPassword"):
            user.set_password(data["newPassword"])
            fields.append("password")

        if fields:
            user.save(update_fields=[*fields, "updated_at"])

        return Response(UserSerializer(user).data)


# --------------------------------------------------------------------------- #
# Profile                                                                     #
# --------------------------------------------------------------------------- #


class ProfileView(APIView):
    """GET/PATCH /api/profile/."""

    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def _profile(self, request) -> Profile:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return profile

    def get(self, request):
        profile = self._profile(request)
        return Response(ProfileSerializer(profile, context={"request": request}).data)

    def patch(self, request):
        profile = self._profile(request)
        serializer = ProfileSerializer(profile, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TourCompletedView(APIView):
    """POST /api/profile/tour-completed/ — record that the guided tour is done.

    Called when the tour is finished *or* skipped; both mean "do not show this
    again". Idempotent, so a duplicate request from a double-click or a retry
    does not move the original timestamp.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if profile.tour_completed_at is None:
            profile.tour_completed_at = timezone.now()
            profile.save(update_fields=["tour_completed_at"])

        # Point the reverse relation at the instance just updated. Without this
        # the serializer can read a stale cached `user.profile` from earlier in
        # the request and report the tour as still unseen, even though the row
        # was written.
        request.user.profile = profile

        # The updated user, so the client can replace its cached copy instead of
        # keeping a second source of truth.
        return Response(UserSerializer(request.user).data)


class ProfileSectionDetailView(APIView):
    """PATCH /api/profile/sections/{sectionId}/."""

    serializer_class = ProfileSectionSerializer
    permission_classes = [IsAuthenticated]

    def patch(self, request, section_id: str):
        section = None

        # Accept either a numeric primary key or the semantic section key.
        if section_id.isdigit():
            section = ProfileSection.objects.filter(user=request.user, id=int(section_id)).first()

        if section is None:
            section = ProfileSection.objects.filter(user=request.user, key=section_id).first()

        if section is None:
            return Response({"detail": "Section not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProfileSectionSerializer(section, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(ProfileSerializer(profile, context={"request": request}).data)


class CvUploadView(APIView):
    """POST (multipart, field `file`) / DELETE /api/profile/cv/."""

    serializer_class = CvDocumentSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {"detail": "No file was provided.", "errors": {"file": ["This field is required."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        extension = Path(uploaded.name).suffix.lower()
        if extension not in settings.CV_ALLOWED_EXTENSIONS:
            return Response(
                {
                    "detail": "Unsupported file type.",
                    "errors": {"file": ["Only PDF and DOCX files are accepted."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded.size > settings.CV_MAX_UPLOAD_BYTES:
            limit_mb = settings.CV_MAX_UPLOAD_BYTES // (1024 * 1024)
            return Response(
                {
                    "detail": "File is too large.",
                    "errors": {"file": [f"Files must be {limit_mb} MB or smaller."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = CvDocument.objects.create(
            user=request.user,
            file=uploaded,
            file_name=uploaded.name,
            size_bytes=uploaded.size,
            status=CvDocument.Status.PROCESSING,
        )

        try:
            self._ingest(request.user, document)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("CV ingestion failed for user %s", request.user_id)
            document.status = CvDocument.Status.ERROR
            document.error = str(exc)
            document.save(update_fields=["status", "error"])

        # One primary CV per user: retire any earlier documents.
        stale = request.user.cv_documents.exclude(pk=document.pk)
        for previous in stale:
            previous.file.delete(save=False)
            previous.delete()

        return Response(
            CvDocumentSerializer(document, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        for document in request.user.cv_documents.all():
            document.file.delete(save=False)
            document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _ingest(self, user: User, document: CvDocument) -> None:
        """Populate profile sections and contact details from the CV text."""

        parsed = parse_cv(document.file.path)
        sections = parsed["sections"]
        contact = parsed["contact"]

        profile, _ = Profile.objects.get_or_create(user=user)
        changed: list[str] = []

        if contact.get("phone") and not profile.phone:
            profile.phone = contact["phone"]
            changed.append("phone")
        if contact.get("full_name") and not user.full_name:
            user.full_name = contact["full_name"]
            user.save(update_fields=["full_name", "updated_at"])
        if contact.get("email") and contact["email"].lower() != user.email:
            # Keep the account email authoritative; surface it in the contact section.
            sections.setdefault("personal", "")

        if sections.get("summary") and not profile.summary:
            profile.summary = sections["summary"]
            changed.append("summary")
        if changed:
            profile.save(update_fields=[*changed, "updated_at"])

        for section in user.profile_sections.all():
            extracted = sections.get(section.key)
            if extracted:
                section.content = extracted
                section.save(update_fields=["content", "updated_at"])

        document.status = CvDocument.Status.READY
        document.save(update_fields=["status"])


# --------------------------------------------------------------------------- #
# Preferences and notifications                                               #
# --------------------------------------------------------------------------- #


class PreferencesView(APIView):
    """GET/PUT /api/profile/preferences/."""

    serializer_class = PreferencesSerializer
    permission_classes = [IsAuthenticated]

    def _preferences(self, request) -> Preferences:
        preferences, _ = Preferences.objects.get_or_create(user=request.user)
        return preferences

    def get(self, request):
        return Response(PreferencesSerializer(self._preferences(request)).data)

    def put(self, request):
        preferences = self._preferences(request)
        serializer = PreferencesSerializer(preferences, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request):
        preferences = self._preferences(request)
        serializer = PreferencesSerializer(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotificationSettingsView(APIView):
    """GET/PUT /api/settings/notifications/."""

    serializer_class = NotificationSettingsSerializer
    permission_classes = [IsAuthenticated]

    def _settings(self, request) -> NotificationSettings:
        settings_obj, _ = NotificationSettings.objects.get_or_create(user=request.user)
        return settings_obj

    def get(self, request):
        return Response(NotificationSettingsSerializer(self._settings(request)).data)

    def put(self, request):
        instance = self._settings(request)
        serializer = NotificationSettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    patch = put


class AccountDeleteView(APIView):
    """DELETE /api/account/ — permanently remove the account and its data."""

    serializer_class = EmptySerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request):
        user = request.user
        for document in user.cv_documents.all():
            document.file.delete(save=False)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
