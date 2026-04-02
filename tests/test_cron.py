"""Tests for closeclaw.cron."""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, patch

import pytest

from closeclaw.cron import CronJob, run_cron_tasks


LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo


class TestRunCronTasks:
    async def test_runs_job_when_time_matches(self):
        callback = AsyncMock()
        job = CronJob(name="test-job", hour=0, minute=0, callback=callback)

        call_count = 0

        async def controlled_callback():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError("stop loop")

        job.callback = controlled_callback

        base = datetime.datetime(2024, 6, 30, 0, 0, 0, tzinfo=LOCAL_TZ)

        def fake_now():
            return base

        with pytest.raises(asyncio.CancelledError):
            await run_cron_tasks([job], _now_factory=fake_now)

        assert call_count == 1

    async def test_skips_then_triggers(self):
        callback = AsyncMock()
        job = CronJob(name="test-job", hour=12, minute=0, callback=callback)

        base = datetime.datetime(2024, 6, 30, 11, 59, 0, tzinfo=LOCAL_TZ)
        call_idx = 0

        def fake_now():
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return base
            # second call happens after sleep, return 12:00
            if call_idx == 2:
                return base.replace(hour=12, minute=0)
            return base

        loop_idx = 0

        async def short_sleep(_seconds):
            nonlocal loop_idx
            loop_idx += 1
            if loop_idx >= 2:
                raise asyncio.CancelledError("stop loop")

        with patch("closeclaw.cron.asyncio.sleep", new=short_sleep):
            with pytest.raises(asyncio.CancelledError):
                await run_cron_tasks([job], _now_factory=fake_now)

        callback.assert_awaited_once()

    async def test_runs_job_exactly_once_per_day(self):
        callback = AsyncMock()
        job = CronJob(name="test-job", hour=0, minute=0, callback=callback)

        base = datetime.datetime(2024, 6, 30, 0, 0, 0, tzinfo=LOCAL_TZ)
        call_idx = 0

        def fake_now():
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return base
            # Subsequent loops are still the same day after midnight
            return base.replace(minute=call_idx - 1)

        loop_idx = 0

        async def short_sleep(_seconds):
            nonlocal loop_idx
            loop_idx += 1
            if loop_idx >= 3:
                raise asyncio.CancelledError("stop loop")

        with patch("closeclaw.cron.asyncio.sleep", new=short_sleep):
            with pytest.raises(asyncio.CancelledError):
                await run_cron_tasks([job], _now_factory=fake_now)

        callback.assert_awaited_once()
