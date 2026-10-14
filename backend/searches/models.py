"""Searches domain: search runs, their stages, and automatic-search settings."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class SearchRun(models.Model):
    """One execution of a job search (manual or scheduled)."""

    class Mode(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATIC = "automatic", "Automatic"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_runs")

    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.MANUAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    criteria = models.JSONField(default=dict, blank=True)
    criteria_summary = models.CharField(max_length=255, blank=True)
    sources = models.JSONField(default=list, blank=True)

    discovered = models.PositiveIntegerField(default=0)
    matched = models.PositiveIntegerField(default=0)

    # [{key, label, detail, state}] — `state` is pending | active | done | error
    stages = models.JSONField(default=list, blank=True)

    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at", "-id")

    def __str__(self) -> str:
        return f"SearchRun<{self.id} {self.status}>"

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.FAILED}


class AutoSearchSettings(models.Model):
    """Scheduling preferences for automatic searching."""

    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ERROR = "error", "Error"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auto_search"
    )
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=16, choices=Frequency.choices, default=Frequency.DAILY)
    time_of_day = models.CharField(max_length=5, default="08:30")
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)  # 0=Monday
    sources = models.JSONField(default=list, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "automatic search settings"

    def __str__(self) -> str:
        return f"AutoSearch<{self.user_id} {'on' if self.enabled else 'off'}>"

    @property
    def status(self) -> str:
        if self.last_error:
            return self.Status.ERROR
        return self.Status.ACTIVE if self.enabled else self.Status.PAUSED

    def save(self, *args, **kwargs):
        if not self.sources:
            self.sources = ["LinkedIn", "StepStone", "Stellenwerk"]
        self.next_run_at = compute_next_run(self) if self.enabled else None
        super().save(*args, **kwargs)


def parse_time_of_day(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.split(":")
        return max(0, min(23, int(hour))), max(0, min(59, int(minute)))
    except (ValueError, AttributeError):
        return 8, 30


def compute_next_run(auto: AutoSearchSettings, now: datetime | None = None) -> datetime:
    """Return the next scheduled execution time in UTC."""

    now = now or timezone.now()
    hour, minute = parse_time_of_day(auto.time_of_day)

    if auto.frequency == AutoSearchSettings.Frequency.WEEKLY:
        target_weekday = auto.weekday if auto.weekday is not None else 0  # Monday
        days_ahead = (target_weekday - now.weekday()) % 7
        candidate = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
