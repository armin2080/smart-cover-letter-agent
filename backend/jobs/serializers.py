"""Serializers for the jobs domain."""

from __future__ import annotations

from rest_framework import serializers

from .models import ActivityEntry, Job
from .sources.base import EmploymentType, WorkModel


class JobSerializer(serializers.ModelSerializer):
    companyInitials = serializers.CharField(source="company_initials", read_only=True)
    companyColor = serializers.CharField(source="company_color", read_only=True)
    employmentType = serializers.CharField(source="employment_type", read_only=True)
    employmentTypeLabel = serializers.SerializerMethodField()
    employmentTypeConfidence = serializers.FloatField(source="employment_type_confidence", read_only=True)
    employmentTypeEvidence = serializers.ListField(
        source="employment_type_evidence", read_only=True
    )
    #: Which categories had evidence when the type could not be decided.
    #: Lets the UI explain why an untyped listing was kept by a filter.
    employmentTypeCandidates = serializers.ListField(
        source="employment_type_candidates", read_only=True
    )
    workModel = serializers.CharField(source="work_model", read_only=True)
    postedAt = serializers.DateTimeField(source="posted_at", read_only=True)
    collectedAt = serializers.DateTimeField(source="collected_at", read_only=True)
    sourceUrl = serializers.CharField(source="source_url", read_only=True)
    hasCoverLetter = serializers.BooleanField(source="has_cover_letter", read_only=True)
    isUserProvided = serializers.BooleanField(source="is_user_provided", read_only=True)
    salaryMin = serializers.IntegerField(source="salary_min", read_only=True)
    salaryMax = serializers.IntegerField(source="salary_max", read_only=True)

    # Independent user-interaction state.
    reviewedAt = serializers.DateTimeField(source="reviewed_at", read_only=True)
    savedAt = serializers.DateTimeField(source="saved_at", read_only=True)
    dismissedAt = serializers.DateTimeField(source="dismissed_at", read_only=True)

    class Meta:
        model = Job
        fields = (
            "id",
            "title",
            "company",
            "companyInitials",
            "companyColor",
            "location",
            "city",
            "region",
            "country",
            "employmentType",
            "employmentTypeLabel",
            "employmentTypeConfidence",
            "employmentTypeEvidence",
            "employmentTypeCandidates",
            "workModel",
            "postedAt",
            "collectedAt",
            "source",
            "sourceUrl",
            "match",
            "status",
            "skills",
            "hasCoverLetter",
            "isUserProvided",
            "salaryMin",
            "salaryMax",
            "reviewedAt",
            "savedAt",
            "dismissedAt",
        )

    def get_employmentTypeLabel(self, obj: Job) -> str:  # noqa: N802 - API camelCase
        try:
            return EmploymentType(obj.employment_type).label
        except ValueError:
            return obj.employment_type


class JobDetailSerializer(JobSerializer):
    analysis = serializers.SerializerMethodField()
    provenance = serializers.ListField(read_only=True)

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + (
            "description",
            "summary",
            "responsibilities",
            "requirements",
            "provenance",
            "analysis",
        )

    def get_analysis(self, obj: Job) -> dict:
        return {
            "cvAlignment": obj.cv_alignment or [],
            "preferenceFit": obj.preference_fit or [],
        }


class JobStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Job.Status.choices)


class ManualJobImportSerializer(serializers.Serializer):
    """User-supplied listing.

    The supplied URL is **not** fetched: retrieving it would be automated access
    to that platform. The user's own description is used instead.
    """

    url = serializers.URLField(max_length=1024, required=False, allow_blank=True)
    title = serializers.CharField(max_length=255)
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    employmentType = serializers.ChoiceField(
        choices=[choice.value for choice in Job.EmploymentType],
        required=False,
        allow_blank=True,
    )
    description = serializers.CharField(required=False, allow_blank=True, max_length=8000)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("title", "").strip():
            raise serializers.ValidationError({"title": ["A job title is required."]})
        return attrs


class ProviderStatusSerializer(serializers.Serializer):
    source = serializers.CharField()
    displayName = serializers.CharField()
    status = serializers.CharField()
    statusLabel = serializers.CharField()
    operational = serializers.BooleanField()
    detail = serializers.CharField()
    termsNote = serializers.CharField()


class ActivityEntrySerializer(serializers.ModelSerializer):
    occurredAt = serializers.DateTimeField(source="occurred_at", read_only=True)

    class Meta:
        model = ActivityEntry
        fields = ("id", "kind", "title", "subtitle", "occurredAt")


class StatCardSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    hint = serializers.CharField()


class JobStatsSerializer(serializers.Serializer):
    cards = StatCardSerializer(many=True)
    automaticSearchActive = serializers.BooleanField()
    lastSearchAt = serializers.DateTimeField(allow_null=True)
    nextSearchAt = serializers.DateTimeField(allow_null=True)
