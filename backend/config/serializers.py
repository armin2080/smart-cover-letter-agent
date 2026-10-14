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


class CountsSerializer(serializers.Serializer):
    """Status tallies used by the My Jobs tabs."""

    new = serializers.IntegerField()
    reviewed = serializers.IntegerField()
    saved = serializers.IntegerField()
    dismissed = serializers.IntegerField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, help_text="Refresh token to invalidate.")
