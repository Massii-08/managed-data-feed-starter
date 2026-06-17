"""Tests for the in-memory SnapshotStore and the shared data payload."""
from __future__ import annotations

from feedsmith.store import Snapshot, SnapshotStore, build_data_payload


def test_version_starts_at_zero_and_latest_is_none() -> None:
    store = SnapshotStore()
    assert store.version("books-demo") == 0
    assert store.latest("books-demo") is None


def test_update_stores_rows_and_bumps_version() -> None:
    store = SnapshotStore()
    snap = store.update(
        "books-demo",
        [{"title": "A", "price": "£1", "fetched_at": "2026-06-16T10:00:00Z"}],
        "2026-06-16T10:00:00Z",
    )
    assert isinstance(snap, Snapshot)
    assert store.version("books-demo") == 1
    latest = store.latest("books-demo")
    assert latest is not None
    assert latest.records == [
        {"title": "A", "price": "£1", "fetched_at": "2026-06-16T10:00:00Z"}
    ]
    assert latest.fetched_at == "2026-06-16T10:00:00Z"


def test_update_is_isolated_per_feed() -> None:
    store = SnapshotStore()
    store.update("books-demo", [{"title": "A"}], "t1")
    store.update("prices-demo", [{"pair": "BTC-EUR"}], "t2")
    assert store.version("books-demo") == 1
    assert store.version("prices-demo") == 1
    assert store.latest("books-demo").records == [{"title": "A"}]
    assert store.latest("prices-demo").records == [{"pair": "BTC-EUR"}]


def test_empty_update_keeps_fetched_at_none() -> None:
    store = SnapshotStore()
    snap = store.update("books-demo", [], None)
    assert snap.records == []
    assert snap.fetched_at is None
    assert store.version("books-demo") == 1


def test_payload_when_no_snapshot_is_stale_and_empty() -> None:
    payload = build_data_payload("books-demo", None, stale=False)
    assert payload == {
        "feed_id": "books-demo",
        "fetched_at": None,
        "count": 0,
        "stale": True,
        "records": [],
    }


def test_payload_with_snapshot_uses_passed_stale() -> None:
    snap = Snapshot(
        feed_id="books-demo",
        fetched_at="2026-06-16T10:00:00Z",
        records=[{"title": "A"}, {"title": "B"}],
        version=4,
    )
    payload = build_data_payload("books-demo", snap, stale=False)
    assert payload == {
        "feed_id": "books-demo",
        "fetched_at": "2026-06-16T10:00:00Z",
        "count": 2,
        "stale": False,
        "records": [{"title": "A"}, {"title": "B"}],
    }
