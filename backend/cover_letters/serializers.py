"""Serializers for the cover letters domain."""

from __future__ import annotations

from rest_framework import serializers

from jobs.models import Job
from jobs.serializers import JobSerializer

from .models import CoverLetter


class CoverLetterSerializer(serializers.ModelSerializer):
    jobId = serializers.IntegerField(source="job_id", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    savedAt = serializers.DateTimeField(source="saved_at", read_only=True)

    class Meta:
        model = CoverLetter
        fields = (
            "id",
            "jobId",
            "content",
            "language",
            "tone",
            "length",
            "status",
            "updatedAt",
            "savedAt",
        )


class CoverLetterGenerateSerializer(serializers.Serializer):
    jobId = serializers.IntegerField()
    language = serializers.CharField(max_length=32, required=False, default="English")
    tone = serializers.ChoiceField(choices=CoverLetter.Tone.choices, required=False, default="professional")
    length = serializers.ChoiceField(
        choices=CoverLetter.Length.choices, required=False, default="balanced"
    )
    instructions = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_jobId(self, value: int) -> int:  # noqa: N802 - API camelCase
        request = self.context["request"]
        if not Job.objects.filter(pk=value, user=request.user).exists():
            raise serializers.ValidationError("Job not found.")
        return value


class CoverLetterUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True)
    language = serializers.CharField(max_length=32, required=False)
    tone = serializers.ChoiceField(choices=CoverLetter.Tone.choices, required=False)
    length = serializers.ChoiceField(choices=CoverLetter.Length.choices, required=False)


class CoverLetterPreviewSerializer(serializers.Serializer):
    """Response for `GET /cover-letters/preview/?job=<id>`."""

    jobId = serializers.IntegerField(source="job.id")
    job = JobSerializer()
    cvLabel = serializers.CharField()
    language = serializers.CharField()
    tone = serializers.CharField()
    length = serializers.CharField()
