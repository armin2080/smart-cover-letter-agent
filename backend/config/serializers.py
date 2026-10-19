"""Small shared serializers used for schema generation and simple bodies."""

from rest_framework import serializers


class EmptySerializer(serializers.Serializer):
    """Placeholder for endpoints that accept or return no body."""


class DetailSerializer(serializers.Serializer):
    """Standard error/acknowledgement envelope."""

    detail = serializers.CharField(help_text="Human-readable message.")
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        required=False,
        help_text="Field-level validation errors keyed by field name.",
    )


class LanguageCountsSerializer(serializers.Serializer):
    """Per-language tallies for the job list's language tabs."""

    any = serializers.IntegerField(help_text="Every job, including unknown languages.")
    german = serializers.IntegerField()
    english = serializers.IntegerField()
    unknown = serializers.IntegerField()


class CountsSerializer(serializers.Serializer):
    """Status tallies used by the My Jobs tabs."""

    new = serializers.IntegerField()
    reviewed = serializers.IntegerField()
    saved = serializers.IntegerField()
    dismissed = serializers.IntegerField()
    languages = LanguageCountsSerializer()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, help_text="Refresh token to invalidate.")


class PublicConfigSerializer(serializers.Serializer):
    """Feature flags the frontend reads before anyone signs in.

    Unauthenticated, so it must never carry anything sensitive.
    """

    registrationEnabled = serializers.BooleanField(  # noqa: N815 - API camelCase
        help_text="Whether visitors may create their own account. When false the "
        "signup form is hidden and POST /api/auth/register/ is refused."
    )
