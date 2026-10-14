"""Rate limiting for the endpoints that are expensive to serve.

Why this exists
---------------
Password verification in Django is deliberately slow — PBKDF2 at Django 6's
default iteration count. Measured on the production droplet (1 vCPU):

    one password check:    1555 ms
    throughput:            0.6 attempts/sec

A single unauthenticated POST to the login endpoint therefore occupies the CPU
for over a second. That machine also runs a more important service on the same
core, so an unthrottled login route is not merely a brute-force risk — it is a
trivial way to make that other service unresponsive.

Throttling is the mitigation. Note what it does *not* rely on: the attacker
needs no vulnerability, no credential and no cleverness, only the cost of the
app's own password hashing.

Scope
-----
Applied to the auth endpoints only. Those are two to three orders of magnitude
more expensive than a normal read, so a global limit would add friction
everywhere without protecting anything meaningful.
"""

from __future__ import annotations

import hashlib

from django.core.cache import caches
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class _ThrottleCacheMixin:
    """Keep throttle counters in their own cache.

    Sharing the default cache would let ordinary caching traffic evict throttle
    state, quietly weakening the limits at exactly the moment they matter.
    """

    @property
    def cache(self):
        return caches["throttle"]


class AuthBurstThrottle(_ThrottleCacheMixin, AnonRateThrottle):
    """Short-window limit on credential endpoints.

    Catches a script hammering the login route. Kept tight because the cost of
    a single request is so high on this hardware.
    """

    scope = "auth-burst"


class AuthSustainedThrottle(_ThrottleCacheMixin, AnonRateThrottle):
    """Longer-window limit, to stop a slow drip rather than a burst.

    A burst limit alone is easy to sidestep by pacing requests just under it,
    which still saturates a single core over time.
    """

    scope = "auth-sustained"


class LoginIdentityThrottle(_ThrottleCacheMixin, SimpleRateThrottle):
    """Limit per *targeted account*, independent of source IP.

    IP-based limits miss a distributed attempt on one account, and they also
    punish everyone behind a shared address. Keying on the submitted email
    closes both gaps: it caps attempts against a single account however many
    addresses they come from.

    The email is hashed rather than used directly so a cache dump cannot be
    read as a list of accounts that someone tried to break into.
    """

    scope = "auth-identity"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            # Nothing to key on; the IP-based throttles cover this request.
            return None

        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
        return f"throttle-identity-{digest}"
