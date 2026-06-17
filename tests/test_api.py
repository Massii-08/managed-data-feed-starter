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


def _make_client_with_store(store, consecutive_failures: int = 0):
    """Client whose registry shares ``store`` and a controllable health."""
    config = _make_config()
    health = FeedHealth(feed_id="books-demo")
    health.record_success("2026-06-16T10:00:00+00:00")
    health.consecutive_failures = consecutive_failures
    result = RunResult(feed_id="books-demo", ok=True, record_count=0,
                       output="x", error=None)
    handle = FeedHandle(config=config, runner=FakeRunner(result), health=health)
    app = create_app({"books-demo": handle}, store=store)
    return TestClient(app)


def test_data_empty_when_no_snapshot() -> None:
    from feedsmith.store import SnapshotStore

    client = _make_client_with_store(SnapshotStore())
    resp = client.get("/feeds/books-demo/data")
    assert resp.status_code == 200
    assert resp.json() == {
        "feed_id": "books-demo", "fetched_at": None, "count": 0,
        "stale": True, "records": [],
    }


def test_data_returns_latest_snapshot() -> None:
    from feedsmith.store import SnapshotStore

    store = SnapshotStore()
    store.update("books-demo",
                 [{"title": "A", "source": "books.toscrape.com",
                   "fetched_at": "2026-06-16T10:00:00Z"}],
                 "2026-06-16T10:00:00Z")
    client = _make_client_with_store(store)
    body = client.get("/feeds/books-demo/data").json()
    assert body["count"] == 1
    assert body["stale"] is False
    assert body["fetched_at"] == "2026-06-16T10:00:00Z"
    assert body["records"][0]["title"] == "A"


def test_data_is_stale_when_feed_is_failing() -> None:
    from feedsmith.store import SnapshotStore

    store = SnapshotStore()
    store.update("books-demo", [{"title": "A"}], "2026-06-16T10:00:00Z")
    client = _make_client_with_store(store, consecutive_failures=2)
    body = client.get("/feeds/books-demo/data").json()
    assert body["stale"] is True
    assert body["count"] == 1


def test_data_unknown_feed_404() -> None:
    from feedsmith.store import SnapshotStore

    client = _make_client_with_store(SnapshotStore())
    assert client.get("/feeds/nope/data").status_code == 404


def test_stream_endpoint_streams_event_stream_content_type(monkeypatch) -> None:
    """GET /stream returns text/event-stream with an initial update event.

    The live generator is infinite, so we monkeypatch it with a bounded (1-iter)
    version to avoid blocking the TestClient's ASGI transport (HTTPX never sends
    http.disconnect while more_body is pending, so an unpatched infinite generator
    would hang forever in the test process).
    """
    import feedsmith.api as api_mod
    from feedsmith.store import SnapshotStore

    async def _bounded_sse(store, feed_id, *, stale_fn, **_kw):
        from feedsmith.stream import _format_event
        from feedsmith.store import build_data_payload
        payload = build_data_payload(feed_id, store.latest(feed_id), stale_fn(feed_id))
        yield _format_event("update", payload)

    monkeypatch.setattr(api_mod, "sse_events", _bounded_sse)

    store = SnapshotStore()
    store.update("books-demo", [{"title": "A"}], "2026-06-16T10:00:00Z")
    client = _make_client_with_store(store)
    # stream=True so the TestClient does not block on the (now bounded) generator.
    with client.stream("GET", "/feeds/books-demo/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # Anti-buffering headers so CDNs/proxies stream events promptly.
        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("x-accel-buffering") == "no"
        first = next(resp.iter_lines())
        assert first == "event: update"


def test_stream_unknown_feed_404() -> None:
    from feedsmith.store import SnapshotStore

    client = _make_client_with_store(SnapshotStore())
    resp = client.get("/feeds/nope/stream")
    assert resp.status_code == 404


def test_widget_js_is_served_as_javascript() -> None:
    from feedsmith.store import SnapshotStore

    client = _make_client_with_store(SnapshotStore())
    resp = client.get("/widget.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "EventSource" in resp.text  # the widget subscribes to the SSE stream


def test_cors_allows_cross_origin_get() -> None:
    from feedsmith.store import SnapshotStore

    client = _make_client_with_store(SnapshotStore())
    resp = client.get(
        "/feeds/books-demo/data",
        headers={"Origin": "https://feedsmith-demo.pages.dev"},
    )
    assert resp.headers.get("access-control-allow-origin") in (
        "*", "https://feedsmith-demo.pages.dev",
    )


def test_default_app_exposes_both_demo_feeds() -> None:
    app = create_app()
    client = TestClient(app)
    ids = {entry["id"] for entry in client.get("/feeds").json()}
    assert {"books-demo", "prices-demo"} <= ids


class _FakeAps:
    """Minimal APScheduler stand-in capturing jobs and start/shutdown."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self._jobs: list = []

    def add_job(self, fn, trigger, id):  # noqa: A002 - APScheduler uses `id`
        self._jobs.append(type("J", (), {"id": id})())

    def get_jobs(self):
        return list(self._jobs)

    def start(self):
        self.started = True

    def shutdown(self):
        self.stopped = True


def _one_feed_registry():
    """A one-feed registry (books-demo, interval schedule) for scheduler tests."""
    from feedsmith.api import FeedHandle

    cfg = _make_config()  # schedule.interval_seconds == 60
    health = FeedHealth(feed_id="books-demo")
    result = RunResult(feed_id="books-demo", ok=True, record_count=0,
                       output="x", error=None)
    return {"books-demo": FeedHandle(config=cfg, runner=FakeRunner(result),
                                     health=health)}


def test_register_feeds_adds_one_job_per_feed_with_schedule() -> None:
    from feedsmith.api import register_feeds
    from feedsmith.scheduler import FeedScheduler

    fs = FeedScheduler(_FakeAps())
    register_feeds(fs, _one_feed_registry())
    assert fs.job_ids == ["books-demo"]


def test_startup_starts_scheduler_and_registers_feeds() -> None:
    from feedsmith.scheduler import FeedScheduler
    from feedsmith.store import SnapshotStore

    fake = _FakeAps()
    fs = FeedScheduler(fake)
    app = create_app(_one_feed_registry(), store=SnapshotStore(),
                     start_scheduler=True, scheduler=fs)
    with TestClient(app):  # entering the context triggers the lifespan startup
        pass
    assert fake.started is True
    assert fake.stopped is True
    assert "books-demo" in fs.job_ids


def test_no_scheduler_started_by_default() -> None:
    from feedsmith.scheduler import FeedScheduler
    from feedsmith.store import SnapshotStore

    fake = _FakeAps()
    fs = FeedScheduler(fake)
    # start_scheduler defaults False -> lifespan must not touch the scheduler.
    app = create_app(_one_feed_registry(), store=SnapshotStore(), scheduler=fs)
    with TestClient(app):
        pass
    assert fake.started is False
    assert fs.job_ids == []
