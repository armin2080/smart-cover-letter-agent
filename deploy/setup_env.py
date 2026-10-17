"""Write the production .env on the server.

Run over SSH with this script piped to the venv's python, so the SECRET_KEY is
generated on the server and never appears in any command output or transcript.
"""

import secrets
from datetime import datetime, timezone
from pathlib import Path

ENV_PATH = Path("/home/codex/sca/app/backend/.env")

TEMPLATE = """\
# ---------------------------------------------------------------------------
# PRODUCTION configuration for sca.armin2080.de
# Generated on the server by deploy/setup_env.py. Never commit this file.
# ---------------------------------------------------------------------------

# Generated with secrets.token_urlsafe(64) at {generated_at}
DJANGO_SECRET_KEY={secret_key}
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=sca.armin2080.de,127.0.0.1,localhost
DJANGO_LOG_LEVEL=INFO

# Behind the Cloudflare tunnel the browser origin is HTTPS. Without these,
# CSRF rejects every POST because Django sees the plain-HTTP loopback hop.
CSRF_TRUSTED_ORIGINS=https://sca.armin2080.de
CORS_ALLOWED_ORIGINS=https://sca.armin2080.de

# Data lives outside the source tree, so a redeploy cannot touch the database
# or any uploaded CV.
DJANGO_DB_PATH=/home/codex/sca/data/db.sqlite3
DJANGO_MEDIA_ROOT=/home/codex/sca/data/media

# Where the built SPA was placed.
SPA_ROOT=/home/codex/sca/app/frontend/dist

# JWT lifetimes
JWT_ACCESS_MINUTES=60
JWT_REFRESH_DAYS=14

# Cover letters. No API key on the server, so generation falls back to the
# deterministic offline draft grounded strictly in the user's own profile.
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-70b-versatile
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_TIMEOUT_SECONDS=60

# Invitation-only pilot: accounts are created through the admin panel.
REGISTRATION_ENABLED=false

# ---------------------------------------------------------------------------
# Job sources
# ---------------------------------------------------------------------------
# TEST MODE: collection is enabled with NO authorization on record. This is for
# evaluation only and is not permission. Every provider below is reported as
# "Test mode - no authorization", never as ready.
PROVIDER_TEST_MODE=true

PROVIDER_LINKEDIN_ENABLED=true
PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE=

PROVIDER_STEPSTONE_ENABLED=true
PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE=

PROVIDER_STELLENWERK_ENABLED=true
PROVIDER_STELLENWERK_AUTHORIZATION_REFERENCE=

PROVIDER_MANUAL_ENABLED=true
SAMPLE_DATA_ENABLED=true

# Conservative: few requests per source, generous timeouts.
SOURCE_HTTP_TIMEOUT_SECONDS=25
SOURCE_HTTP_MAX_ATTEMPTS=2
SOURCE_MAX_RESULTS=30
SOURCE_ENRICH_LIMIT=6

# Whether an external timer actually calls `manage.py run_scheduled_searches`.
# Keep false on a fresh box: there is no cron entry yet, and the UI uses this to
# avoid promising a next run that nothing will trigger. Set it to true at the
# same time the cron entry is installed (see deploy/README.md).
AUTO_SEARCH_SCHEDULER_ENABLED=false

CV_MAX_UPLOAD_BYTES=10485760
"""


def main() -> None:
    if ENV_PATH.exists():
        # Never silently overwrite a live configuration.
        raise SystemExit(f"{ENV_PATH} already exists - refusing to overwrite")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(
        TEMPLATE.format(
            secret_key=secrets.token_urlsafe(64),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    )
    ENV_PATH.chmod(0o600)

    # Report only non-secret facts.
    print(f"written: {ENV_PATH}")
    print(f"mode:    {oct(ENV_PATH.stat().st_mode)[-3:]}")
    print(f"bytes:   {ENV_PATH.stat().st_size}")
    print("secret:  generated on the server, not displayed")


if __name__ == "__main__":
    main()
