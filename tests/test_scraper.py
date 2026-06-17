"""Offline tests for the BookstoreScraper.

Self-contained: loads a local HTML fixture and asserts the scraper extracts
exactly the four factual, non-PII fields per product.
"""
from __future__ import annotations

import os
from typing import List

from feedsmith.models import PII_FIELDS
from feedsmith.scraper import BookstoreScraper

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "books_page.html"
)


def _load_fixture() -> str:
    """Read the local catalogue HTML fixture as text."""
    with open(FIXTURE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def test_default_urls() -> None:
    """Default URL list points at catalogue page 1."""
    scraper = BookstoreScraper()
    assert scraper.urls() == [
        "https://books.toscrape.com/catalogue/page-1.html"
    ]


def test_custom_urls() -> None:
    """Custom URLs are stored and returned as a copy."""
    custom = ["https://books.toscrape.com/catalogue/page-2.html"]
    scraper = BookstoreScraper(urls=custom)
    assert scraper.urls() == custom
    # Returned list is a copy, not the internal reference.
    scraper.urls().append("mutated")
    assert scraper.urls() == custom


def test_scrape_returns_three_records() -> None:
    """Scraping the fixture yields at least three product dicts."""
    scraper = BookstoreScraper()
    records = scraper.scrape(_load_fixture())
    assert len(records) >= 3


def test_scrape_fields_exact() -> None:
    """Each record has exactly the four declared FIELDS as keys."""
    scraper = BookstoreScraper()
    records = scraper.scrape(_load_fixture())
    expected_keys = set(BookstoreScraper.FIELDS)
    for rec in records:
        assert set(rec.keys()) == expected_keys


def test_scrape_expected_values() -> None:
    """Specific titles, prices, stripped availability and ratings match."""
    scraper = BookstoreScraper()
    records = scraper.scrape(_load_fixture())

    by_title = {rec["title"]: rec for rec in records}

    light = by_title["A Light in the Attic"]
    assert light["price"] == "£51.77"
    assert light["availability"] == "In stock"
    assert light["rating"] == "Three"

    velvet = by_title["Tipping the Velvet"]
    assert velvet["price"] == "£53.74"
    assert velvet["availability"] == "In stock"
    assert velvet["rating"] == "One"

    soumission = by_title["Soumission"]
    assert soumission["price"] == "£50.10"
    assert soumission["availability"] == "In stock"
    assert soumission["rating"] == "Five"


def test_availability_is_stripped() -> None:
    """Availability text has no surrounding whitespace or newlines."""
    scraper = BookstoreScraper()
    records = scraper.scrape(_load_fixture())
    for rec in records:
        avail = rec["availability"]
        assert avail == avail.strip()
        assert "\n" not in avail


def test_no_pii_keys() -> None:
    """No scraped key collides with the PII field policy set."""
    scraper = BookstoreScraper()
    records = scraper.scrape(_load_fixture())
    pii_lower = {p.lower() for p in PII_FIELDS}
    for rec in records:
        for key in rec.keys():
            assert key.lower() not in pii_lower


def test_scrape_empty_html() -> None:
    """HTML with no product pods yields an empty list."""
    scraper = BookstoreScraper()
    result: List = scraper.scrape("<html><body><p>nothing here</p></body></html>")
    assert result == []


def test_price_scraper_parses_coinbase_spot_payload() -> None:
    from feedsmith.scraper import PriceScraper

    payload = '{"data":{"amount":"58234.91","base":"BTC","currency":"EUR"}}'
    scraper = PriceScraper(["https://api.coinbase.com/v2/prices/BTC-EUR/spot"])
    assert scraper.source == "api.coinbase.com"
    rows = scraper.scrape(payload)
    assert rows == [{"pair": "BTC-EUR", "price": "58234.91", "currency": "EUR"}]


def test_price_scraper_default_urls_cover_two_pairs() -> None:
    from feedsmith.scraper import PriceScraper

    urls = PriceScraper().urls()
    assert any("BTC-EUR" in u for u in urls)
    assert any("ETH-EUR" in u for u in urls)


def test_price_scraper_returns_empty_on_malformed_payload() -> None:
    from feedsmith.scraper import PriceScraper

    scraper = PriceScraper()
    assert scraper.scrape('{"data":{}}') == []
