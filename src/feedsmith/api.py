"""FastAPI control plane for Feedsmith.

Exposes a small HTTP API to inspect feed health and trigger runs on demand.
The default application loads the bundled ``feeds/books_demo.yaml`` feed (a
public e-commerce scraping sandbox, factual / non-PII data only) into a single
in-memory registry; tests inject their own registry instead.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from feedsmith.config import FeedConfig, load_feed_config
from feedsmith.monitor import FeedHealth
from feedsmith.runner import FeedRunner, build_runner
from feedsmith.scheduler import FeedScheduler
from feedsmith.store import SnapshotStore, build_data_payload
from feedsmith.stream import sse_events

# Absolute path to the repository root (two levels up from this file:
# src/feedsmith/api.py -> repo root).
REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@dataclass
class FeedHandle:
    """In-memory binding of a feed's config, runner and health state."""

    config: FeedConfig
    runner: FeedRunner
    health: FeedHealth


def _default_registry(store: SnapshotStore) -> Dict[str, FeedHandle]:
    """Build the default registry from every YAML feed under ``feeds/``.

    Each feed is teed to the shared ``store`` so the live API can serve it.
    Never raises: a missing/invalid file is skipped so import can't crash.
    """
    import glob

    registry: Dict[str, FeedHandle] = {}
    pattern = os.path.join(REPO_ROOT, "feeds", "*.yaml")
    for config_path in sorted(glob.glob(pattern)):
        try:
            config = load_feed_config(config_path)
            runner, health = build_runner(config, store=store)
            registry[config.id] = FeedHandle(
                config=config, runner=runner, health=health
            )
        except Exception:
            continue
    return registry


def register_feeds(
    scheduler: FeedScheduler, registry: Dict[str, FeedHandle]
) -> None:
    """Register each feed's runner with the scheduler on its configured schedule.

    Reads ``interval_seconds`` / ``cron`` from each feed's ``ScheduleConfig``
    (exactly one is set, enforced by the config model) so the served app keeps
    every feed continuously fresh.
    """
    for feed_id, handle in registry.items():
        sched = handle.config.schedule
        scheduler.add_feed(
            feed_id,
            handle.runner,
            interval_seconds=sched.interval_seconds,
            cron=sched.cron,
        )


def create_app(
    registry: Optional[Dict[str, FeedHandle]] = None,
    store: Optional[SnapshotStore] = None,
    *,
    start_scheduler: bool = False,
    scheduler: Optional[FeedScheduler] = None,
) -> FastAPI:
    """Create the Feedsmith FastAPI application.

    Args:
        registry: Optional mapping of feed id to :class:`FeedHandle`. When
            ``None``, every ``feeds/*.yaml`` is loaded (failures swallowed).
        store: Optional shared :class:`SnapshotStore` the live endpoints read.
            When ``None``, a fresh store is created and wired to the default
            registry.
        start_scheduler: When True, a lifespan hook registers every feed on its
            schedule and starts the scheduler so the served app refreshes feeds
            continuously (and shuts it down on teardown). Off in tests so the
            suite stays offline.
        scheduler: Optional :class:`FeedScheduler` to use when
            ``start_scheduler`` is True (a default one is built otherwise).
            Injectable so tests can assert scheduling without real timers.

    Returns:
        The configured FastAPI application.
    """
    if store is None:
        store = SnapshotStore()
    if registry is None:
        registry = _default_registry(store)

    lifespan = None
    if start_scheduler:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def lifespan(_app: FastAPI):  # noqa: F811 - conditional lifespan
            sch = scheduler if scheduler is not None else FeedScheduler()
            register_feeds(sch, registry)
            sch.start()
            _app.state.feed_scheduler = sch
            try:
                yield
            finally:
                sch.shutdown()

    app = FastAPI(title="Feedsmith", version="0.1.0", lifespan=lifespan)

    origins_env = os.environ.get("FEEDSMITH_CORS_ORIGINS", "*")
    origins = [o.strip() for o in origins_env.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        """Liveness probe for the service itself."""
        return {"status": "ok", "service": "feedsmith"}

    @app.get("/feeds")
    def list_feeds() -> List[Dict[str, str]]:
        """List the registered feeds with their current health status."""
        return [
            {
                "id": feed_id,
                "source": handle.config.source,
                "status": handle.health.status,
            }
            for feed_id, handle in registry.items()
        ]

    @app.get("/feeds/{feed_id}/status")
    def feed_status(feed_id: str) -> Dict[str, object]:
        """Return the detailed health record for a feed (404 if unknown)."""
        handle = registry.get(feed_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="feed not found")
        return handle.health.as_dict()

    @app.post("/feeds/{feed_id}/run")
    def run_feed(feed_id: str) -> Dict[str, object]:
        """Trigger a single run of a feed and return its result (404 if unknown)."""
        handle = registry.get(feed_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="feed not found")
        return dataclasses.asdict(handle.runner.run_once())

    @app.get("/feeds/{feed_id}/data")
    def feed_data(feed_id: str) -> Dict[str, object]:
        """Return the latest clean records for a feed (404 if unknown)."""
        handle = registry.get(feed_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="feed not found")
        stale = handle.health.consecutive_failures > 0
        return build_data_payload(feed_id, store.latest(feed_id), stale)

    @app.get("/feeds/{feed_id}/stream")
    def feed_stream(feed_id: str) -> StreamingResponse:
        """Stream live feed updates as Server-Sent Events (404 if unknown)."""
        handle = registry.get(feed_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="feed not found")

        def _stale(fid: str) -> bool:
            h = registry.get(fid)
            return bool(h and h.health.consecutive_failures > 0)

        return StreamingResponse(
            sse_events(store, feed_id, stale_fn=_stale),
            media_type="text/event-stream",
        )

    @app.get("/widget.js")
    def widget_js() -> FileResponse:
        """Serve the embeddable live-feed widget as JavaScript."""
        return FileResponse(
            os.path.join(STATIC_DIR, "widget.js"),
            media_type="application/javascript",
        )

    return app


# The served application starts the scheduler so feeds refresh continuously.
# (Tests build their own apps via create_app() with start_scheduler=False.)
app = create_app(start_scheduler=True)
