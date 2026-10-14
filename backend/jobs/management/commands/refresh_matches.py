"""Recompute stored match analysis for existing jobs.

Match analysis is snapshotted when a job is discovered. Run this after changing
the matching rules, or after a user's CV or preferences change.

    python manage.py refresh_matches                 # every user
    python manage.py refresh_matches --email me@x.y  # one user
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from jobs.services import refresh_user_matches

User = get_user_model()


class Command(BaseCommand):
    help = "Recompute match analysis (match level, CV alignment, preference fit) for existing jobs."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Only refresh this user's jobs.")
        parser.add_argument(
            "--status",
            action="append",
            dest="statuses",
            help="Only refresh jobs with this status. Repeatable.",
        )

    def handle(self, *args, **options):
        statuses = set(options["statuses"]) if options.get("statuses") else None

        if options.get("email"):
            users = User.objects.filter(email=options["email"].lower())
            if not users.exists():
                self.stderr.write(self.style.ERROR("No user found with that email."))
                return
        else:
            users = User.objects.all()

        total = 0
        processed = 0
        for user in users.iterator():
            updated = refresh_user_matches(user, only_statuses=statuses)
            total += updated
            processed += 1
            if options.get("email"):
                self.stdout.write(f"{user.email}: {updated} job(s) updated.")

        self.stdout.write(
            self.style.SUCCESS(f"Refreshed {total} job(s) across {processed} user(s).")
        )
