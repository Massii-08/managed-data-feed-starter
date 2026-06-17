"""Tests for the SSE event generator (offline, fully synchronous driver)."""
from __future__ import annotations

import asyncio

from feedsmith.store import SnapshotStore
from feedsmith.stream import sse_events


def _drain(agen) -> list:
    """Collect all chunks from a bounded async generator, offline."""
    out = []

    async def run() -> None:
        async for chunk in agen:
            out.append(chunk)

    asyncio.run(run())
    return out


async def _noop_sleep(_seconds: float) -> None:
    return None


def test_emits_update_for_existing_snapshot_first() -> None:
    store = SnapshotStore()
    store.update("books-demo", [{"title": "A"}], "2026-06-16T10:00:00Z")
    chunks = _drain(sse_events(
        store, "books-demo", stale_fn=lambda fid: False,
        poll_seconds=1.0, ping_every=15.0, sleep=_noop_sleep,
        max_iterations=1,
    ))
    assert len(chunks) == 1
    assert chunks[0].startswith("event: update\n")
    assert '"title": "A"' in chunks[0]
    assert chunks[0].endswith("\n\n")


def test_emits_ping_when_idle_then_update_on_version_bump() -> None:
    store = SnapshotStore()
    store.update("books-demo", [{"title": "A"}], "t1")

    # Iter 0: initial update (version 1). Iters 1..15: idle -> one ping at 15.
    # We bump the version on iteration 16 by mutating between drains is hard;
    # instead drive a small ping_every and bump mid-stream via a wrapper.
    events = []

    async def run() -> None:
        agen = sse_events(
            store, "books-demo", stale_fn=lambda fid: False,
            poll_seconds=1.0, ping_every=2.0, sleep=_noop_sleep,
            max_iterations=6,
        )
        i = 0
        async for chunk in agen:
            events.append(chunk)
            i += 1
            if i == 3:  # bump the snapshot mid-stream
                store.update("books-demo", [{"title": "B"}], "t2")

    asyncio.run(run())
    kinds = [c.split("\n", 1)[0] for c in events]
    assert kinds[0] == "event: update"      # initial snapshot
    assert any(e.startswith(": ping") for e in events)   # at least one keepalive while idle
    assert any(c.startswith("event: update") and '"title": "B"' in c
               for c in events)              # update after the bump
