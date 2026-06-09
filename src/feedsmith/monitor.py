"""Feed health tracking, alerting, and self-heal triggering.

:class:`FeedHealth` records run outcomes and exposes a derived status.
:class:`Monitor` watches a health object and fires an alert (and optional
heal) exactly once when consecutive failures cross the heal threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class FeedHealth:
    """Mutable health state for a single feed."""

    feed_id: str
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    total_runs: int = 0
    total_failures: int = 0

    def record_success(self, when_iso: str) -> None:
        """Record a successful run and reset the failure streak."""
        self.total_runs += 1
        self.consecutive_failures = 0
        self.last_success_at = when_iso
        self.last_error = None

    def record_failure(self, when_iso: str, err: str) -> None:
        """Record a failed run and extend the failure streak."""
        self.total_runs += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_error = err

    @property
    def status(self) -> str:
        """Derive a human status from the consecutive failure count."""
        if self.consecutive_failures == 0:
            return "healthy"
        if self.consecutive_failures < 3:
            return "degraded"
        return "down"

    def as_dict(self) -> Dict[str, Any]:
        """Return all health fields plus the derived status."""
        return {
            "feed_id": self.feed_id,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "total_runs": self.total_runs,
            "total_failures": self.total_failures,
            "status": self.status,
        }


class Monitor:
    """Observe a feed's health and trigger alerts / self-heal."""

    def __init__(
        self,
        alert: Callable[[str], None] = lambda m: None,
        heal: Optional[Callable[[str], None]] = None,
        heal_threshold: int = 3,
    ) -> None:
        """Store the alert/heal callbacks and the heal threshold."""
        self.alert = alert
        self.heal = heal
        self.heal_threshold = heal_threshold

    def observe(self, health: FeedHealth) -> None:
        """Fire alert (and heal) once when the threshold is exactly hit.

        Using ``==`` (the exact edge) guarantees the alert fires a single
        time per crossing rather than on every failure beyond the threshold.
        """
        if health.consecutive_failures == self.heal_threshold:
            message = (
                "Feed '%s' is down: %d consecutive failures (last error: %s)"
                % (
                    health.feed_id,
                    health.consecutive_failures,
                    health.last_error,
                )
            )
            self.alert(message)
            if self.heal is not None:
                self.heal(health.feed_id)
