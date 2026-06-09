"""Offline tests for FeedRunner orchestration and build_runner wiring."""
from __future__ import annotations

from typing import Any, Dict, List

from feedsmith.models import FieldPolicy, PolicyViolation, Record
from feedsmith.monitor import FeedHealth, Monitor
from feedsmith.runner import FeedRunner, build_runner

FIXED_NOW = "2026-01-01T00:00:00+00:00"


class FakeFetcher:
    """Fetcher returning canned HTML keyed by URL, or raising on demand."""

    def __init__(self, html: str = "<html></html>", raise_exc: Any = None) -> None:
        self.html = html
        self.raise_exc = raise_exc
        self.calls: List[str] = []

    def get(self, url: str) -> str:
        self.calls.append(url)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.html


class FakeScraper:
    """Scraper returning preset raw dicts; ignores the HTML content."""

    source = "fake.source"

    def __init__(self, raw_records: List[Dict[str, Any]]) -> None:
        self._raw = raw_records

    def urls(self) -> List[str]:
        return ["https://fake.source/page-1.html"]

    def scrape(self, html: str) -> List[Dict[str, Any]]:
        return list(self._raw)


class FakeSink:
    """Sink that records the delivered records and returns a fixed output."""

    def __init__(self, output: str = "fake://output") -> None:
        self.output = output
        self.delivered: List[Record] = []
        self.calls = 0

    def deliver(self, records: List[Record]) -> str:
        self.calls += 1
        self.delivered = list(records)
        return self.output


class RecordingMonitor:
    """Monitor stub that records each observed health snapshot."""

    def __init__(self) -> None:
        self.observed: List[int] = []

    def observe(self, health: FeedHealth) -> None:
        self.observed.append(health.consecutive_failures)


def _now() -> str:
    return FIXED_NOW


def test_run_once_happy_path() -> None:
    """Happy path: records delivered, health success, monitor observed."""
    raw = [
        {"title": "Book A", "price": "£10.00"},
        {"title": "Book B", "price": "£20.00"},
    ]
    fetcher = FakeFetcher(html="<html>ignored</html>")
    scraper = FakeScraper(raw)
    policy = FieldPolicy(["title", "price"])
    sink = FakeSink()
    health = FeedHealth("feed-happy")
    monitor = RecordingMonitor()

    runner = FeedRunner(
        "feed-happy", fetcher, scraper, policy, sink, health, monitor, now=_now
    )
    result = runner.run_once()

    assert result.ok is True
    assert result.feed_id == "feed-happy"
    assert result.record_count == 2
    assert result.output == "fake://output"
    assert result.error is None

    # Sink got exactly the cleaned records.
    assert sink.calls == 1
    assert len(sink.delivered) == 2
    assert isinstance(sink.delivered[0], Record)
    assert sink.delivered[0].source == "fake.source"
    assert sink.delivered[0].fetched_at == FIXED_NOW
    assert sink.delivered[0].fields == {"title": "Book A", "price": "£10.00"}

    # Health recorded a success.
    assert health.total_runs == 1
    assert health.total_failures == 0
    assert health.consecutive_failures == 0
    assert health.last_success_at == FIXED_NOW
    assert health.status == "healthy"

    # Monitor observed exactly once.
    assert monitor.observed == [0]


def test_run_once_drops_disallowed_fields() -> None:
    """Policy silently drops keys not in the allowed set (no PII present)."""
    raw = [{"title": "Book A", "price": "£10.00", "extra": "drop-me"}]
    fetcher = FakeFetcher()
    scraper = FakeScraper(raw)
    policy = FieldPolicy(["title", "price"])
    sink = FakeSink()
    health = FeedHealth("feed-drop")
    monitor = RecordingMonitor()

    runner = FeedRunner(
        "feed-drop", fetcher, scraper, policy, sink, health, monitor, now=_now
    )
    result = runner.run_once()

    assert result.ok is True
    assert sink.delivered[0].fields == {"title": "Book A", "price": "£10.00"}


