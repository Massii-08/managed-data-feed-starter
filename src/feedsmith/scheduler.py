"""Scheduling of feed runs via APScheduler (injectable for tests).

:class:`FeedScheduler` wraps a background scheduler and registers feed
runners as interval or cron jobs. The underlying scheduler is injectable
so tests can use a fake and run fully offline.
"""
from __future__ import annotations

from typing import Any, List, Optional

from feedsmith.runner import FeedRunner


class FeedScheduler:
    """Register and control scheduled feed runs."""

    def __init__(self, scheduler: Optional[Any] = None) -> None:
        """Use the injected scheduler or a default BackgroundScheduler."""
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler

            scheduler = BackgroundScheduler()
        self.scheduler = scheduler

    def add_feed(
        self,
        feed_id: str,
        runner: FeedRunner,
        interval_seconds: Optional[int] = None,
        cron: Optional[str] = None,
    ) -> None:
        """Add a job calling ``runner.run_once`` on an interval or cron.

        Exactly one of ``interval_seconds`` or ``cron`` must be provided.
        """
        if interval_seconds is not None and cron is not None:
            raise ValueError("Provide either interval_seconds or cron, not both")
        if interval_seconds is None and cron is None:
            raise ValueError("Provide either interval_seconds or cron")

        if interval_seconds is not None:
            from apscheduler.triggers.interval import IntervalTrigger

            trigger = IntervalTrigger(seconds=interval_seconds)
        else:
            from apscheduler.triggers.cron import CronTrigger

            trigger = CronTrigger.from_crontab(cron)

        self.scheduler.add_job(runner.run_once, trigger, id=feed_id)

    def start(self) -> None:
        """Start the underlying scheduler."""
        self.scheduler.start()

    def shutdown(self) -> None:
        """Shut the underlying scheduler down."""
        self.scheduler.shutdown()

    @property
    def job_ids(self) -> List[str]:
        """Return the ids of all registered jobs."""
        return [job.id for job in self.scheduler.get_jobs()]
