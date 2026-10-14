"""Seed a demo account so the frontend has realistic data to render.

    python manage.py seed_demo
    python manage.py seed_demo --email me@example.com --password secret123

Jobs are produced by running the real search pipeline (provider → matching
engine → persistence), so the seeded data exercises the same code paths as
production. All names and companies are illustrative sample data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Profile, ensure_user_defaults
from jobs.models import ActivityEntry, Job
from searches.models import AutoSearchSettings, SearchRun
from searches.runner import build_stages, execute_search_sync, set_pacing, summarise_criteria

User = get_user_model()

DEFAULT_EMAIL = "armin.keller@example.com"
DEFAULT_PASSWORD = "demo-password-123"

SECTIONS = {
    "personal": "Armin Keller · Berlin, Germany · armin.keller@example.com · +49 151 234 5678",
    "summary": (
        "Product designer with 5+ years creating intuitive B2B and consumer experiences, "
        "focused on design systems and research-led product work."
    ),
    "experience": (
        "Senior Product Designer at Studio Nord · 2021 - Present\n"
        "Product Designer at Kollektiv · 2019 - 2021"
    ),
    "education": "M.A. Interaction Design, UDK Berlin · 2019",
    "skills": "Figma, Product strategy, Design systems, User research, Prototyping, Accessibility",
    "projects": "Flowline Design System · Studio Nord",
    "languages": "German (Native), English (Fluent)",
    "certificates": "NN/g UX Certification · 2022",
}


class Command(BaseCommand):
    help = "Create a demo user with profile, preferences and matched jobs."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--name", default="Armin Keller")

    def handle(self, *args, **options):
        email = options["email"].lower().strip()
        password = options["password"]

        user, created = User.objects.get_or_create(email=email, defaults={"full_name": options["name"]})
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        ensure_user_defaults(user)

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.phone = "+49 151 234 5678"
        profile.location = "Berlin, Germany"
        profile.portfolio = "arminkeller.example.com"
        profile.summary = SECTIONS["summary"]
        profile.save()

        for section in user.profile_sections.all():
            content = SECTIONS.get(section.key)
            if content:
                section.content = content
                section.save(update_fields=["content", "updated_at"])

        preferences = user.preferences
        preferences.desired_roles = ["Product Designer", "Senior UX Designer"]
        preferences.locations = ["Berlin", "Remote (Germany)"]
        preferences.radius_km = 50
        preferences.employment_types = ["full-time"]
        preferences.sources = ["LinkedIn", "StepStone", "Stellenwerk"]
        preferences.keywords = ["SaaS", "design systems", "B2B"]
        preferences.save()

        auto, _ = AutoSearchSettings.objects.get_or_create(user=user)
        auto.enabled = True
        auto.frequency = AutoSearchSettings.Frequency.DAILY
        auto.time_of_day = "08:30"
        auto.sources = ["LinkedIn", "StepStone", "Stellenwerk"]
        auto.save()

        # Run the real pipeline to populate jobs.
        criteria = {
            "roles": preferences.desired_roles,
            "locations": preferences.locations,
            "radius_km": preferences.radius_km,
            "employment_types": preferences.employment_types,
            "keywords": preferences.keywords,
            "use_saved_preferences": True,
        }

        created_jobs = 0
        if not Job.objects.filter(user=user).exists():
            set_pacing(0)
            run = SearchRun.objects.create(
                user=user,
                mode=SearchRun.Mode.AUTOMATIC,
                status=SearchRun.Status.QUEUED,
                started_at=timezone.now(),
                criteria=criteria,
                criteria_summary=summarise_criteria(criteria),
                sources=preferences.sources,
                stages=build_stages(),
            )
            execute_search_sync(run.id)
            run.refresh_from_db()
            created_jobs = Job.objects.filter(user=user).count()

            # Give the demo a couple of non-new states so every tab has content.
            jobs = list(Job.objects.filter(user=user).order_by("-posted_at"))
            seed_states = ["saved", "reviewed", "reviewed", "dismissed", "saved"]
            for index, state in enumerate(seed_states):
                if index >= len(jobs):
                    break
                job = jobs[index]
                if job.status != state:
                    job.status = state
                    job.save(update_fields=["status", "updated_at"])

            if not ActivityEntry.objects.filter(user=user).exists():
                ActivityEntry.objects.create(
                    user=user,
                    kind=ActivityEntry.Kind.DISCOVERED,
                    title=f"{created_jobs} new jobs discovered",
                    subtitle="Automatic search",
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo account ready: {email} / {password}\n"
                f"  profile sections: {user.profile_sections.count()}\n"
                f"  jobs: {Job.objects.filter(user=user).count()} (created {created_jobs})\n"
                f"  preferences: {len(preferences.desired_roles)} roles, {len(preferences.sources)} sources"
            )
        )
