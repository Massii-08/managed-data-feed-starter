"""Tests for FeedConfig fields relevant to the live-feed POC."""
from __future__ import annotations

from feedsmith.config import FeedConfig


def _base() -> dict:
    return {
        "id": "x",
        "source": "src",
        "fields": ["a"],
        "schedule": {"interval_seconds": 30},
        "output": {"kind": "csv", "path": "data/x.csv"},
    }


def test_scraper_defaults_to_bookstore() -> None:
    config = FeedConfig.model_validate(_base())
    assert config.scraper == "bookstore"


def test_scraper_accepts_price() -> None:
    data = _base()
    data["scraper"] = "price"
    config = FeedConfig.model_validate(data)
    assert config.scraper == "price"


def test_fetcher_defaults_to_httpx() -> None:
    config = FeedConfig.model_validate(_base())
    assert config.fetcher == "httpx"
    assert config.warm_url is None


def test_fetcher_accepts_stealth_with_warm_url() -> None:
    data = _base()
    data["fetcher"] = "stealth"
    data["warm_url"] = "https://target.example/"
    config = FeedConfig.model_validate(data)
    assert config.fetcher == "stealth"
    assert config.warm_url == "https://target.example/"
