"""Minimal HTTP transport for the PrismCrawl API.

This is intentionally not an SDK: it sends one JSON body to one PrismCrawl endpoint path and turns the documented
response envelope into either a `PrismCrawlResponse` or a `PrismCrawlError`. Endpoint-specific request building lives
in separate modules (see `google_search.py`), so another endpoint can be added without touching this file.

Documented behavior this module relies on (https://www.prismcrawl.com/openapi.json):

- Authentication uses the `x-api-key` header.
- Every response is `{success, request_id, data, error?}`; `X-Request-Id` and `X-Credits-Remaining` headers may be set.
- Only successful searches consume a credit. 400/401/402/405/413 are permanent errors. 429 (`quota_exceeded`, with
  optional `reset_at`) and 500 (`internal_failure` / `overloaded`, "no quota has been deducted") are transient.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

API_BASE_URL = 'https://api.prismcrawl.com'
USER_AGENT = 'PrismCrawl-Apify-Actor/1.0'

# A live search usually completes in seconds. A timed-out request may still have succeeded (and been charged) on the
# PrismCrawl side, so timeouts are never retried; keep the limit generous.
DEFAULT_TIMEOUT_SECS = 90.0

# Only responses that PrismCrawl documents as uncharged, transient failures are retried.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
BACKOFF_BASE_SECS = 2.0
BACKOFF_MAX_SECS = 30.0
RATE_LIMIT_MAX_WAIT_SECS = 60.0

REDACTED = '***'

_STATUS_HINTS = {
    400: 'PrismCrawl rejected the request parameters. No credit was charged.',
    401: 'The PrismCrawl API key is missing, invalid, expired, or revoked. Create or rotate a key in the PrismCrawl '
    'dashboard (https://www.prismcrawl.com/).',
    402: 'Your PrismCrawl account has no credits remaining. Buy credits at https://www.prismcrawl.com/ and run again.',
    413: 'The request body is larger than PrismCrawl allows (64 KiB).',
    429: 'PrismCrawl rate limit exceeded. No credit was charged.',
}


def redact(text: str, *secrets: str | None) -> str:
    """Replace every occurrence of each non-empty secret in `text`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


@dataclass
class PrismCrawlResponse:
    """A successful (HTTP 2xx) PrismCrawl response."""

    status: int
    body: dict[str, Any]
    request_id: str | None
    credits_remaining: int | None


@dataclass
class PrismCrawlError(Exception):
    """A failed PrismCrawl call, carrying the documented error envelope fields."""

    status: int | None
    code: str
    message: str
    request_id: str | None = None
    rule: str | None = None
    reset_at: str | None = None
    body: dict[str, Any] | None = field(default=None, repr=False)
    # Set for failures that never reached PrismCrawl (DNS, connection refused) and are therefore safe to retry.
    connection_failed: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.describe())

    @property
    def retryable(self) -> bool:
        return self.connection_failed or self.status in RETRYABLE_STATUS_CODES

    def describe(self) -> str:
        """Build a single-line, user-facing error message."""
        status = f'HTTP {self.status}' if self.status is not None else 'Network error'
        message = self.message.rstrip()
        if message and message[-1] not in '.!?':
            message += '.'
        parts = [f'PrismCrawl request failed ({status}, {self.code}): {message}']
        hint = _STATUS_HINTS.get(self.status or 0)
        if hint is None and self.status is not None and self.status >= 500:  # noqa: PLR2004
            hint = 'PrismCrawl could not complete the request. No credit was charged; try again later.'
        if hint:
            parts.append(hint)
        if self.rule or self.reset_at:
            parts.append(f'Rate-limit rule: {self.rule or "unknown"}, resets at {self.reset_at or "unknown"}.')
        if self.request_id:
            parts.append(f'PrismCrawl request ID: {self.request_id} (include it when contacting support).')
        return ' '.join(parts)


