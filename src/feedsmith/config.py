"""Feed configuration models and loader for Feedsmith.

Defines the pydantic v2 models that describe a managed data feed: its public
source, the allowed factual / non-PII fields, the rate limit, the schedule, and
the delivery output. ``load_feed_config`` reads a YAML file and validates it
into a :class:`FeedConfig`.
"""
from __future__ import annotations

from typing import List, Optional

import yaml
from pydantic import BaseModel, model_validator
from typing_extensions import Literal


class OutputConfig(BaseModel):
    """Delivery configuration for a feed.

    Attributes:
        kind: One of ``"csv"``, ``"json"`` or ``"webhook"``.
        path: Filesystem path for ``csv`` / ``json`` sinks.
        url: Target URL for the ``webhook`` sink.
    """

    kind: Literal["csv", "json", "webhook"]
    path: Optional[str] = None
    url: Optional[str] = None


class ScheduleConfig(BaseModel):
    """Schedule configuration for a feed.

    Exactly one of ``interval_seconds`` or ``cron`` must be provided.
    """

    interval_seconds: Optional[int] = None
    cron: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_schedule(self) -> "ScheduleConfig":
        """Ensure exactly one of interval_seconds / cron is set."""
        has_interval = self.interval_seconds is not None
        has_cron = self.cron is not None
        if has_interval == has_cron:
            raise ValueError(
                "exactly one of 'interval_seconds' or 'cron' must be set"
            )
        return self


class FeedConfig(BaseModel):
    """Full configuration for a single managed data feed.

    Attributes:
        id: Stable feed identifier (used as the scheduler job id).
        source: Human-readable identifier of the public source.
        fields: Allowed factual / non-PII field names to keep.
        rate_limit_seconds: Minimum seconds between successive fetches.
        urls: Optional explicit list of URLs to scrape.
        schedule: When the feed runs.
        output: Where clean records are delivered.
    """

    id: str
    source: str
    fields: List[str]
    rate_limit_seconds: float = 1.0
    urls: Optional[List[str]] = None
    schedule: ScheduleConfig
    output: OutputConfig


def load_feed_config(path: str) -> FeedConfig:
    """Load and validate a feed configuration from a YAML file.

    Args:
        path: Path to a YAML file describing a single feed.

    Returns:
        The validated :class:`FeedConfig`.
    """
    with open(path) as handle:
        data = yaml.safe_load(handle)
    return FeedConfig.model_validate(data)
