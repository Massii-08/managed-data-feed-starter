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

from feedsmith.delivery import (
    CsvSink, JsonSink, ParquetSink, Sink, SnapshotSink, TeeSink, WebhookSink,
)
from feedsmith.fetcher import Fetcher, HttpxFetcher, ImpersonateFetcher, RateLimiter
from feedsmith.stealth import StealthFetcher
from feedsmith.models import FieldPolicy, Record, utcnow_iso
from feedsmith.monitor import FeedHealth, Monitor
from feedsmith.scraper import BookstoreScraper, PriceScraper, Scraper
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
    if output.kind == "parquet":
        return ParquetSink(output.path)
    if output.kind == "webhook":
        return WebhookSink(output.url)
    raise ValueError("Unknown output kind: %r" % (output.kind,))


def _build_scraper(config: "FeedConfig") -> Scraper:
    """Pick the scraper implementation named by ``config.scraper``."""
    if config.scraper == "price":
        return PriceScraper(config.urls)
    return BookstoreScraper(config.urls)


def _build_fetcher(config: "FeedConfig", rate: RateLimiter) -> Fetcher:
    """Pick the fetcher implementation named by ``config.fetcher``."""
    if config.fetcher == "impersonate":
        return ImpersonateFetcher(rate)
    if config.fetcher == "stealth":
        return StealthFetcher(rate, warm_url=config.warm_url)
    return HttpxFetcher(rate)


def build_runner(
    config: "FeedConfig",
    store: Any = None,
) -> Tuple[FeedRunner, FeedHealth]:
    """Construct a runner from config WITHOUT any network call.

    Wires a rate-limited HTTP fetcher, the scraper named by config, the field
    policy, the configured sink, fresh health, and a default monitor. When a
    ``store`` is supplied, deliveries are teed to a :class:`SnapshotSink`
    (first) plus the configured file sink, so the live API is fed without
    changing the CLI (which passes ``store=None``).
    """
    rate = RateLimiter(config.rate_limit_seconds)
    fetcher = _build_fetcher(config, rate)
    scraper = _build_scraper(config)
    policy = FieldPolicy(config.fields)
    base_sink = _build_sink(config.output)
    if store is not None:
        sink: Sink = TeeSink([SnapshotSink(config.id, store), base_sink])
    else:
        sink = base_sink
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
