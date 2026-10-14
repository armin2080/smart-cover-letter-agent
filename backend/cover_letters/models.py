"""Cover letters domain."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CoverLetter(models.Model):
    """A cover letter drafted for one job."""

    class Tone(models.TextChoices):
        PROFESSIONAL = "professional", "Professional"
        CONFIDENT = "confident", "Confident"
        WARM = "warm", "Warm"

    class Length(models.TextChoices):
        CONCISE = "concise", "Concise"
        BALANCED = "balanced", "Balanced"
        DETAILED = "detailed", "Detailed"

    class Status(models.TextChoices):
        GENERATING = "generating", "Generating"
        DRAFT = "draft", "Draft"
        SAVED = "saved", "Saved"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cover_letters"
    )
    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="cover_letters")

    content = models.TextField(blank=True)
    language = models.CharField(max_length=32, default="English")
    tone = models.CharField(max_length=16, choices=Tone.choices, default=Tone.PROFESSIONAL)
    length = models.CharField(max_length=16, choices=Length.choices, default=Length.BALANCED)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    # Records which generator produced the current content, for transparency.
    generator = models.CharField(max_length=32, default="groq")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    saved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=["user", "job"], name="one_cover_letter_per_job"),
        ]

    def __str__(self) -> str:
        return f"CoverLetter<{self.job_id} {self.status}>"
