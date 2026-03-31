"""Tests for closeclaw.api (FastAPI gateway)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import closeclaw.config as config_mod
from closeclaw.config import Settings


def _gateway_settings(**env: str) -> Settings:
    with (
        patch.dict(os.environ, env, clear=False),
        patch.object(config_mod, "_config_file", None),
    ):
        return Settings(
            _env_file=None,
            kimi_api_key="fake-key",
            telegram_bot_token="fake:token",
        )


def _mock_tg_app() -> MagicMock:
    """Create a mock Telegram Application with async lifecycle methods."""
    tg = MagicMock()
    tg.initialize = AsyncMock()
    tg.start = AsyncMock()
    tg.stop = AsyncMock()
    tg.shutdown = AsyncMock()
    tg.updater.start_polling = AsyncMock()
    tg.updater.stop = AsyncMock()
    tg.bot = MagicMock()
    return tg


def _patched_gateway(settings, mock_tg):
    """Return (app, patches-context) for a gateway with mocked Telegram."""
    return (
        patch(
            "closeclaw.channels.telegram.build_telegram_app",
            return_value=mock_tg,
        ),
        patch("closeclaw.channels.telegram._get_session"),
    )


class TestGateway:
    def test_heartbeat_endpoint(self):
        from fastapi.testclient import TestClient

        from closeclaw.api import create_gateway

        settings = _gateway_settings()
        mock_tg = _mock_tg_app()
        p1, p2 = _patched_gateway(settings, mock_tg)

        with p1, p2:
            app = create_gateway(settings)
            with TestClient(app) as client:
                resp = client.post("/heartbeat")
                assert resp.status_code == 200
                assert resp.json() == {"status": "triggered"}

    def test_unknown_route_404(self):
        from fastapi.testclient import TestClient

        from closeclaw.api import create_gateway

        settings = _gateway_settings()
        mock_tg = _mock_tg_app()
        p1, p2 = _patched_gateway(settings, mock_tg)

        with p1, p2:
            app = create_gateway(settings)
            with TestClient(app) as client:
                resp = client.get("/nonexistent")
                assert resp.status_code in (404, 405)

    def test_lifespan_starts_telegram(self):
        from fastapi.testclient import TestClient

        from closeclaw.api import create_gateway

        settings = _gateway_settings()
        mock_tg = _mock_tg_app()

        with (
            patch(
                "closeclaw.channels.telegram.build_telegram_app",
                return_value=mock_tg,
            ) as build_mock,
            patch("closeclaw.channels.telegram._get_session"),
        ):
            app = create_gateway(settings)
            with TestClient(app):
                build_mock.assert_called_once_with(settings)
                mock_tg.initialize.assert_called_once()
                mock_tg.start.assert_called_once()
                mock_tg.updater.start_polling.assert_called_once()