def test_run_once_failure_when_fetch_raises() -> None:
    """Fetch error path: ok False, health failure, monitor still observed."""
    fetcher = FakeFetcher(raise_exc=RuntimeError("network down"))
    scraper = FakeScraper([{"title": "x"}])
    policy = FieldPolicy(["title"])
    sink = FakeSink()
    health = FeedHealth("feed-fail")
    monitor = RecordingMonitor()

    runner = FeedRunner(
        "feed-fail", fetcher, scraper, policy, sink, health, monitor, now=_now
    )
    result = runner.run_once()  # must NOT raise

    assert result.ok is False
    assert result.record_count == 0
    assert result.output is None
    assert result.error == "network down"

    # Sink never called.
    assert sink.calls == 0

    # Health recorded a failure.
    assert health.total_runs == 1
    assert health.total_failures == 1
    assert health.consecutive_failures == 1
    assert health.last_error == "network down"
    assert health.status == "degraded"

    # Monitor observed even on failure.
    assert monitor.observed == [1]


def test_run_once_failure_on_policy_violation() -> None:
    """A PII key triggers PolicyViolation, captured as a failed run."""
    raw = [{"title": "Book A", "email": "leak@example.test"}]
    fetcher = FakeFetcher()
    scraper = FakeScraper(raw)
    policy = FieldPolicy(["title"])
    sink = FakeSink()
    health = FeedHealth("feed-pii")
    monitor = RecordingMonitor()

    runner = FeedRunner(
        "feed-pii", fetcher, scraper, policy, sink, health, monitor, now=_now
    )
    result = runner.run_once()

    assert result.ok is False
    assert result.error is not None
    assert sink.calls == 0
    assert health.consecutive_failures == 1
    # Sanity: the policy really does reject this directly.
    try:
        policy.validate({"email": "x"})
        raised = False
    except PolicyViolation:
        raised = True
    assert raised is True


def test_run_once_never_raises_on_sink_error() -> None:
    """An exception inside the sink is captured, not propagated."""

    class BoomSink:
        def deliver(self, records: List[Record]) -> str:
            raise ValueError("disk full")

    fetcher = FakeFetcher()
    scraper = FakeScraper([{"title": "Book A"}])
    policy = FieldPolicy(["title"])
    health = FeedHealth("feed-sink")
    monitor = RecordingMonitor()

    runner = FeedRunner(
        "feed-sink", fetcher, scraper, policy, BoomSink(), health, monitor, now=_now
    )
    result = runner.run_once()

    assert result.ok is False
    assert result.error == "disk full"
    assert health.consecutive_failures == 1
    assert monitor.observed == [1]


def test_build_runner_no_network() -> None:
    """build_runner constructs a runner from real config; zero network."""
    from feedsmith.config import (
        FeedConfig,
        OutputConfig,
        ScheduleConfig,
    )

    config = FeedConfig(
        id="books-demo",
        source="books.toscrape.com",
        fields=["title", "price", "availability", "rating"],
        rate_limit_seconds=1.5,
        urls=["https://books.toscrape.com/catalogue/page-1.html"],
        schedule=ScheduleConfig(interval_seconds=3600),
        output=OutputConfig(kind="csv", path="data/books-demo.csv"),
    )

    runner, health = build_runner(config)

    assert isinstance(runner, FeedRunner)
    assert isinstance(health, FeedHealth)
    assert runner.feed_id == "books-demo"
    assert health.feed_id == "books-demo"
    # The scraper is wired with the configured URLs.
    assert runner.scraper.urls() == [
        "https://books.toscrape.com/catalogue/page-1.html"
    ]
    # Health starts clean (no run has happened, so no network occurred).
    assert health.total_runs == 0
    assert health.status == "healthy"


def test_build_runner_webhook_output() -> None:
    """build_runner wires a webhook sink when configured."""
    from feedsmith.config import (
        FeedConfig,
        OutputConfig,
        ScheduleConfig,
    )
    from feedsmith.delivery import WebhookSink

    config = FeedConfig(
        id="wh",
        source="books.toscrape.com",
        fields=["title"],
        schedule=ScheduleConfig(cron="0 * * * *"),
        output=OutputConfig(kind="webhook", url="https://example.test/hook"),
    )
    runner, _health = build_runner(config)
    assert isinstance(runner.sink, WebhookSink)
    assert runner.sink.url == "https://example.test/hook"
