"""Adapter registry and the platform authorization gate.

**This module is the compliance boundary of the system.**

An MIT licence on a scraper library authorises use of that *code*. It does not
authorise automated access to the platform the code talks to. Those are separate
questions, and the second one is decided by each platform's terms of service and
by whatever written agreement exists with the operator.

The gate therefore requires **two** independent conditions before any live
request is made:

1. `PROVIDER_<NAME>_ENABLED=true` — an explicit configuration opt-in.
2. `PROVIDER_<NAME>_AUTHORIZATION_REFERENCE=<non-empty>` — a recorded reference
   to the written authorization covering this integration.

Condition 2 exists so that flipping a boolean cannot silently switch on
collection that nobody has documented a right to perform. Enabling a provider
without a recorded authorization leaves it in
`DISABLED_AUTHORIZATION_PENDING`, and the adapter is never called.

See `docs/provider-authorization-matrix.md` for the current status per platform.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from jobs.sources.base import JobSourceAdapter, ProviderStatus, SourceHealth

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    """Everything the gate needs to know about one provider."""

    name: str
    display_name: str
    #: Platform terms summary, surfaced in the UI and the audit docs.
    terms_note: str
    #: Whether live collection is ever expected to be permitted.
    live_collection_expected: bool = True


#: Registry of known providers. The manual import path is always available
#: because it involves no third-party automated access.
PROVIDERS: dict[str, ProviderConfig] = {
    "linkedin": ProviderConfig(
        name="linkedin",
        display_name="LinkedIn",
        terms_note=(
            "LinkedIn's User Agreement prohibits scraping and unauthorised automated "
            "access. Public accessibility of the guest jobs endpoint is not permission."
        ),
    ),
    "stepstone": ProviderConfig(
        name="stepstone",
        display_name="StepStone",
        terms_note=(
            "StepStone's terms prohibit scraping for other purposes, republication, "
            "use outside its intended service, and commercial reuse of applicant services."
        ),
    ),
    "stellenwerk": ProviderConfig(
        name="stellenwerk",
        display_name="Stellenwerk",
        terms_note=(
            "Stellenwerk's legal notice restricts commercial reuse and modification of "
            "its website documents and graphics."
        ),
    ),
    "manual": ProviderConfig(
        name="manual",
        display_name="Manually added",
        terms_note=(
            "User-supplied listings. No third-party automated access is performed, so no "
            "platform authorization is required."
        ),
        live_collection_expected=False,
    ),
}


def _setting_name(provider: str, suffix: str) -> str:
    return f"PROVIDER_{provider.upper()}_{suffix}"


def is_enabled_by_config(provider: str) -> bool:
    return bool(getattr(settings, _setting_name(provider, "ENABLED"), False))


def authorization_reference(provider: str) -> str:
    """Return the recorded authorization reference, or an empty string.

    Deliberately a *reference* (a document id, ticket or contract path) rather
    than the agreement itself, so private paperwork stays out of Git.
    """

    return (getattr(settings, _setting_name(provider, "AUTHORIZATION_REFERENCE"), "") or "").strip()


def get_provider_status(provider: str) -> ProviderStatus:
    """Resolve the effective status of one provider.

    The order of checks matters: a missing authorization outranks an explicit
    enable, so the system fails closed.
    """

    config = PROVIDERS.get(provider)
    if config is None:
        return ProviderStatus.INTEGRATION_ERROR

    if not config.live_collection_expected:
        # The manual path performs no third-party collection.
        return ProviderStatus.READY if is_enabled_by_config(provider) else ProviderStatus.DISABLED_BY_CONFIG

    if not is_enabled_by_config(provider):
        return ProviderStatus.DISABLED_BY_CONFIG

    if not authorization_reference(provider):
        logger.warning(
            "Provider %s is enabled but has no recorded authorization reference; "
            "live collection remains disabled.",
            provider,
        )
        return ProviderStatus.DISABLED_AUTHORIZATION_PENDING

    return ProviderStatus.READY


def get_adapter(provider: str) -> JobSourceAdapter | None:
    """Return an adapter instance, or None when it must not be used.

    Returns None for any status other than READY, so a caller cannot
    accidentally bypass the gate by ignoring the status.
    """

    if get_provider_status(provider) is not ProviderStatus.READY:
        return None

    # Imported lazily so a broken optional adapter cannot break the registry.
    try:
        if provider == "linkedin":
            from jobs.sources.linkedin.adapter import LinkedInAdapter

            return LinkedInAdapter()
        if provider == "stepstone":
            from jobs.sources.stepstone.adapter import StepStoneAdapter

            return StepStoneAdapter()
        if provider == "stellenwerk":
            from jobs.sources.stellenwerk.adapter import StellenwerkAdapter

            return StellenwerkAdapter()
        if provider == "manual":
            from jobs.sources.manual.adapter import ManualImportAdapter

            return ManualImportAdapter()
    except Exception:  # noqa: BLE001 - never let one adapter break the registry
        logger.exception("Could not instantiate adapter for %s", provider)
        return None

    return None


def available_providers() -> list[str]:
    """Providers whose adapters may actually be used right now."""

    return [name for name in PROVIDERS if get_provider_status(name) is ProviderStatus.READY]


def enabled_provider_names() -> list[str]:
    """Providers a user may select, regardless of live availability.

    Used by the UI so users can still express a preference for a source that is
    pending authorization.
    """

    return list(PROVIDERS)


def provider_health() -> list[SourceHealth]:
    """Health snapshot for every provider, for the API and the UI."""

    from django.utils import timezone

    snapshot: list[SourceHealth] = []
    for name, config in PROVIDERS.items():
        status = get_provider_status(name)
        detail = config.terms_note
        if status is ProviderStatus.DISABLED_AUTHORIZATION_PENDING:
            detail = "Live collection disabled: no written platform authorization is on record."
        elif status is ProviderStatus.DISABLED_BY_CONFIG:
            detail = "Disabled by configuration."

        snapshot.append(
            SourceHealth(source=name, status=status, detail=detail, checked_at=timezone.now())
        )
    return snapshot
