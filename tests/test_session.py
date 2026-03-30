"""Tests for session persistence in AgentSession."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import closeclaw.config as config_mod
from closeclaw.agent_core.loop import AgentSession
from closeclaw.config import AgentSettings, Settings
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


class TestNewSession:
    def test_gets_uuid(self, tmp_path):
        s = _session(tmp_path)
        # UUID4 format: 8-4-4-4-12 hex
        assert len(s.session_id) == 36
        assert s.session_id.count("-") == 4

    def test_empty_history(self, tmp_path):
        s = _session(tmp_path)
        assert s.history == []

    def test_creates_session_dir(self, tmp_path):
        d = tmp_path / "sub" / "sessions"
        AgentSession(_make_settings(session_dir=str(d)), chat_id=1)
        assert d.is_dir()


class TestSave:
    def test_creates_file(self, tmp_path):
        s = _session(tmp_path)
        s.history.append(Message(role="user", content="hello"))
        s._save()
        chat_dir = tmp_path / "42"
        files = list(chat_dir.glob("*.json"))
        assert len(files) == 1
        assert files[0].name == f"{s.session_id}.json"

    def test_file_content(self, tmp_path):
        s = _session(tmp_path)
        s.history.append(Message(role="user", content="hello"))
        s.history.append(Message(role="assistant", content="hi"))
        s._save()
        chat_dir = tmp_path / "42"
        data = json.loads((chat_dir / f"{s.session_id}.json").read_text())
        assert data["session_id"] == s.session_id
        assert data["chat_id"] == 42
        assert "updated_at" in data
        assert len(data["history"]) == 2
        assert data["history"][0]["role"] == "user"
        assert data["history"][1]["role"] == "assistant"

    def test_no_save_without_chat_id(self, tmp_path):
        s = _session(tmp_path, chat_id=None)
        s.history.append(Message(role="user", content="hello"))
        s._save()
        assert list(tmp_path.glob("*.json")) == []

    def test_no_save_without_session_dir(self):
        s = AgentSession(_make_settings(session_dir=""), chat_id=42)
        s.history.append(Message(role="user", content="hello"))
        s._save()  # should not raise


class TestResume:
    def test_resumes_session(self, tmp_path):
        s1 = _session(tmp_path)
        s1.history.append(Message(role="user", content="hello"))
        s1.history.append(Message(role="assistant", content="hi"))
        s1._save()

        s2 = _session(tmp_path)
        assert s2.session_id == s1.session_id
        assert len(s2.history) == 2
        assert s2.history[0].role == "user"
        assert s2.history[1].role == "assistant"

    def test_different_chat_id_no_resume(self, tmp_path):
        s1 = _session(tmp_path, chat_id=42)
        s1.history.append(Message(role="user", content="hello"))
        s1._save()

        s2 = _session(tmp_path, chat_id=99)
        assert s2.session_id != s1.session_id
        assert s2.history == []

    def test_resumes_most_recent(self, tmp_path):
        # Write session files into the chat_id subdirectory
        chat_dir = tmp_path / "42"
        chat_dir.mkdir(parents=True)

        old_data = {
            "session_id": "old-0000-0000-0000-000000000000",
            "chat_id": 42,
            "updated_at": "2025-01-01T00:00:00+00:00",
            "history": [{"role": "user", "content": "old"}],
        }
        old_path = chat_dir / "old-0000-0000-0000-000000000000.json"
        old_path.write_text(json.dumps(old_data))

        time.sleep(0.05)

        new_data = {
            "session_id": "new-0000-0000-0000-000000000000",
            "chat_id": 42,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "history": [{"role": "user", "content": "new"}],
        }
        new_path = chat_dir / "new-0000-0000-0000-000000000000.json"
        new_path.write_text(json.dumps(new_data))

        s = _session(tmp_path)
        assert s.session_id == "new-0000-0000-0000-000000000000"
        assert s.history[0].extract_text() == "new"

    def test_updates_same_file(self, tmp_path):
        s1 = _session(tmp_path)
        s1.history.append(Message(role="user", content="hello"))
        s1._save()

        s2 = _session(tmp_path)
        s2.history.append(Message(role="user", content="world"))
        s2._save()

        chat_dir = tmp_path / "42"
        files = list(chat_dir.glob("*.json"))
        assert len(files) == 1  # same file, not a new one
        data = json.loads(files[0].read_text())
        assert len(data["history"]) == 2  # 1 resumed from s1 + 1 new
