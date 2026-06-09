"""Tests for feedsmith.fetcher: RateLimiter, HttpxFetcher, ImpersonateFetcher.

All tests run fully offline: the rate limiter uses an injected fake clock and a
sleep recorder, and the HTTP fetcher uses httpx.MockTransport so no real
network request is made.
"""
from __future__ import annotations

from typing import List

import httpx
import pytest

from feedsmith.fetcher import (
    FetchError,
    HttpxFetcher,
    ImpersonateFetcher,
    RateLimiter,
)


class FakeClock:
    """Deterministic monotonic clock driven by a preset list of tick values."""

    def __init__(self, ticks: List[float]) -> None:
        self._ticks = list(ticks)

    def __call__(self) -> float:
        # Hold the last value once exhausted (defensive against extra reads).
        if len(self._ticks) > 1:
            return self._ticks.pop(0)
        return self._ticks[0]


def test_rate_limiter_first_call_does_not_sleep() -> None:
    slept: List[float] = []
    clock = FakeClock([100.0])
    rl = RateLimiter(min_interval_s=1.0, clock=clock, sleep=lambda s: slept.append(s))
    rl.wait()
    assert slept == []


def test_rate_limiter_spaces_calls_with_injected_clock_and_sleep() -> None:
    slept: List[float] = []
    # First call reads t=100. Second call reads t=100.3 (only 0.3s elapsed),
    # so it must sleep the remaining 0.7s to honour the 1.0s interval; the
    # post-sleep clock read returns 101.0 (used as the new "last").
    clock = FakeClock([100.0, 100.3, 101.0])
    rl = RateLimiter(min_interval_s=1.0, clock=clock, sleep=lambda s: slept.append(s))
    rl.wait()
    rl.wait()
    assert slept == [pytest.approx(0.7)]


def test_rate_limiter_no_sleep_when_interval_already_elapsed() -> None:
    slept: List[float] = []
    # Second call reads t=102.0 -> 2.0s elapsed >= 1.0s -> no sleep.
    clock = FakeClock([100.0, 102.0])
    rl = RateLimiter(min_interval_s=1.0, clock=clock, sleep=lambda s: slept.append(s))
    rl.wait()
    rl.wait()
    assert slept == []


def _silent_rate() -> RateLimiter:
    """A rate limiter whose clock/sleep never touch the real clock."""
    return RateLimiter(
        min_interval_s=0.0,
        clock=lambda: 0.0,
        sleep=lambda s: None,
    )


def test_httpx_fetcher_success_returns_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>ok</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = HttpxFetcher(rate=_silent_rate(), retries=3, client=client)
    assert fetcher.get("https://books.toscrape.com/") == "<html>ok</html>"


def test_httpx_fetcher_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text="recovered")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = HttpxFetcher(rate=_silent_rate(), retries=3, client=client)
    assert fetcher.get("https://example.com/") == "recovered"
    assert calls["n"] == 3


def test_httpx_fetcher_raises_fetcherror_after_retries_exhausted() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = HttpxFetcher(rate=_silent_rate(), retries=3, client=client)
    with pytest.raises(FetchError):
        fetcher.get("https://example.com/")
    assert calls["n"] == 3


def test_httpx_fetcher_retries_on_transport_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("no route", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = HttpxFetcher(rate=_silent_rate(), retries=2, client=client)
    with pytest.raises(FetchError):
        fetcher.get("https://example.com/")
    assert calls["n"] == 2


def test_impersonate_fetcher_raises_when_curl_cffi_absent() -> None:
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "curl_cffi" or name.startswith("curl_cffi."):
            raise ImportError("No module named 'curl_cffi'")
        return real_import(name, *args, **kwargs)

    fetcher = ImpersonateFetcher(rate=_silent_rate())
    builtins.__import__ = blocked_import
    try:
        with pytest.raises(FetchError):
            fetcher.get("https://example.com/")
    finally:
        builtins.__import__ = real_import
