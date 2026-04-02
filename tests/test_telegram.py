"""Tests for closeclaw.channels.telegram helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

from closeclaw.channels.telegram import (
    _is_allowed,
    _truncate,
)
from closeclaw.config import Settings


def _settings(**env: str) -> Settings:
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


class TestIsAllowed:
    def test_empty_allows_everyone(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="")
        assert _is_allowed(999, s) is True

    def test_user_in_list(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="111,222")
        assert _is_allowed(111, s) is True
        assert _is_allowed(222, s) is True

    def test_user_not_in_list(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="111,222")
        assert _is_allowed(333, s) is False


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_long_text_truncated(self):
        text = "x" * 5000
        result = _truncate(text)
        assert len(result) < len(text)
        assert "truncated" in result

    def test_custom_limit(self):
        text = "abcdefghij"
        result = _truncate(text, limit=5)
        assert "truncated" in result

    def test_exactly_at_limit(self):
        limit = 100
        text = "x" * limit
        assert _truncate(text, limit=limit) == text


class TestDownloadPhotoBase64:
    async def test_returns_data_url(self):
        from unittest.mock import AsyncMock, MagicMock

        from closeclaw.channels.telegram import _download_photo_base64

        fake_file = AsyncMock()
        fake_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"\x89PNG"))

        fake_bot = AsyncMock()
        fake_bot.get_file = AsyncMock(return_value=fake_file)

        photo = MagicMock()
        photo.file_id = "abc123"

        result = await _download_photo_base64(fake_bot, photo)
        assert result.startswith("data:image/jpeg;base64,")
        # Verify the base64 payload decodes back
        import base64

        b64_part = result.split(",", 1)[1]
        assert base64.b64decode(b64_part) == b"\x89PNG"
        fake_bot.get_file.assert_called_once_with("abc123")


class TestGetSession:
    def test_creates_and_caches(self):
        """_get_session creates an AgentSession and caches it in _sessions."""
        from unittest.mock import MagicMock, patch as _patch

        import closeclaw.channels.telegram as tg_mod
        from closeclaw.channels.telegram import _get_session

        s = _settings(KIMI_API_KEY="fake-key")
        fake_session = MagicMock()

        old_sessions = tg_mod._sessions.copy()
        try:
            tg_mod._sessions.clear()
            with _patch.object(tg_mod, "AgentSession", return_value=fake_session):
                result = _get_session(12345, s)
                assert result is fake_session
                assert tg_mod._sessions[12345] is fake_session

                # Second call returns cached session, no new creation
                result2 = _get_session(12345, s)
                assert result2 is fake_session
        finally:
            tg_mod._sessions.clear()
            tg_mod._sessions.update(old_sessions)


class TestInsertDateTick:
    async def test_inserts_into_main_and_active_sessions(self):
        import asyncio
        from unittest.mock import MagicMock, patch as _patch

        import closeclaw.channels.telegram as tg_mod
        from closeclaw.channels.telegram import _insert_date_tick

        s = _settings(KIMI_API_KEY="fake-key", MAIN_SESSION_CHAT_ID="42")

        main_session = MagicMock()
        main_session.history = []
        other_session = MagicMock()
        other_session.history = []

        old_sessions = tg_mod._sessions.copy()
        old_lock = tg_mod._heartbeat_lock
        try:
            tg_mod._sessions.clear()
            tg_mod._sessions[42] = main_session
            tg_mod._sessions[99] = other_session
            tg_mod._heartbeat_lock = asyncio.Lock()

            with _patch.object(tg_mod, "AgentSession"):
                await _insert_date_tick(s)

            assert len(main_session.history) == 1
            assert main_session._save.called
            msg = main_session.history[0]
            assert msg.role == "user"
            text = msg.content[0].text
            assert "<system-event>" in text
            assert "Current date" in text
            assert "Weekday:" in text

            assert len(other_session.history) == 1
            assert other_session._save.called
        finally:
            tg_mod._sessions.clear()
            tg_mod._sessions.update(old_sessions)
            tg_mod._heartbeat_lock = old_lock
