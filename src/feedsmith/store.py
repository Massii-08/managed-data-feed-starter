"""In-memory snapshot store that serves the latest feed records to the API.

The store is the bridge between the scheduled scraping runs (which write the
latest clean records via :class:`~feedsmith.delivery.SnapshotSink`) and the
live HTTP API (``/feeds/{id}/data`` reads it; ``/feeds/{id}/stream`` polls its
version). It is thread-safe because runs execute in a background scheduler
thread while the API serves requests on the event loop.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Snapshot:
    """The latest delivered records for one feed, plus liveness metadata."""

    feed_id: str
    fetched_at: Optional[str]
    records: List[Dict[str, Any]]
    version: int


class SnapshotStore:
    """Hold the latest snapshot per feed id, with a monotonic version."""

    def __init__(self) -> None:
        """Initialise an empty, lock-guarded store."""
        self._lock = threading.Lock()
        self._snapshots: Dict[str, Snapshot] = {}
        self._versions: Dict[str, int] = {}

    def update(
        self,
        feed_id: str,
        rows: List[Dict[str, Any]],
        fetched_at: Optional[str],
    ) -> Snapshot:
        """Replace the snapshot for ``feed_id`` and bump its version."""
        with self._lock:
            version = self._versions.get(feed_id, 0) + 1
            self._versions[feed_id] = version
            snapshot = Snapshot(
                feed_id=feed_id,
                fetched_at=fetched_at,
                records=list(rows),
                version=version,
            )
            self._snapshots[feed_id] = snapshot
            return snapshot

    def latest(self, feed_id: str) -> Optional[Snapshot]:
        """Return the last snapshot for ``feed_id`` (None if never updated)."""
        with self._lock:
            return self._snapshots.get(feed_id)

    def version(self, feed_id: str) -> int:
        """Return the current version for ``feed_id`` (0 if never updated)."""
        with self._lock:
            return self._versions.get(feed_id, 0)


def build_data_payload(
    feed_id: str,
    snapshot: Optional[Snapshot],
    stale: bool,
) -> Dict[str, Any]:
    """Build the JSON envelope returned by ``/data`` and SSE ``update`` events.

    With no snapshot yet, the feed is reported empty and ``stale=True``.
    """
    if snapshot is None:
        return {
            "feed_id": feed_id,
            "fetched_at": None,
            "count": 0,
            "stale": True,
            "records": [],
        }
    return {
        "feed_id": feed_id,
        "fetched_at": snapshot.fetched_at,
        "count": len(snapshot.records),
        "stale": stale,
        "records": snapshot.records,
    }
