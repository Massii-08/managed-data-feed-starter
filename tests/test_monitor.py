"""Offline tests for FeedHealth transitions and Monitor self-heal."""
from __future__ import annotations

from typing import List

from feedsmith.monitor import FeedHealth, Monitor


def test_record_success_resets_streak() -> None:
    """A success bumps total_runs and clears the failure streak."""
    health = FeedHealth("f1")
    health.record_failure("2026-01-01T00:00:00+00:00", "boom")
    health.record_success("2026-01-01T00:01:00+00:00")

    assert health.total_runs == 2
    assert health.total_failures == 1
    assert health.consecutive_failures == 0
    assert health.last_success_at == "2026-01-01T00:01:00+00:00"
    assert health.last_error is None


def test_record_failure_accumulates() -> None:
    """Failures accumulate totals and extend the consecutive streak."""
    health = FeedHealth("f1")
    health.record_failure("2026-01-01T00:00:00+00:00", "e1")
    health.record_failure("2026-01-01T00:01:00+00:00", "e2")

    assert health.total_runs == 2
    assert health.total_failures == 2
    assert health.consecutive_failures == 2
    assert health.last_error == "e2"


def test_status_thresholds() -> None:
    """Status: 0 -> healthy, 1..2 -> degraded, >=3 -> down."""
    health = FeedHealth("f1")
    assert health.status == "healthy"

    health.record_failure("2026-01-01T00:00:00+00:00", "e1")
    assert health.consecutive_failures == 1
    assert health.status == "degraded"

    health.record_failure("2026-01-01T00:01:00+00:00", "e2")
    assert health.consecutive_failures == 2
    assert health.status == "degraded"

    health.record_failure("2026-01-01T00:02:00+00:00", "e3")
    assert health.consecutive_failures == 3
    assert health.status == "down"


def test_as_dict_includes_status() -> None:
    """as_dict exposes every field plus the derived status."""
    health = FeedHealth("feed-x")
    health.record_success("2026-01-01T00:00:00+00:00")
    data = health.as_dict()

    assert data["feed_id"] == "feed-x"
    assert data["status"] == "healthy"
    assert data["last_success_at"] == "2026-01-01T00:00:00+00:00"
    assert data["last_error"] is None
    assert data["consecutive_failures"] == 0
    assert data["total_runs"] == 1
    assert data["total_failures"] == 0


def test_monitor_fires_alert_and_heal_once_at_edge() -> None:
    """Monitor fires alert+heal exactly once when streak hits threshold."""
    alerts: List[str] = []
    heals: List[str] = []
    monitor = Monitor(
        alert=lambda m: alerts.append(m),
        heal=lambda fid: heals.append(fid),
        heal_threshold=3,
    )
    health = FeedHealth("feed-y")

    # Failure 1 -> below threshold, nothing fires.
    health.record_failure("2026-01-01T00:00:00+00:00", "e1")
    monitor.observe(health)
    assert alerts == []
    assert heals == []

    # Failure 2 -> still below threshold.
    health.record_failure("2026-01-01T00:01:00+00:00", "e2")
    monitor.observe(health)
    assert alerts == []
    assert heals == []

    # Failure 3 -> exact edge, fires once.
    health.record_failure("2026-01-01T00:02:00+00:00", "e3")
    monitor.observe(health)
    assert len(alerts) == 1
    assert heals == ["feed-y"]
    assert "feed-y" in alerts[0]

    # Failure 4 -> past the edge, does NOT fire again.
    health.record_failure("2026-01-01T00:03:00+00:00", "e4")
    monitor.observe(health)
    assert len(alerts) == 1
    assert heals == ["feed-y"]


def test_monitor_default_no_heal() -> None:
    """Monitor with no heal callback still fires the alert at the edge."""
    alerts: List[str] = []
    monitor = Monitor(alert=lambda m: alerts.append(m), heal=None, heal_threshold=2)
    health = FeedHealth("feed-z")

    health.record_failure("2026-01-01T00:00:00+00:00", "e1")
    monitor.observe(health)
    assert alerts == []

    health.record_failure("2026-01-01T00:01:00+00:00", "e2")
    monitor.observe(health)
    assert len(alerts) == 1


def test_monitor_observe_on_success_does_nothing() -> None:
    """Observing a healthy feed (0 failures) never fires."""
    alerts: List[str] = []
    heals: List[str] = []
    monitor = Monitor(
        alert=lambda m: alerts.append(m),
        heal=lambda fid: heals.append(fid),
        heal_threshold=3,
    )
    health = FeedHealth("feed-ok")
    health.record_success("2026-01-01T00:00:00+00:00")
    monitor.observe(health)

    assert alerts == []
    assert heals == []
