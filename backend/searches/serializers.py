"""Serializers for the searches domain."""

from __future__ import annotations

from rest_framework import serializers

from .models import AutoSearchSettings, SearchRun


class SearchCriteriaSerializer(serializers.Serializer):
    """Input payload for starting a search."""

    roles = serializers.ListField(child=serializers.CharField(max_length=120), required=False, default=list)
    locations = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, default=list
    )
    radiusKm = serializers.IntegerField(required=False, default=50, min_value=0, max_value=500)
    employmentTypes = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, default=list
    )
    sources = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list
    )
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, default=list
    )
    useSavedPreferences = serializers.BooleanField(required=False, default=True)

    def to_criteria(self) -> dict:
        """Normalised criteria dict stored on the run."""

        data = self.validated_data
        return {
            "roles": _clean(data.get("roles", [])),
            "locations": _clean(data.get("locations", [])),
            "radius_km": data.get("radiusKm", 50),
            "employment_types": _clean(data.get("employmentTypes", [])),
            "sources": _clean(data.get("sources", [])),
            "keywords": _clean(data.get("keywords", [])),
            "use_saved_preferences": data.get("useSavedPreferences", True),
        }


def _clean(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values or []:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


class SearchRunSerializer(serializers.ModelSerializer):
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    finishedAt = serializers.DateTimeField(source="finished_at", read_only=True)
    criteriaSummary = serializers.CharField(source="criteria_summary", read_only=True)

    class Meta:
        model = SearchRun
        fields = (
            "id",
            "mode",
            "status",
            "startedAt",
            "finishedAt",
            "criteriaSummary",
            "sources",
            "discovered",
            "matched",
            "stages",
            "error",
        )


class AutoSearchSettingsSerializer(serializers.ModelSerializer):
    timeOfDay = serializers.CharField(source="time_of_day")
    status = serializers.CharField(read_only=True)
    lastRunAt = serializers.DateTimeField(source="last_run_at", read_only=True)
    nextRunAt = serializers.DateTimeField(source="next_run_at", read_only=True)
    #: Whether an external scheduler actually runs the searches.
    #:
    #: Setting `enabled` only records intent; nothing in the web process fires
    #: on a timer. Surfaced so the UI can say "scheduled" honestly instead of
    #: counting down to a run that will never happen.
    schedulerActive = serializers.SerializerMethodField()

    class Meta:
        model = AutoSearchSettings
        fields = (
            "enabled",
            "frequency",
            "timeOfDay",
            "weekday",
            "sources",
            "status",
            "lastRunAt",
            "nextRunAt",
            "schedulerActive",
        )

    def get_schedulerActive(self, obj: AutoSearchSettings) -> bool:  # noqa: N802 - API camelCase
        from django.conf import settings

        return bool(settings.AUTO_SEARCH_SCHEDULER_ENABLED)

    def validate_timeOfDay(self, value: str) -> str:  # noqa: N802 - API camelCase
        try:
            hour, minute = value.split(":")
            hour_int, minute_int = int(hour), int(minute)
        except (ValueError, AttributeError) as exc:
            raise serializers.ValidationError("Use the HH:MM format.") from exc
        if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
            raise serializers.ValidationError("Use a valid 24-hour time, for example 08:30.")
        return f"{hour_int:02d}:{minute_int:02d}"

    def validate_weekday(self, value):
        if value is None:
            return value
        if not 0 <= int(value) <= 6:
            raise serializers.ValidationError("Weekday must be between 0 (Monday) and 6 (Sunday).")
        return int(value)
