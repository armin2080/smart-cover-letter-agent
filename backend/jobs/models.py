"""Jobs domain: discovered opportunities, match analysis and activity feed."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Job(models.Model):
    """A job opportunity discovered for a specific user.

    The record holds two distinct concerns:

    * **The listing** — what the source advertised (title, company, description,
      provenance). Sourced from an authorized adapter or supplied by the user.
    * **The user's interaction** — `reviewed_at`, `saved_at`, `dismissed_at` and
      `cover_letter_created_at`. These are independent: a job can be both
      reviewed and saved. `status` is a denormalised convenience for filtering
      and is derived from those timestamps.
    """

    class Match(models.TextChoices):
        STRONG = "strong", "Strong match"
        GOOD = "good", "Good match"
        POTENTIAL = "potential", "Potential match"
        LOW = "low", "Low relevance"

    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed"
        SAVED = "saved", "Saved"
        DISMISSED = "dismissed", "Dismissed"

    class EmploymentType(models.TextChoices):
        WORKING_STUDENT = "working-student", "Working student"
        INTERNSHIP = "internship", "Internship"
        STUDENT_ASSISTANT = "student-assistant", "Student assistant"
        PART_TIME = "part-time", "Part-time"
        FULL_TIME = "full-time", "Full-time"
        MINI_JOB = "minijob", "Minijob"
        TEMPORARY = "temporary", "Temporary"
        APPRENTICESHIP = "apprenticeship", "Apprenticeship"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    class WorkModel(models.TextChoices):
        ON_SITE = "on-site", "On-site"
        HYBRID = "hybrid", "Hybrid"
        REMOTE = "remote", "Remote"
        UNKNOWN = "unknown", "Unknown"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs")

    # -- listing identity --------------------------------------------------- #
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    company_initials = models.CharField(max_length=4, blank=True)
    company_color = models.CharField(max_length=16, blank=True)

    # -- location ----------------------------------------------------------- #
    location = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=80, blank=True, default="Germany")

    # -- classification ----------------------------------------------------- #
    employment_type = models.CharField(
        max_length=32, choices=EmploymentType.choices, default=EmploymentType.UNKNOWN
    )
    employment_type_confidence = models.FloatField(default=0.0)
    #: Terms that produced the classification, for auditability.
    employment_type_evidence = models.JSONField(default=list, blank=True)
    #: Categories that had evidence when the type could not be decided.
    employment_type_candidates = models.JSONField(default=list, blank=True)
    work_model = models.CharField(max_length=16, choices=WorkModel.choices, default=WorkModel.UNKNOWN)

    # -- compensation ------------------------------------------------------- #
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)

    # -- content ------------------------------------------------------------ #
    summary = models.TextField(blank=True)
    description = models.TextField(blank=True)
    responsibilities = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)

    # -- source and provenance ---------------------------------------------- #
    source = models.CharField(max_length=64, blank=True)
    source_url = models.URLField(max_length=1024, blank=True)
    external_id = models.CharField(max_length=128, blank=True)
    #: True when the user supplied the listing themselves.
    is_user_provided = models.BooleanField(default=False)
    #: [{source, url, external_id}] for every source that advertised this job.
    provenance = models.JSONField(default=list, blank=True)
    #: Untouched source payload, retained for traceability.
    raw_source_data = models.JSONField(default=dict, blank=True)

    # -- dates -------------------------------------------------------------- #
    posted_at = models.DateTimeField()
    collected_at = models.DateTimeField(null=True, blank=True)

    # -- matching ----------------------------------------------------------- #
    match = models.CharField(max_length=16, choices=Match.choices, default=Match.POTENTIAL)
    cv_alignment = models.JSONField(default=list, blank=True)
    preference_fit = models.JSONField(default=list, blank=True)

    # -- user interaction (independent of each other) ------------------------ #
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    saved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    cover_letter_created_at = models.DateTimeField(null=True, blank=True)

    has_cover_letter = models.BooleanField(default=False)

    # Stable hash of source + url + title, used to avoid duplicate listings.
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-posted_at", "-id")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "posted_at"]),
            models.Index(fields=["user", "employment_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "fingerprint"], name="unique_job_fingerprint_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.title} @ {self.company}"

    def save(self, *args, **kwargs):
        if not self.company_initials:
            self.company_initials = "".join(word[0] for word in self.company.split()[:2]).upper() or "?"
        if not self.company_color:
            self.company_color = company_color(self.company)
        super().save(*args, **kwargs)

    # -- interaction helpers ------------------------------------------------ #

    @property
    def is_saved(self) -> bool:
        return self.saved_at is not None

    @property
    def is_reviewed(self) -> bool:
        return self.reviewed_at is not None

    @property
    def is_dismissed(self) -> bool:
        return self.dismissed_at is not None

    def sync_status(self) -> str:
        """Derive the filter-friendly `status` from the interaction timestamps.

        Dismissal wins, then saved, then reviewed — but the underlying
        timestamps are never cleared, so a dismissed job still records that it
        was once saved.
        """

        if self.dismissed_at is not None:
            derived = self.Status.DISMISSED
        elif self.saved_at is not None:
            derived = self.Status.SAVED
        elif self.reviewed_at is not None:
            derived = self.Status.REVIEWED
        else:
            derived = self.Status.NEW

        self.status = derived
        return derived


class ActivityEntry(models.Model):
    """A user-visible event shown on the dashboard activity feed."""

    class Kind(models.TextChoices):
        DISCOVERED = "discovered", "Jobs discovered"
        REVIEWED = "reviewed", "Job reviewed"
        SAVED = "saved", "Job saved"
        COVER_LETTER = "cover-letter", "Cover letter"
        DISMISSED = "dismissed", "Job dismissed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-id")

    def __str__(self) -> str:
        return f"{self.kind}: {self.title}"


# --------------------------------------------------------------------------- #
# Presentation helpers                                                        #
# --------------------------------------------------------------------------- #

COMPANY_PALETTE = ("#172333", "#299B8D", "#285A8A", "#6750A4", "#765B44", "#1A746A", "#8A4B4B")


def company_color(company: str) -> str:
    """Deterministic avatar colour so a company always renders the same."""

    if not company:
        return COMPANY_PALETTE[0]
    digest = 0
    for char in company:
        digest = (digest * 31 + ord(char)) & 0xFFFFFFFF
    return COMPANY_PALETTE[digest % len(COMPANY_PALETTE)]


def job_fingerprint(source: str, source_url: str, title: str, company: str) -> str:
    """Stable identifier used to deduplicate listings per user."""

    import hashlib

    raw = "|".join(part.strip().lower() for part in (source, source_url, title, company))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
