"""Start due job searches for every user with automatic search enabled.

This is the trigger the application cannot provide for itself. Schedule it with
cron, for example every fifteen minutes — the command decides which users are
actually due, so a frequent tick does not mean frequent searches:

    0,15,30,45 * * * * cd /path/to/backend \
        && .venv/bin/python manage.py run_scheduled_searches

Runs execute inline rather than in a background thread, because this process
exits as soon as the command returns.
"""

from django.core.management.base import BaseCommand

from searches import runner
from searches.runner import run_scheduled_searches


class Command(BaseCommand):
    help = "Start automatic searches for users whose scheduled time has arrived."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if the next scheduled time has not been reached yet.",
        )

    def handle(self, *args, **options):
        # Nobody is watching a progress bar here, so the pacing that spreads
        # stages out for the UI would only make the command slower.
        runner.set_pacing(0)

        started = run_scheduled_searches(force=options["force"])

        if started:
            self.stdout.write(self.style.SUCCESS(f"Started {started} automatic search run(s)."))
        elif options["force"]:
            self.stdout.write("No users have automatic search enabled.")
        else:
            self.stdout.write("No automatic searches are due right now.")
