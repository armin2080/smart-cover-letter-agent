"""Serializers for the accounts domain.

Field names are camelCase to match the frontend contract exactly.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    CvDocument,
    NotificationSettings,
    Preferences,
    Profile,
    ProfileSection,
    User,
)


# --------------------------------------------------------------------------- #
# User                                                                        #
# --------------------------------------------------------------------------- #


class UserSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="full_name")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "fullName", "createdAt")


class RegisterSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=255, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    passwordConfirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    acceptedTerms = serializers.BooleanField()

    def validate_email(self, value: str) -> str:
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["passwordConfirm"]:
            raise serializers.ValidationError({"passwordConfirm": ["Passwords do not match."]})
        if not attrs.get("acceptedTerms"):
            raise serializers.ValidationError(
                {"acceptedTerms": ["You must accept the terms to create an account."]}
            )

        # Reuse Django's configured password validators.
        candidate = User(email=attrs["email"], full_name=attrs["fullName"])
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc

        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["fullName"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    remember = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict) -> dict:
        email = attrs["email"].lower().strip()
        user = authenticate(request=self.context.get("request"), username=email, password=attrs["password"])
        if user is None:
            # Deliberately vague to avoid disclosing which accounts exist.
            raise serializers.ValidationError({"detail": "Incorrect email or password."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "This account is disabled."})
        attrs["user"] = user
        return attrs


class AccountUpdateSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=255, required=False, trim_whitespace=True)
    email = serializers.EmailField(required=False)
    currentPassword = serializers.CharField(required=False, write_only=True, allow_blank=True)
    newPassword = serializers.CharField(required=False, write_only=True, allow_blank=True)

    def validate_email(self, value: str) -> str:
        email = value.lower().strip()
        user: User = self.context["request"].user
        if User.objects.filter(email=email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs: dict) -> dict:
        user: User = self.context["request"].user
        new_password = attrs.get("newPassword")

        if new_password:
            current = attrs.get("currentPassword") or ""
            if not user.check_password(current):
                raise serializers.ValidationError({"currentPassword": ["Your current password is incorrect."]})
            try:
                password_validation.validate_password(new_password, user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"newPassword": list(exc.messages)}) from exc

        return attrs


# --------------------------------------------------------------------------- #
# Profile                                                                     #
# --------------------------------------------------------------------------- #


class ProfileSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileSection
        fields = ("id", "key", "title", "content")
        read_only_fields = ("id", "key", "title")


class CvDocumentSerializer(serializers.ModelSerializer):
    fileName = serializers.CharField(source="file_name", read_only=True)
    sizeBytes = serializers.IntegerField(source="size_bytes", read_only=True)
    uploadedAt = serializers.DateTimeField(source="uploaded_at", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = CvDocument
        fields = ("id", "fileName", "sizeBytes", "uploadedAt", "url", "status")

    def get_url(self, obj: CvDocument) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ProfileSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="user.full_name")
    email = serializers.EmailField(source="user.email")
    sections = serializers.SerializerMethodField()
    cv = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ("fullName", "email", "phone", "location", "portfolio", "summary", "sections", "cv")

    def get_sections(self, obj: Profile) -> list[dict]:
        sections = obj.user.profile_sections.all()
        return ProfileSectionSerializer(sections, many=True).data

    def get_cv(self, obj: Profile) -> dict | None:
        document = obj.user.cv_documents.order_by("-uploaded_at").first()
        if not document:
            return None
        return CvDocumentSerializer(document, context=self.context).data

    def update(self, instance: Profile, validated_data: dict) -> Profile:
        user_data = validated_data.pop("user", {}) or {}
        user: User = instance.user

        changed_user_fields: list[str] = []
        if "full_name" in user_data:
            user.full_name = user_data["full_name"]
            changed_user_fields.append("full_name")
        if "email" in user_data:
            user.email = user_data["email"].lower().strip()
            changed_user_fields.append("email")
        if changed_user_fields:
            user.save(update_fields=[*changed_user_fields, "updated_at"])

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


# --------------------------------------------------------------------------- #
# Preferences and notifications                                               #
# --------------------------------------------------------------------------- #


class PreferencesSerializer(serializers.ModelSerializer):
    desiredRoles = serializers.ListField(child=serializers.CharField(max_length=120), source="desired_roles")
    locations = serializers.ListField(child=serializers.CharField(max_length=120))
    radiusKm = serializers.IntegerField(source="radius_km", min_value=0, max_value=500)
    employmentTypes = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                "full-time",
                "part-time",
                "working-student",
                "internship",
                "minijob",
            ]
        ),
        source="employment_types",
    )
    sources = serializers.ListField(child=serializers.CharField(max_length=64))
    keywords = serializers.ListField(child=serializers.CharField(max_length=120))

    class Meta:
        model = Preferences
        fields = (
            "desiredRoles",
            "locations",
            "radiusKm",
            "employmentTypes",
            "sources",
            "keywords",
        )

    def _clean_list(self, values: list[str]) -> list[str]:
        seen: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen

    def validate_desiredRoles(self, value):  # noqa: N802 - camelCase matches the API
        return self._clean_list(value)

    def validate_locations(self, value):
        return self._clean_list(value)

    def validate_sources(self, value):
        return self._clean_list(value)

    def validate_keywords(self, value):
        return self._clean_list(value)


class NotificationSettingsSerializer(serializers.ModelSerializer):
    newMatches = serializers.BooleanField(source="new_matches", required=False)
    searchCompleted = serializers.BooleanField(source="search_completed", required=False)
    searchFailures = serializers.BooleanField(source="search_failures", required=False)

    class Meta:
        model = NotificationSettings
        fields = ("newMatches", "searchCompleted", "searchFailures")
