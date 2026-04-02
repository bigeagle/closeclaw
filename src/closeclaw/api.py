"""Gateway – FastAPI service that owns the Telegram bot and heartbeat ticker."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Body, FastAPI
from loguru import logger
from telegram import Update

from closeclaw.config import Settings


def create_gateway(settings: Settings) -> FastAPI:
    """Build the main FastAPI application.

    The returned app manages the Telegram bot and heartbeat ticker via
    its *lifespan* context manager, and exposes control endpoints (e.g.
    ``POST /heartbeat``).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from closeclaw.channels.telegram import (
            _get_session,
            _run_heartbeat,
            build_telegram_app,
        )

        # ── Startup ──────────────────────────────────────────────────
        tg_app = build_telegram_app(settings)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot started")

        app.state.telegram_app = tg_app
        app.state.bot = tg_app.bot
        app.state.settings = settings

        # Pre-warm main session
        if settings.main_session_chat_id:
            logger.info(
                "Pre-warming main session for chat {cid}",
                cid=settings.main_session_chat_id,
            )
            _get_session(settings.main_session_chat_id, settings)

        # Heartbeat ticker
        heartbeat_task: asyncio.Task | None = None
        if (
            settings.heartbeat.enabled
            and settings.heartbeat.interval > 0
            and settings.main_session_chat_id
        ):

            async def _heartbeat_ticker() -> None:
                while True:
                    await asyncio.sleep(settings.heartbeat.interval)
                    try:
                        await _run_heartbeat(tg_app.bot, settings)
                    except Exception as exc:
                        logger.error("Heartbeat failed: {e}", e=exc)

            heartbeat_task = asyncio.create_task(_heartbeat_ticker())
            logger.info(
                "Heartbeat ticker started (interval={i}s)",
                i=settings.heartbeat.interval,
            )

        # Cron ticker (date-change tick at 00:00 local time)
        cron_task: asyncio.Task | None = None
        if settings.main_session_chat_id:
            from closeclaw.cron import CronJob, run_cron_tasks
            from closeclaw.channels.telegram import _insert_date_tick

            async def _cron_runner() -> None:
                jobs = [
                    CronJob(
                        name="daily-date-tick",
                        hour=0,
                        minute=0,
                        callback=lambda: _insert_date_tick(settings),
                    ),
                ]
                await run_cron_tasks(jobs)

            cron_task = asyncio.create_task(_cron_runner())
            logger.info("Cron ticker started")

        yield

        # ── Shutdown ─────────────────────────────────────────────────
        if heartbeat_task:
            heartbeat_task.cancel()
        if cron_task:
            cron_task.cancel()
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        logger.info("Telegram bot stopped")

    app = FastAPI(title="closeclaw", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.post("/heartbeat")
    async def trigger_heartbeat(
        prompt: str = Body(default="", embed=True),
    ) -> dict[str, str]:
        from closeclaw.channels.telegram import _run_heartbeat

        logger.info("API: manual heartbeat trigger")
        asyncio.create_task(
            _run_heartbeat(app.state.bot, settings, prompt_override=prompt)
        )
        return {"status": "triggered"}

    return app


def run_gateway(settings: Settings) -> None:
    """Start the gateway (blocking)."""
    app = create_gateway(settings)
    uvicorn.run(app, host="127.0.0.1", port=settings.api_port, log_level="info")
