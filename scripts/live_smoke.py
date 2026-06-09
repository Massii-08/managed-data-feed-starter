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


if __name__ == "__main__":
    main()
