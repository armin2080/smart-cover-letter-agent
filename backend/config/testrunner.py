"""Test runner that isolates rate-limit counters between tests.

The throttle counters live in a cache, and caches are deliberately not
transactional — `TestCase`'s rollback does not touch them. Without isolation the
counters accumulate across the whole run, and the suite makes far more than five
requests to the login and register endpoints, so unrelated tests begin receiving
429 responses that have nothing to do with what they assert.

Clearing per *test* rather than per class or per run is the right granularity: it
keeps the limits genuinely active within a test, which is what
`AuthRateLimitTests` depends on, while stopping state leaking between them.

The suite is walked and each test's `run` method is wrapped, rather than
reimplementing `TestSuite.run`. That leaves class-level setup, fixtures and
skipping entirely in unittest's hands.
"""

from __future__ import annotations

import unittest

from django.core.cache import caches
from django.test.runner import DiscoverRunner


def _wrap(test: unittest.TestCase) -> unittest.TestCase:
    """Clear the throttle cache immediately before this test runs."""

    original_run = test.run

    def run(result=None):  # noqa: ANN001 - mirrors unittest's signature
        try:
            caches["throttle"].clear()
        except Exception:  # noqa: BLE001 - a missing cache must not break the run
            pass
        return original_run(result)

    test.run = run
    return test


def _isolate(suite: unittest.TestSuite) -> unittest.TestSuite:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            _isolate(item)
        else:
            _wrap(item)
    return suite


class IsolatedThrottleTestRunner(DiscoverRunner):
    """Wrap every test so its throttle counters start from zero."""

    def build_suite(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _isolate(super().build_suite(*args, **kwargs))
