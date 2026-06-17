"""Server-Sent Events generator for live feed updates.

``sse_events`` polls the :class:`~feedsmith.store.SnapshotStore` version for a
feed and yields an ``update`` event whenever it changes, a ``: ping`` comment
when idle (keepalive through proxies / Cloudflare), in plain ``text/event-stream``
wire format. The clock (``sleep``) and ``max_iterations`` are injectable so the
generator is fully testable offline without a running event loop timer.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional

from feedsmith.store import SnapshotStore, build_data_payload


def _format_event(event: str, data: Dict[str, Any]) -> str:
    """Format one named SSE event with a JSON data line."""
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data))


async def sse_events(
    store: SnapshotStore,
    feed_id: str,
    *,
    stale_fn: Callable[[str], bool] = lambda _fid: False,
    poll_seconds: float = 1.0,
    ping_every: float = 15.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_iterations: Optional[int] = None,
) -> AsyncIterator[str]:
    """Yield SSE chunks: an ``update`` on every version change, else pings."""
    last_version = -1
    idle_elapsed = 0.0
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        version = store.version(feed_id)
        if version != last_version:
            last_version = version
            payload = build_data_payload(
                feed_id, store.latest(feed_id), stale_fn(feed_id)
            )
            yield _format_event("update", payload)
            idle_elapsed = 0.0
        else:
            idle_elapsed += poll_seconds
            if idle_elapsed >= ping_every:
                yield ": ping\n\n"  # SSE comment keepalive (flush)
                idle_elapsed = 0.0
        iterations += 1
        await sleep(poll_seconds)
