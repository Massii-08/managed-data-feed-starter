"""HTTP fetchers and rate limiting for Feedsmith.

Provides a :class:`RateLimiter` that paces requests against public sources, a
default :class:`HttpxFetcher` with retry/backoff, and an optional
:class:`ImpersonateFetcher` that uses curl_cffi TLS impersonation to showcase
fetching from harder public sites. All time and sleep dependencies are
injectable so the behaviour is fully testable offline.
"""
from __future__ import annotations

import time
import typing
from typing import Any, Callable, Optional


class FetchError(Exception):
    """Raised when a fetch fails after exhausting retries."""

    pass


class RateLimiter:
    """Guarantee a minimum interval between successive returns from ``wait``.

    Uses an injected monotonic clock and sleep function so the spacing can be
    asserted deterministically in tests without touching the real clock.
    """

    def __init__(
        self,
        min_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store the minimum interval and the injected clock/sleep callables."""
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._last: Optional[float] = None

    def wait(self) -> None:
        """Block until at least ``min_interval_s`` has passed since last call."""
        now = self._clock()
        if self._last is not None:
            elapsed = now - self._last
            remaining = self.min_interval_s - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last = now


class Fetcher(typing.Protocol):
    """Protocol for objects able to fetch text content from a URL."""

    def get(self, url: str) -> str:
        ...


class HttpxFetcher:
    """Default fetcher backed by httpx with linear-backoff retries."""

    def __init__(
        self,
        rate: RateLimiter,
        retries: int = 3,
        timeout: float = 20.0,
        user_agent: str = "FeedsmithBot/0.1 (+https://github.com/Massii-08) public-data feed",
        client: Optional[Any] = None,
    ) -> None:
        """Configure the fetcher with a rate limiter and httpx settings."""
        self.rate = rate
        self.retries = retries
        self.timeout = timeout
        self.user_agent = user_agent
        self.client = client

    def get(self, url: str) -> str:
        """Fetch the text body at ``url``, retrying transient failures.

        Paces the request via the rate limiter, performs the GET (using the
        injected client if provided, otherwise a fresh httpx client), retries
        up to ``self.retries`` times on httpx errors or HTTP status >= 400 with
        a small linear backoff, and raises :class:`FetchError` once exhausted.
        """
        import httpx

        client = self.client
        owns_client = False
        if client is None:
            client = httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            owns_client = True

        last_error: Optional[str] = None
        try:
            for attempt in range(self.retries):
                try:
                    response = client.get(url)
                    if response.status_code >= 400:
                        last_error = "HTTP status {0}".format(response.status_code)
                    else:
                        return response.text
                except httpx.HTTPError as exc:
                    last_error = str(exc)

                if attempt < self.retries - 1:
                    self.rate._sleep(0.1 * (attempt + 1))
            raise FetchError(
                "GET {0} failed after {1} attempts: {2}".format(
                    url, self.retries, last_error
                )
            )
        finally:
            if owns_client:
                client.close()


class ImpersonateFetcher:
    """Optional fetcher using curl_cffi TLS impersonation for hard public sites."""

    def __init__(
        self,
        rate: RateLimiter,
        impersonate: str = "chrome",
        retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        """Configure the impersonating fetcher with TLS profile and retries."""
        self.rate = rate
        self.impersonate = impersonate
        self.retries = retries
        self.timeout = timeout

    def get(self, url: str) -> str:
        """Fetch ``url`` via curl_cffi, lazily importing the optional dependency.

        Raises:
            FetchError: if curl_cffi is not installed, or if all retries fail.
        """
        try:
            from curl_cffi import requests as curl_requests  # type: ignore
        except ImportError:
            raise FetchError(
                "curl_cffi not installed; pip install '.[impersonate]'"
            )

        last_error: Optional[str] = None
        for attempt in range(self.retries):
            self.rate.wait()
            try:
                response = curl_requests.get(
                    url, impersonate=self.impersonate, timeout=self.timeout
                )
                status = getattr(response, "status_code", 200)
                if status >= 400:
                    last_error = "HTTP status {0}".format(status)
                else:
                    return response.text
            except Exception as exc:  # curl_cffi raises its own error types
                last_error = str(exc)

            if attempt < self.retries - 1:
                self.rate._sleep(0.1 * (attempt + 1))

        raise FetchError(
            "GET {0} failed after {1} attempts: {2}".format(
                url, self.retries, last_error
            )
        )
