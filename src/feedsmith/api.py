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

from feedsmith.config import FeedConfig, load_feed_config
from feedsmith.monitor import FeedHealth
from feedsmith.runner import FeedRunner, build_runner

# Absolute path to the repository root (two levels up from this file:
# src/feedsmith/api.py -> repo root).
REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


@dataclass
class FeedHandle:
    """In-memory binding of a feed's config, runner and health state."""

    config: FeedConfig
    runner: FeedRunner
    health: FeedHealth


def _default_registry() -> Dict[str, FeedHandle]:
    """Build the default registry from the bundled demo feed.

    Never raises: if the demo config is missing or invalid, an empty registry
    is returned so importing the module can never crash.
    """
    registry: Dict[str, FeedHandle] = {}
    try:
        config_path = os.path.join(REPO_ROOT, "feeds", "books_demo.yaml")
        config = load_feed_config(config_path)
        runner, health = build_runner(config)
        registry[config.id] = FeedHandle(config=config, runner=runner, health=health)
    except Exception:
        return {}
    return registry


def create_app(registry: Optional[Dict[str, FeedHandle]] = None) -> FastAPI:
    """Create the Feedsmith FastAPI application.

    Args:
        registry: Optional mapping of feed id to :class:`FeedHandle`. When
            ``None``, the bundled demo feed is loaded (failures are swallowed,
            yielding an empty registry).

    Returns:
        The configured FastAPI application.
    """
    if registry is None:
        registry = _default_registry()

    app = FastAPI(title="Feedsmith", version="0.1.0")

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

    return app


app = create_app()
