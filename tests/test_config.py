"""Tests for closeclaw.config."""

from __future__ import annotations

import os
from unittest.mock import patch

from closeclaw.config import Settings


def _settings(**env: str) -> Settings:
    """Create Settings from explicit env vars, ignoring .env file."""
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


class TestDefaults:
    def test_kimi_defaults(self):
        s = _settings()
        assert s.kimi_api_key == ""
        assert s.kimi_base_url == "https://api.moonshot.ai/v1"
        assert s.kimi_model == "kimi-k2.5"

    def test_telegram_defaults(self):
        s = _settings()
        assert s.telegram_bot_token == ""
        assert s.telegram_allowed_users == ""
        assert s.allowed_user_ids == []


class TestEnvOverride:
    def test_kimi_api_key(self):
        s = _settings(KIMI_API_KEY="sk-test-123")
        assert s.kimi_api_key == "sk-test-123"

    def test_kimi_model(self):
        s = _settings(KIMI_MODEL="custom-model")
        assert s.kimi_model == "custom-model"

    def test_telegram_bot_token(self):
        s = _settings(TELEGRAM_BOT_TOKEN="123:ABC")
        assert s.telegram_bot_token == "123:ABC"


class TestAllowedUserIds:
    def test_empty_string(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="")
        assert s.allowed_user_ids == []

    def test_single_id(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="42")
        assert s.allowed_user_ids == [42]

    def test_multiple_ids(self):
        s = _settings(TELEGRAM_ALLOWED_USERS="111,222,333")
        assert s.allowed_user_ids == [111, 222, 333]

    def test_whitespace_handling(self):
        s = _settings(TELEGRAM_ALLOWED_USERS=" 111 , 222 , 333 ")
        assert s.allowed_user_ids == [111, 222, 333]