class PrismCrawlClient:
    """Sends JSON POST requests to PrismCrawl with conservative retries."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API_BASE_URL,
        timeout_secs: float = DEFAULT_TIMEOUT_SECS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[PrismCrawlError, int, float], None] | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('A PrismCrawl API key is required.')
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip('/')
        self._timeout_secs = timeout_secs
        self._max_retries = max_retries
        self._sleep = sleep
        self._on_retry = on_retry

    def redact(self, text: str) -> str:
        return redact(text, self._api_key)

    def post(self, path: str, body: dict[str, Any]) -> PrismCrawlResponse:
        """POST `body` to `path`, retrying only documented transient failures."""
        attempt = 0
        while True:
            try:
                return self._post_once(path, body)
            except PrismCrawlError as error:
                if not error.retryable or attempt >= self._max_retries:
                    raise
                delay = self._retry_delay(error, attempt)
                attempt += 1
                if self._on_retry:
                    self._on_retry(error, attempt, delay)
                self._sleep(delay)

    def _retry_delay(self, error: PrismCrawlError, attempt: int) -> float:
        delay = min(BACKOFF_BASE_SECS * 2.0**attempt, BACKOFF_MAX_SECS)
        if error.status == 429 and error.reset_at:  # noqa: PLR2004
            try:
                reset_at = datetime.fromisoformat(error.reset_at.replace('Z', '+00:00'))
            except ValueError:
                return delay
            until_reset = (reset_at - datetime.now(UTC)).total_seconds()
            delay = max(delay, min(until_reset, RATE_LIMIT_MAX_WAIT_SECS))
        return delay

    def _post_once(self, path: str, body: dict[str, Any]) -> PrismCrawlResponse:
        request = urllib.request.Request(  # noqa: S310 (the URL is always the fixed https PrismCrawl API base)
            f'{self._base_url}{path}',
            data=json.dumps(body).encode(),
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': USER_AGENT,
                'x-api-key': self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_secs) as response:  # noqa: S310
                return self._parse_success(response.status, response.headers, response.read())
        except urllib.error.HTTPError as http_error:
            try:
                raw = http_error.read() if http_error.fp is not None else b''
            except OSError:
                raw = b''
            finally:
                http_error.close()
            raise self._parse_error(http_error.code, http_error.headers, raw) from None
        except urllib.error.URLError as url_error:
            raise self._network_error(url_error.reason) from None
        except (TimeoutError, OSError) as os_error:
            raise self._network_error(os_error) from None

    def _parse_success(self, status: int, headers: Any, raw: bytes) -> PrismCrawlResponse:
        payload = _load_json(raw)
        request_id = _request_id(payload, headers)
        if not isinstance(payload, dict) or payload.get('success') is not True:
            # 2xx without the documented success envelope: surface it rather than guess.
            raise self._envelope_error(status, headers, payload, default_code='unexpected_response')
        return PrismCrawlResponse(
            status=status,
            body=payload,
            request_id=request_id,
            credits_remaining=_credits_remaining(headers),
        )

    def _parse_error(self, status: int, headers: Any, raw: bytes) -> PrismCrawlError:
        return self._envelope_error(status, headers, _load_json(raw), default_code=f'http_{status}')

    def _envelope_error(self, status: int, headers: Any, payload: Any, *, default_code: str) -> PrismCrawlError:
        error = payload.get('error') if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        message = error.get('message') or 'No error message was returned.'
        return PrismCrawlError(
            status=status,
            code=str(error.get('code') or default_code),
            message=self.redact(str(message)),
            request_id=_request_id(payload, headers),
            rule=_optional_str(error.get('rule')),
            reset_at=_optional_str(error.get('reset_at')),
            body=payload if isinstance(payload, dict) else None,
        )

    def _network_error(self, reason: object) -> PrismCrawlError:
        # Connection-establishment failures (DNS, refused) mean the request never reached PrismCrawl, so they are
        # safe to retry. Timeouts and dropped connections are not: the search may have completed and been charged.
        retryable_network = isinstance(reason, (ConnectionRefusedError, socket.gaierror))
        timed_out = isinstance(reason, TimeoutError)
        message = self.redact(str(reason) or type(reason).__name__)
        if timed_out:
            message = (
                f'{message}. The search may still have completed; check your PrismCrawl request history before '
                'running again.'
            )
        return PrismCrawlError(
            status=None,
            code='connection_failed' if retryable_network else ('timeout' if timed_out else 'network_error'),
            message=message,
            connection_failed=retryable_network,
        )


def _load_json(raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _request_id(payload: Any, headers: Any) -> str | None:
    if isinstance(payload, dict) and payload.get('request_id'):
        return str(payload['request_id'])
    header_value = headers.get('X-Request-Id') if headers is not None else None
    return header_value or None


def _credits_remaining(headers: Any) -> int | None:
    value = headers.get('X-Credits-Remaining') if headers is not None else None
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
