"""HTTP client for source adapters.

Compliance notes (deliberate design decisions)
----------------------------------------------
* **429, 403 and 401 are never retried.** A rate limit or an access denial is a
  signal to stop, not to try harder. Retrying them is a circumvention technique
  and is explicitly out of scope for this project.
* **`Retry-After` is honoured** when the server supplies it, and surfaced to the
  caller so a scheduler can back off properly.
* **No user-agent rotation, no proxy rotation, no cookie reuse.** Requests carry
  a single, honest, identifying user agent.
* Only genuinely transient conditions are retried: timeouts and 5xx/408/425.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "SmartCoverLetterAgent/1.0 (+https://example.com/bot)"

#: Statuses worth retrying: transient infrastructure problems only.
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 425, 500, 502, 503, 504})

#: Statuses that mean "you are not permitted". Never retried.
BLOCKED_STATUSES: frozenset[int] = frozenset({401, 403, 429})

#: Encodings `requests` may report when the server declared no charset. RFC 2616
#: makes ISO-8859-1 the default, so seeing one of these means "unknown, guessed"
#: rather than "the server said Latin-1".
_LATIN1_FALLBACK_ENCODINGS: frozenset[str] = frozenset(
    {"iso-8859-1", "latin-1", "latin1", "latin_1", ""}
)


class SourceBlocked(RuntimeError):
    """The source refused access.

    Deliberately **not** retried. Raised so the pipeline can report the source
    as unavailable and move on, rather than escalating.
    """

    def __init__(self, status_code: int, url: str, retry_after: float | None = None):
        self.status_code = status_code
        self.url = url
        self.retry_after = retry_after
        message = {
            401: "authentication required",
            403: "access forbidden",
            429: "rate limited",
        }.get(status_code, f"HTTP {status_code}")
        message = f"HTTP {status_code} ({message})"
        if retry_after is not None:
            message += f" (retry after {retry_after:.0f}s)"
        super().__init__(f"{message}: {url}")


@dataclass
class RetryPolicy:
    """Bounded retry behaviour for transient failures."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    #: Jitter avoids synchronised retries when several searches run at once.
    jitter: float = 0.3

    def delay_for(self, attempt: int) -> float:
        delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        if self.jitter:
            delay *= 1 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, delay)


def _parse_retry_after(response: requests.Response) -> float | None:
    """Read `Retry-After` as seconds, supporting both forms of the header."""

    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(raw)
        return max(0.0, (when - parsedate_to_datetime(response.headers["Date"])).total_seconds())
    except Exception:  # noqa: BLE001 - malformed header is not fatal
        return None


class SourceHttpClient:
    """Small, honest HTTP client shared by every adapter."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 20.0,
        policy: RetryPolicy | None = None,
        respect_politeness_delay: bool = True,
    ):
        self.timeout = timeout
        self.policy = policy or RetryPolicy()
        self.respect_politeness_delay = respect_politeness_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            }
        )

    # -- public API -------------------------------------------------------- #

    def get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> SourceHttpClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- internals --------------------------------------------------------- #

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_error: Exception | None = None

        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.Timeout as exc:
                last_error = exc
                logger.warning("Timeout on %s (attempt %s/%s)", url, attempt, self.policy.max_attempts)
            except requests.RequestException as exc:
                # Connection errors are usually transient.
                last_error = exc
                logger.warning("Request error on %s: %s", url, exc)
            else:
                if response.status_code in BLOCKED_STATUSES:
                    # Stop immediately. Do not escalate or circumvent.
                    raise SourceBlocked(
                        response.status_code, url, retry_after=_parse_retry_after(response)
                    )

                if response.status_code in RETRYABLE_STATUSES:
                    last_error = requests.HTTPError(
                        f"HTTP {response.status_code}", response=response
                    )
                    retry_after = _parse_retry_after(response)
                    if retry_after is not None and retry_after > self.policy.max_delay:
                        # Waiting longer than we are willing to is pointless.
                        raise requests.HTTPError(
                            f"HTTP {response.status_code} (retry-after {retry_after:.0f}s)",
                            response=response,
                        )
                elif response.status_code >= 400:
                    # 4xx that is not a block: a genuine client error. No retry.
                    response.raise_for_status()
                    return _correct_encoding(response)
                else:
                    return _correct_encoding(response)

            if attempt < self.policy.max_attempts:
                delay = self.policy.delay_for(attempt)
                if self.respect_politeness_delay and delay:
                    time.sleep(delay)

        raise last_error if last_error else RuntimeError(f"Request to {url} failed")


def _charset_from_header(response: requests.Response) -> str:
    """Return the charset the server explicitly declared, or "".

    `requests` sets `response.encoding` to ISO-8859-1 in two different
    situations and the attribute alone cannot tell them apart:

    * the server sent `Content-Type: text/html; charset=iso-8859-1`, or
    * the server sent no charset at all and `requests` applied the RFC 2616
      default.

    Only the first is an assertion we should honour, so read the raw header.
    """

    header = response.headers.get("Content-Type", "")
    match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", header, re.IGNORECASE)
    return match.group(1).strip().lower() if match else ""


def _correct_encoding(response: requests.Response) -> requests.Response:
    """Fix text that was decoded as Latin-1 but is really UTF-8.

    Some German sites omit a charset from the `Content-Type` header. `requests`
    then falls back to ISO-8859-1 per RFC 2616, which mangles umlauts: "für"
    becomes "fÃ¼r" and "·" becomes "Â·".

    When the server explicitly declared its charset we take it at its word —
    overriding an explicit declaration would corrupt genuinely Latin-1 pages.
    Only the implicit RFC fallback is second-guessed, using the detected
    encoding.

    Without this, German job titles and company names arrive corrupted and the
    employment classifier cannot match terms like "Werkstudent" reliably.
    """

    if _charset_from_header(response):
        return response

    declared = (response.encoding or "").lower()
    if declared not in _LATIN1_FALLBACK_ENCODINGS:
        return response

    detected = response.apparent_encoding
    if detected and detected.lower() not in _LATIN1_FALLBACK_ENCODINGS:
        response.encoding = detected
    return response
