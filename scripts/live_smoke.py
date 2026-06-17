"""Manual live smoke test for Feedsmith scraping.

This is the ONLY file in the project that touches the network. It is meant for
manual smoke-testing the scraping pipeline against the public books.toscrape.com
sandbox (a sanctioned target for scraping). Run it by hand:

    python scripts/live_smoke.py

It fetches a real catalogue page, scrapes the factual / non-PII fields, and
prints the first few records plus a total count. It is never imported by tests.
"""
from __future__ import annotations

from typing import List

from feedsmith.fetcher import HttpxFetcher, RateLimiter
from feedsmith.scraper import BookstoreScraper


def main() -> None:
    """Fetch a real catalogue page and print scraped records."""
    rate = RateLimiter(min_interval_s=1.5)
    fetcher = HttpxFetcher(rate=rate)
    scraper = BookstoreScraper()

    records: List[dict] = []
    for url in scraper.urls():
        html = fetcher.get(url)
        records += scraper.scrape(html)

    print("Source:", scraper.source)
    print("Total records scraped:", len(records))
    print("First few records:")
    for rec in records[:5]:
        print("  -", rec)


def smoke_live_feeds() -> None:
    """Run both demo feeds once against their real sources (network)."""
    import os

    from feedsmith.api import REPO_ROOT
    from feedsmith.config import load_feed_config
    from feedsmith.runner import build_runner
    from feedsmith.store import SnapshotStore

    store = SnapshotStore()
    for name in ("books_demo.yaml", "prices_demo.yaml"):
        config = load_feed_config(os.path.join(REPO_ROOT, "feeds", name))
        runner, _ = build_runner(config, store=store)
        result = runner.run_once()
        snap = store.latest(config.id)
        print("%s ok=%s count=%s stored=%s"
              % (config.id, result.ok, result.record_count,
                 0 if snap is None else len(snap.records)))
        assert result.ok, "feed %s failed: %s" % (config.id, result.error)
        assert snap is not None and snap.records, "feed %s empty" % config.id


if __name__ == "__main__":
    main()
    print()
    smoke_live_feeds()
