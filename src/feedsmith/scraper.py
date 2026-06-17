"""HTML scrapers for Feedsmith feeds.

Scrapers parse HTML from public sources into lists of raw field dicts. The
demo target is a sanctioned scraping sandbox (books.toscrape.com), whose
e-commerce price/stock data is factual and non-PII by construction.
"""
from __future__ import annotations

import json
import typing
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


class Scraper(typing.Protocol):
    """Structural interface for a feed scraper."""

    source: str

    def urls(self) -> List[str]:
        """Return the list of page URLs to fetch for this source."""
        ...

    def scrape(self, html: str) -> List[Dict[str, Any]]:
        """Parse one page of HTML into a list of raw field dicts."""
        ...


class BookstoreScraper:
    """Scraper for the public books.toscrape.com sandbox catalogue.

    Extracts factual, non-PII product data (title, price, availability,
    rating) from each ``article.product_pod`` block.
    """

    source = "books.toscrape.com"
    FIELDS = ("title", "price", "availability", "rating")

    def __init__(self, urls: Optional[List[str]] = None) -> None:
        """Store the page URLs to scrape (defaults to catalogue page 1)."""
        self._urls = urls if urls is not None else [
            "https://books.toscrape.com/catalogue/page-1.html"
        ]

    def urls(self) -> List[str]:
        """Return the configured list of page URLs."""
        return list(self._urls)

    def scrape(self, html: str) -> List[Dict[str, Any]]:
        """Parse the catalogue HTML into raw product dicts.

        For each ``article.product_pod``: title comes from the ``title``
        attribute of the ``h3 > a`` anchor; price from ``p.price_color``;
        availability from ``p.instock.availability`` (stripped); rating from
        the second class of ``p.star-rating`` (e.g. "Three").
        """
        soup = BeautifulSoup(html, "html.parser")
        records: List[Dict[str, Any]] = []

        for pod in soup.select("article.product_pod"):
            title = ""
            anchor = pod.select_one("h3 > a")
            if anchor is not None:
                title = anchor.get("title", "") or ""

            price = ""
            price_el = pod.select_one("p.price_color")
            if price_el is not None:
                price = price_el.get_text()

            availability = ""
            avail_el = pod.select_one("p.instock.availability")
            if avail_el is not None:
                availability = avail_el.get_text().strip()

            rating = ""
            star_el = pod.select_one("p.star-rating")
            if star_el is not None:
                classes = star_el.get("class", []) or []
                # First class is "star-rating"; the rating word is the second.
                remaining = [c for c in classes if c != "star-rating"]
                if remaining:
                    rating = remaining[0]

            records.append(
                {
                    "title": title,
                    "price": price,
                    "availability": availability,
                    "rating": rating,
                }
            )

        return records


class PriceScraper:
    """Scraper for the public, keyless Coinbase spot price API.

    Each configured URL returns one JSON spot payload
    (``{"data":{"amount","base","currency"}}``) which becomes one factual,
    non-PII record ``{"pair","price","currency"}``. Genuinely moving data, so
    the live SSE stream visibly ticks in the demo.
    """

    source = "api.coinbase.com"
    FIELDS = ("pair", "price", "currency")

    def __init__(self, urls: Optional[List[str]] = None) -> None:
        """Store the spot URLs to fetch (defaults to BTC-EUR and ETH-EUR)."""
        self._urls = urls if urls is not None else [
            "https://api.coinbase.com/v2/prices/BTC-EUR/spot",
            "https://api.coinbase.com/v2/prices/ETH-EUR/spot",
        ]

    def urls(self) -> List[str]:
        """Return the configured list of spot URLs."""
        return list(self._urls)

    def scrape(self, html: str) -> List[Dict[str, Any]]:
        """Parse one Coinbase spot JSON payload into a price record.

        Returns an empty list if the payload lacks a usable ``base``.
        """
        data = json.loads(html).get("data", {}) or {}
        base = data.get("base", "")
        currency = data.get("currency", "")
        amount = data.get("amount", "")
        if not base:
            return []
        return [{"pair": "%s-%s" % (base, currency), "price": amount,
                 "currency": currency}]
