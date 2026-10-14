"""Accounts domain: user identity, profile, CV, preferences and notifications."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for the email-based custom user model."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Account identified by email address."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)


# --------------------------------------------------------------------------- #
# Profile                                                                     #
# --------------------------------------------------------------------------- #

SECTION_KEYS = (
    "personal",
    "summary",
    "education",
    "experience",
    "skills",
    "projects",
    "languages",
    "certificates",
)

DEFAULT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("personal", "Personal information"),
    ("summary", "Professional summary"),
    ("experience", "Work experience"),
    ("education", "Education"),
    ("skills", "Skills"),
    ("projects", "Projects"),
    ("languages", "Languages"),
    ("certificates", "Certificates"),
)


class Profile(models.Model):
    """Contact details and summary belonging to a user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=64, blank=True)
    location = models.CharField(max_length=255, blank=True)
    portfolio = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: When the guided tour was finished or skipped. Null means the user has not
    #: seen it yet, so it is offered the next time they reach the workspace.
    #:
    #: Stored per account rather than in browser storage: this pilot hands out
    #: accounts by invitation, and someone signing in from a second device
    #: should not be shown the tour again just because that browser is new.
    tour_completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Profile<{self.user_id}>"


class ProfileSection(models.Model):
    """A structured, independently editable CV section."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="profile_sections")
    key = models.CharField(max_length=32, choices=[(key, key.title()) for key in SECTION_KEYS])
    title = models.CharField(max_length=128)
    content = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="unique_section_key_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.key} ({self.user_id})"


class CvDocument(models.Model):
    """The single primary CV belonging to a user."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        ERROR = "error", "Error"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cv_documents")
    file = models.FileField(upload_to="cvs/%Y/%m/")
    file_name = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)
    error = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return self.file_name


class Preferences(models.Model):
    """Job-search preferences — deliberately separate from CV qualifications."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")
    desired_roles = models.JSONField(default=list, blank=True)
    locations = models.JSONField(default=list, blank=True)
    radius_km = models.PositiveSmallIntegerField(default=50)
    employment_types = models.JSONField(default=list, blank=True)
    sources = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Preferences<{self.user_id}>"


class NotificationSettings(models.Model):
    """User notification opt-ins."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_settings")
    new_matches = models.BooleanField(default=True)
    search_completed = models.BooleanField(default=True)
    search_failures = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Notifications<{self.user_id}>"


# --------------------------------------------------------------------------- #
# Defaults                                                                    #
# --------------------------------------------------------------------------- #

DEFAULT_SOURCES = ["LinkedIn", "StepStone", "Stellenwerk"]


def ensure_user_defaults(user: User) -> None:
    """Create the related profile/sections/preferences rows for a user.

    Idempotent, so it is safe to call from signals, the registration view, the
    seed command or a data migration.
    """

    Profile.objects.get_or_create(user=user)
    Preferences.objects.get_or_create(
        user=user,
        defaults={
            "desired_roles": [],
            "locations": [],
            "radius_km": 50,
            "employment_types": ["full-time"],
            "sources": list(DEFAULT_SOURCES),
            "keywords": [],
        },
    )
    NotificationSettings.objects.get_or_create(user=user)

    existing = set(user.profile_sections.values_list("key", flat=True))
    missing = [
        ProfileSection(user=user, key=key, title=title, content="", order=index)
        for index, (key, title) in enumerate(DEFAULT_SECTIONS)
        if key not in existing
    ]
    if missing:
        ProfileSection.objects.bulk_create(missing)
