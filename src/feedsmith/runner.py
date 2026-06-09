"""Single-run feed orchestration and no-network runner construction.

:class:`FeedRunner` fetches public source pages, scrapes factual non-PII
fields, applies the field policy, delivers the clean records, and updates
health — never raising. :func:`build_runner` wires a runner from config
without performing any network call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

import typing

from feedsmith.delivery import CsvSink, JsonSink, Sink, WebhookSink
from feedsmith.fetcher import Fetcher, HttpxFetcher, RateLimiter
from feedsmith.models import FieldPolicy, Record, utcnow_iso
from feedsmith.monitor import FeedHealth, Monitor
from feedsmith.scraper import BookstoreScraper, Scraper
from feedsmith.transform import transform

if typing.TYPE_CHECKING:  # avoid import cycle with config.py
    from feedsmith.config import FeedConfig


@dataclass
class RunResult:
    """Outcome of a single feed run."""

    feed_id: str
    ok: bool
    record_count: int
    output: Optional[str]
    error: Optional[str]


class FeedRunner:
    """Run one feed end-to-end: fetch -> scrape -> policy -> deliver."""

    def __init__(
        self,
        feed_id: str,
        fetcher: Fetcher,
        scraper: Scraper,
        policy: FieldPolicy,
        sink: Sink,
        health: FeedHealth,
        monitor: Monitor,
        now: Callable[[], str] = utcnow_iso,
    ) -> None:
        """Store all collaborators needed for a run."""
        self.feed_id = feed_id
        self.fetcher = fetcher
        self.scraper = scraper
        self.policy = policy
        self.sink = sink
        self.health = health
        self.monitor = monitor
        self.now = now

    def run_once(self) -> RunResult:
        """Execute one run. Never raises; always observes the monitor.

        On success: deliver records and record health success.
        On any exception: record health failure and capture the error.
        The monitor observes the health in a ``finally`` block.
        """
        result: RunResult
        try:
            raw: List[dict] = []
            for url in self.scraper.urls():
                raw += self.scraper.scrape(self.fetcher.get(url))
            records: List[Record] = transform(
                raw, self.policy, self.scraper.source, self.now()
            )
            output = self.sink.deliver(records)
            self.health.record_success(self.now())
            result = RunResult(
                feed_id=self.feed_id,
                ok=True,
                record_count=len(records),
                output=output,
                error=None,
            )
        except Exception as exc:  # fail-safe: never propagate
            self.health.record_failure(self.now(), str(exc))
            result = RunResult(
                feed_id=self.feed_id,
                ok=False,
                record_count=0,
                output=None,
                error=str(exc),
            )
        finally:
            self.monitor.observe(self.health)
        return result


def _build_sink(output: Any) -> Sink:
    """Construct a sink from an output config (csv / json / webhook)."""
    if output.kind == "csv":
        return CsvSink(output.path)
    if output.kind == "json":
        return JsonSink(output.path)
    if output.kind == "webhook":
        return WebhookSink(output.url)
    raise ValueError("Unknown output kind: %r" % (output.kind,))


def build_runner(config: "FeedConfig") -> Tuple[FeedRunner, FeedHealth]:
    """Construct a runner from config WITHOUT any network call.

    Wires a rate-limited HTTP fetcher, the bookstore scraper, the field
    policy, the configured sink, fresh health, and a default monitor.
    """
    rate = RateLimiter(config.rate_limit_seconds)
    fetcher = HttpxFetcher(rate)
    scraper = BookstoreScraper(config.urls)
    policy = FieldPolicy(config.fields)
    sink = _build_sink(config.output)
    health = FeedHealth(config.id)
    monitor = Monitor()
    runner = FeedRunner(
        config.id,
        fetcher,
        scraper,
        policy,
        sink,
        health,
        monitor,
    )
    return runner, health
