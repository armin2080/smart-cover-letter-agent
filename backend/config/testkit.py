"""Shared test fixtures for provider configuration.

The authorization gate reads provider settings from `django.conf.settings` at
call time (see `jobs.sources.registry`). That is the right behaviour for
production — an operator can toggle a provider and the change takes effect on
the next resolution — but it means a developer's local `backend/.env` silently
changes the behaviour of the test suite.

A `.env` that enables live providers would otherwise make tests like "providers
default to disabled" start failing. Those tests are asserting a real safety
property, so they must not depend on the machine they run on.

Import `PLATFORM_PROVIDERS_DISABLED` and apply it with `@override_settings(...)`
expanded, or use the ready-made decorator below.
"""

from __future__ import annotations

from django.test import override_settings

#: Every platform provider pinned off, with no authorization reference recorded.
#: This mirrors the shipped defaults so tests exercise the fail-closed path.
DISABLED_PLATFORM_PROVIDERS: dict[str, object] = {
    "PROVIDER_LINKEDIN_ENABLED": False,
    "PROVIDER_LINKEDIN_AUTHORIZATION_REFERENCE": "",
    "PROVIDER_STEPSTONE_ENABLED": False,
    "PROVIDER_STEPSTONE_AUTHORIZATION_REFERENCE": "",
    "PROVIDER_STELLENWERK_ENABLED": False,
    "PROVIDER_STELLENWERK_AUTHORIZATION_REFERENCE": "",
    # The manual path needs no third-party access and is operational by default,
    # so pin it on rather than inheriting whatever the environment says.
    "PROVIDER_MANUAL_ENABLED": True,
    # No live provider is operational under this configuration, so the synthetic
    # fallback is deterministic.
    "SAMPLE_DATA_ENABLED": True,
}


def platform_providers_disabled():
    """Decorator pinning the gate to its fail-closed defaults."""

    return override_settings(**DISABLED_PLATFORM_PROVIDERS)
