"""Tests for the Feedsmith FastAPI control plane.

Self-contained: a local fake runner returns a canned ``RunResult`` so no
network or real scraping happens. The registry is injected directly into
``create_app`` to avoid loading any YAML config from disk.
"""
from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from feedsmith.api import FeedHandle, create_app
from feedsmith.config import FeedConfig
from feedsmith.monitor import FeedHealth
from feedsmith.runner import RunResult


class FakeRunner:
    """Stand-in for :class:`FeedRunner` that returns a fixed result offline."""

    def __init__(self, result: RunResult) -> None:
        self._result = result
        self.calls = 0

    def run_once(self) -> RunResult:
        """Record the call and return the canned result (no network)."""
        self.calls += 1
        return self._result


def _make_config() -> FeedConfig:
    """Build a small, valid in-test feed configuration."""
    return FeedConfig.model_validate(
        {
            "id": "books-demo",
            "source": "books.toscrape.com",
            "fields": ["title", "price", "availability", "rating"],
            "schedule": {"interval_seconds": 60},
            "output": {"kind": "csv", "path": "data/x.csv"},
        }
    )


def _make_client(result: Optional[RunResult] = None) -> TestClient:
    """Create a TestClient backed by a one-feed fake registry."""
    if result is None:
        result = RunResult(
            feed_id="books-demo",
            ok=True,
            record_count=3,
            output="data/x.csv",
            error=None,
        )
    config = _make_config()
    health = FeedHealth(feed_id="books-demo")
    health.record_success("2026-06-10T00:00:00+00:00")
    handle = FeedHandle(config=config, runner=FakeRunner(result), health=health)
    app = create_app({"books-demo": handle})
    return TestClient(app)


def test_health_endpoint() -> None:
    """GET /health returns the service liveness body."""
    client = _make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "feedsmith"}


def test_list_feeds() -> None:
    """GET /feeds lists the single registered feed with its status."""
    client = _make_client()
    resp = client.get("/feeds")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["id"] == "books-demo"
    assert entry["source"] == "books.toscrape.com"
    assert entry["status"] == "healthy"


def test_feed_status_ok() -> None:
    """GET /feeds/{id}/status returns the detailed health record."""
    client = _make_client()
    resp = client.get("/feeds/books-demo/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["feed_id"] == "books-demo"
    assert body["status"] == "healthy"
    assert body["last_success_at"] == "2026-06-10T00:00:00+00:00"
    assert body["consecutive_failures"] == 0
    assert body["total_runs"] == 1


def test_feed_status_unknown_404() -> None:
    """GET /feeds/{id}/status returns 404 for an unknown feed."""
    client = _make_client()
    resp = client.get("/feeds/nope/status")
    assert resp.status_code == 404


def test_run_feed_ok() -> None:
    """POST /feeds/{id}/run returns the RunResult dict (no network)."""
    result = RunResult(
        feed_id="books-demo",
        ok=True,
        record_count=7,
        output="data/x.csv",
        error=None,
    )
    client = _make_client(result)
    resp = client.post("/feeds/books-demo/run")
    assert resp.status_code == 200
    assert resp.json() == {
        "feed_id": "books-demo",
        "ok": True,
        "record_count": 7,
        "output": "data/x.csv",
        "error": None,
    }


def test_run_feed_unknown_404() -> None:
    """POST /feeds/{id}/run returns 404 for an unknown feed."""
    client = _make_client()
    resp = client.post("/feeds/nope/run")
    assert resp.status_code == 404
