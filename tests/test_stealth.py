"""Tests for the stealth fetcher tier (offline; no real browser)."""
from __future__ import annotations

import pytest

from feedsmith.stealth import is_challenge, jitter_delay


def test_is_challenge_detects_cloudflare_titles() -> None:
    assert is_challenge("Just a moment...") is True
    assert is_challenge("Un instant…") is True
    assert is_challenge("Checking your browser") is True
    assert is_challenge("") is True   # empty/not-loaded counts as challenge


def test_is_challenge_passes_real_titles() -> None:
    assert is_challenge("Books to Scrape - All products") is False
    assert is_challenge("BTC-EUR spot price") is False


def test_jitter_delay_is_bounded_by_injected_rng() -> None:
    # rng is injectable: assert the bounds are forwarded and value returned.
    seen = {}

    def fake_rng(lo, hi):
        seen["lo"], seen["hi"] = lo, hi
        return (lo + hi) / 2

    val = jitter_delay(rng=fake_rng, lo=3.0, hi=8.0)
    assert seen == {"lo": 3.0, "hi": 8.0}
    assert val == 5.5


from feedsmith.fetcher import FetchError, RateLimiter
from feedsmith.stealth import StealthFetcher


class FakeSession:
    """Scriptable BrowserSession: titles is a list consumed per title() call."""

    def __init__(self, titles, content="<html>OK</html>"):
        self._titles = list(titles)
        self._content = content
        self.goto_calls = []
        self._last_title = "ready"

    def goto(self, url):
        self.goto_calls.append(url)

    def title(self):
        if self._titles:
            self._last_title = self._titles.pop(0)
        return self._last_title

    def content(self):
        return self._content


def _rate():
    return RateLimiter(0.0, clock=lambda: 0.0, sleep=lambda s: None)


def test_stealth_happy_path_returns_content_and_paces() -> None:
    slept = []
    sess = FakeSession(titles=["Books to Scrape"], content="<html>books</html>")
    f = StealthFetcher(_rate(), session=sess, sleep=lambda s: slept.append(s),
                       jitter=lambda: 4.2, max_wait_s=5, retries=2)
    out = f.get("https://target/page")
    assert out == "<html>books</html>"
    assert sess.goto_calls == ["https://target/page"]
    assert 4.2 in slept  # human jitter was applied


def test_stealth_warms_once_then_fetches() -> None:
    sess = FakeSession(titles=["ready", "ready"], content="<html>x</html>")
    f = StealthFetcher(_rate(), session=sess, warm_url="https://target/",
                       sleep=lambda s: None, jitter=lambda: 0.0,
                       max_wait_s=5, retries=2)
    f.get("https://target/a")
    f.get("https://target/b")
    # warm URL hit exactly once (first call), then each target once.
    assert sess.goto_calls == ["https://target/", "https://target/a",
                               "https://target/b"]


def test_stealth_waits_through_challenge_then_resolves() -> None:
    # title() returns challenge twice, then a real title.
    sess = FakeSession(titles=["Just a moment...", "Just a moment...",
                               "Books to Scrape"], content="<html>ok</html>")
    f = StealthFetcher(_rate(), session=sess, sleep=lambda s: None,
                       jitter=lambda: 0.0, max_wait_s=10, retries=2)
    assert f.get("https://target/p") == "<html>ok</html>"


def test_stealth_persistent_challenge_raises_without_infinite_loop() -> None:
    sess = FakeSession(titles=["Just a moment..."] * 1000)
    f = StealthFetcher(_rate(), session=sess, warm_url="https://t/",
                       sleep=lambda s: None, jitter=lambda: 0.0,
                       max_wait_s=3, retries=2)
    with pytest.raises(FetchError):
        f.get("https://target/blocked")
    # bounded: warm + (goto target) per retry, not unbounded.
    assert len(sess.goto_calls) <= 8


def test_patchright_session_missing_dep_raises(monkeypatch) -> None:
    import sys

    from feedsmith.stealth import PatchrightBrowserSession

    # Force the lazy `from patchright...` import to fail regardless of whether
    # patchright is installed, so this test never launches a real browser.
    monkeypatch.setitem(sys.modules, "patchright", None)
    monkeypatch.setitem(sys.modules, "patchright.sync_api", None)
    sess = PatchrightBrowserSession(profile="/tmp/feedsmith_stealth_test")
    with pytest.raises(FetchError):
        sess.goto("https://example.com")
