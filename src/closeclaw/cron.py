"""Simple minute-level cron ticker."""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Awaitable, Callable

from loguru import logger

CronCallback = Callable[[], Awaitable[None]]


class CronJob:
    """A single cron job scheduled at a specific local time."""

    def __init__(
        self, name: str, hour: int, minute: int, callback: CronCallback
    ) -> None:
        self.name = name
        self.hour = hour
        self.minute = minute
        self.callback = callback


async def run_cron_tasks(
    jobs: list[CronJob],
    *,
    _now_factory: Callable[[], datetime.datetime] = datetime.datetime.now,
) -> None:
    """Run cron jobs with minute-level precision."""
    triggered_today: set[str] = set()

    while True:
        now = _now_factory().astimezone()

        # Reset trigger state at midnight
        if now.hour == 0 and now.minute == 0:
            triggered_today.clear()

        for job in jobs:
            key = f"{job.name}:{now.date().isoformat()}"
            if (
                now.hour == job.hour
                and now.minute >= job.minute
                and key not in triggered_today
            ):
                triggered_today.add(key)
                try:
                    await job.callback()
                except Exception:
                    logger.exception("Cron job {job} failed", job=job.name)

        # Sleep until the start of the next minute
        next_minute = (now + datetime.timedelta(minutes=1)).replace(
            second=0, microsecond=0
        )
        await asyncio.sleep((next_minute - now).total_seconds())
