"""Start a job search for every user with automatic search enabled.

Schedule with cron, for example every hour:

    0 * * * * cd /path/to/backend && .venv/bin/python manage.py run_scheduled_searches
"""

from django.core.management.base import BaseCommand

from searches.runner import run_scheduled_searches


class Command(BaseCommand):
    help = "Start automatic searches for all users with automatic search enabled."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if the next scheduled time has not been reached yet.",
        )

    def handle(self, *args, **options):
        started = run_scheduled_searches()
        if started:
            self.stdout.write(self.style.SUCCESS(f"Started {started} automatic search run(s)."))
        else:
            self.stdout.write("No users have automatic search enabled.")
