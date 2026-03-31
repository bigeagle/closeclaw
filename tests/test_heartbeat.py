"""Tests for AgentSession.fork() and heartbeat logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import closeclaw.config as config_mod
from closeclaw.agent_core.loop import AgentSession, TextDelta, TurnDone
from closeclaw.config import AgentSettings, HeartbeatSettings, Settings
from kosong.message import Message


def _make_settings(session_dir: str = "") -> Settings:
    with patch.object(config_mod, "_config_file", None):
        return Settings(
            _env_file=None,
            kimi_api_key="fake-key",
            kimi_model="test-model",
            kimi_base_url="https://fake.test",
            agent=AgentSettings(session_dir=session_dir),
        )


def _session(tmp_path, chat_id=42):
    return AgentSession(_make_settings(session_dir=str(tmp_path)), chat_id=chat_id)


# ── Fork tests ────────────────────────────────────────────────────────────────


class TestFork:
    def test_copies_history(self, tmp_path):
        s = _session(tmp_path)
        s.history.append(Message(role="user", content="hello"))
        s.history.append(Message(role="assistant", content="hi"))

        forked = s.fork()
        assert len(forked.history) == 2
        assert forked.history is not s.history

    def test_independent_history(self, tmp_path):
        s = _session(tmp_path)
        s.history.append(Message(role="user", content="hello"))

        forked = s.fork()
        forked.history.append(Message(role="assistant", content="from fork"))

        assert len(s.history) == 1
        assert len(forked.history) == 2

    def test_no_persistence(self, tmp_path):
        s = _session(tmp_path)
        forked = s.fork()

        assert forked._session_dir is None
        assert forked.chat_id is None

        # _save should be a no-op (no crash, no file)
        forked.history.append(Message(role="user", content="test"))
        forked._save()

    def test_shares_provider_and_toolset(self, tmp_path):
        s = _session(tmp_path)
        forked = s.fork()

        assert forked._provider is s._provider
        assert forked._toolset is s._toolset
        assert forked.system_prompt is s.system_prompt

    def test_different_session_id(self, tmp_path):
        s = _session(tmp_path)
        forked = s.fork()

        assert forked.session_id != s.session_id

    def test_deep_copy_messages(self, tmp_path):
        """Mutating a message in the fork must not affect the original."""
        s = _session(tmp_path)
        s.history.append(Message(role="user", content="original"))

        forked = s.fork()
        # The Message objects should be independent copies
        assert forked.history[0] is not s.history[0]


# ── Heartbeat logic tests ────────────────────────────────────────────────────


def _heartbeat_settings(
    chat_id: int = 42,
    prompt: str = "heartbeat check",
) -> Settings:
    with patch.object(config_mod, "_config_file", None):
        return Settings(
            _env_file=None,
            kimi_api_key="fake-key",
            kimi_model="test-model",
            kimi_base_url="https://fake.test",
            main_session_chat_id=chat_id,
            heartbeat=HeartbeatSettings(enabled=True, prompt=prompt),
        )


class TestRunHeartbeat:
    async def test_heartbeat_ok_no_writeback(self):
        """Agent replies HEARTBEAT_OK → no message sent, no history change."""
        import closeclaw.channels.telegram as tg_mod

        settings = _heartbeat_settings()
        bot = AsyncMock()

        # Create a mock main session with fork support
        main_session = MagicMock()
        main_session.history = [Message(role="user", content="old")]
        original_len = len(main_session.history)

        forked = MagicMock()
        forked.history = list(main_session.history) + [
            Message(role="user", content="heartbeat check"),
            Message(role="assistant", content="HEARTBEAT_OK"),
        ]

        async def fake_chat(prompt):
            yield TextDelta(text="HEARTBEAT_OK")
            yield TurnDone(text="HEARTBEAT_OK")

        forked.chat = fake_chat
        main_session.fork.return_value = forked

        old_sessions = tg_mod._sessions.copy()
        try:
            tg_mod._sessions.clear()
            tg_mod._sessions[42] = main_session

            await tg_mod._run_heartbeat(bot, settings)

            # No message sent
            bot.send_message.assert_not_called()
            # History unchanged
            assert len(main_session.history) == original_len
        finally:
            tg_mod._sessions.clear()
            tg_mod._sessions.update(old_sessions)

    async def test_heartbeat_no_reply_silent(self):
        """Agent replies NO_REPLY → silent, no write-back."""
        import closeclaw.channels.telegram as tg_mod

        settings = _heartbeat_settings()
        bot = AsyncMock()

        main_session = MagicMock()
        main_session.history = []

        forked = MagicMock()
        forked.history = [
            Message(role="user", content="heartbeat check"),
            Message(role="assistant", content="NO_REPLY"),
        ]

        async def fake_chat(prompt):
            yield TextDelta(text="NO_REPLY")
            yield TurnDone(text="NO_REPLY")

        forked.chat = fake_chat
        main_session.fork.return_value = forked

        old_sessions = tg_mod._sessions.copy()
        try:
            tg_mod._sessions.clear()
            tg_mod._sessions[42] = main_session

            await tg_mod._run_heartbeat(bot, settings)
            bot.send_message.assert_not_called()
        finally:
            tg_mod._sessions.clear()
            tg_mod._sessions.update(old_sessions)

    async def test_heartbeat_writeback(self):
        """Agent replies with real text → message sent + history written back."""
        import closeclaw.channels.telegram as tg_mod

        settings = _heartbeat_settings()
        bot = AsyncMock()

        main_session = MagicMock()
        main_session.history = [Message(role="user", content="old")]

        hb_user = Message(role="user", content="heartbeat check")
        hb_reply = Message(role="assistant", content="You have new files!")
        forked = MagicMock()
        forked.history = list(main_session.history) + [hb_user, hb_reply]

        async def fake_chat(prompt):
            yield TextDelta(text="You have new files!")
            yield TurnDone(text="You have new files!")

        forked.chat = fake_chat
        main_session.fork.return_value = forked

        old_sessions = tg_mod._sessions.copy()
        try:
            tg_mod._sessions.clear()
            tg_mod._sessions[42] = main_session

            await tg_mod._run_heartbeat(bot, settings)

            # Text sent to Telegram
            assert bot.send_message.called
            # History extended with the heartbeat delta
            assert len(main_session.history) == 3  # 1 original + 2 from heartbeat
            assert main_session.history[1] is hb_user
            assert main_session.history[2] is hb_reply
            main_session._save.assert_called_once()
        finally:
            tg_mod._sessions.clear()
            tg_mod._sessions.update(old_sessions)

    async def test_skipped_without_main_session(self):
        """Heartbeat is skipped when main_session_chat_id is 0."""
        import closeclaw.channels.telegram as tg_mod

        settings = _heartbeat_settings(chat_id=0)
        bot = AsyncMock()
        await tg_mod._run_heartbeat(bot, settings)
        bot.send_message.assert_not_called()

    async def test_skipped_without_prompt(self):
        """Heartbeat is skipped when prompt is empty."""
        import closeclaw.channels.telegram as tg_mod

        settings = _heartbeat_settings(prompt="")
        bot = AsyncMock()
        await tg_mod._run_heartbeat(bot, settings)
        bot.send_message.assert_not_called()
