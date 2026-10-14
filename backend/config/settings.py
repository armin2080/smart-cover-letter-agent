"""Django settings for the Smart Cover Letter Agent backend."""

from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env if present (never committed).
load_dotenv(BASE_DIR / ".env")

# Detect Django's test runner so tests can be hermetic. Test runs must never
# touch the network, so they default to the deterministic demo provider.
TESTING = "test" in sys.argv or os.getenv("DJANGO_TESTING") == "true"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Core                                                                        #
# --------------------------------------------------------------------------- #

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]", "testserver"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local
    "accounts",
    "jobs",
    "searches",
    "cover_letters",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------- #
# Database                                                                    #
# --------------------------------------------------------------------------- #

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Authentication                                                              #
# --------------------------------------------------------------------------- #

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------- #
# Internationalisation                                                        #
# --------------------------------------------------------------------------- #

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Static and media                                                            #
# --------------------------------------------------------------------------- #

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------- #
# Django REST Framework                                                       #
# --------------------------------------------------------------------------- #

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Smart Cover Letter Agent API",
    "DESCRIPTION": "Job discovery, explainable CV matching, and AI-assisted cover letters.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------- #
# CORS                                                                        #
# --------------------------------------------------------------------------- #
# The Vite dev server proxies /api to this backend, so CORS is not strictly
# required in development. It is enabled anyway for direct-origin setups.

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", CORS_ALLOWED_ORIGINS)

# --------------------------------------------------------------------------- #
# Application-specific settings                                               #
# --------------------------------------------------------------------------- #

# Groq (cover letter generation). Without a key the service falls back to a
# deterministic, profile-grounded draft so the feature still works offline.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
GROQ_TIMEOUT_SECONDS = int(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))

import os
import sys

# --------------------------------------------------------------------------- #
# Job source providers                                                        #
# --------------------------------------------------------------------------- #
#
# COMPLIANCE GATE. Two independent conditions must both hold before any live
# request is made to a third-party platform:
#
#   1. PROVIDER_<NAME>_ENABLED=true
#   2. PROVIDER_<NAME>_AUTHORIZATION_REFERENCE=<non-empty reference>
#
# The second condition records *which* written authorization covers the
# integration. An MIT licence on a scraper library authorises the code, not
# access to the platform. Enabling a provider without a recorded authorization
# leaves it DISABLED_AUTHORIZATION_PENDING and the adapter is never called.
#
# The default for every platform is OFF.
# See docs/provider-authorization-matrix.md.

PROVIDER_LINKEDIN_ENABLED = env_bool("PROVIDER_LINKEDIN_ENABLED", False)
PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE = os.getenv(
    "PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE", ""
)

PROVIDER_STEPSTONE_ENABLED = env_bool("PROVIDER_STEPSTONE_ENABLED", False)
PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE = os.getenv(
    "PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE", ""
)

PROVIDER_STELLENWERK_ENABLED = env_bool("PROVIDER_STELLENWERK_ENABLED", False)
PROVIDER_STELLENWERK_AUTHORIZATION_REFERENCE = os.getenv(
    "PROVIDER_STELLENWERK_AUTHORIZATION_REFERENCE", ""
)

# The manual import path performs no third-party collection, so it needs no
# authorization and is enabled by default.
PROVIDER_MANUAL_ENABLED = env_bool("PROVIDER_MANUAL_ENABLED", True)

# Adapter HTTP behaviour (applies only to authorized providers).
SOURCE_HTTP_TIMEOUT_SECONDS = int(os.getenv("SOURCE_HTTP_TIMEOUT_SECONDS", "20"))
SOURCE_HTTP_MAX_ATTEMPTS = int(os.getenv("SOURCE_HTTP_MAX_ATTEMPTS", "3"))
SOURCE_MAX_RESULTS = int(os.getenv("SOURCE_MAX_RESULTS", "50"))
# How many listings per source get a detail fetch. Descriptions materially
# improve classification and matching, but each one costs a request.
SOURCE_ENRICH_LIMIT = int(os.getenv("SOURCE_ENRICH_LIMIT", "6"))

# Legacy switch retained for the deterministic sample provider used by the seed
# command and the test suite. It is NOT a live source.
SAMPLE_DATA_ENABLED = env_bool("SAMPLE_DATA_ENABLED", True)

# Run searches in a background thread. Disable for tests or single-process
# deployments where inline execution is preferable.
SEARCH_RUN_ASYNC = env_bool("SEARCH_RUN_ASYNC", True)

# Maximum size for an uploaded CV (bytes).
CV_MAX_UPLOAD_BYTES = int(os.getenv("CV_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
CV_ALLOWED_EXTENSIONS = [".pdf", ".docx"]

# --------------------------------------------------------------------------- #
# Logging                                                                     #
# --------------------------------------------------------------------------- #

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
