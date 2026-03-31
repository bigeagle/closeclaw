"""Tests for closeclaw.config."""

from __future__ import annotations

import os
from unittest.mock import patch

import closeclaw.config as config_mod
from closeclaw.config import Settings


def _settings(yaml_file=None, **env: str) -> Settings:
    """Create Settings from explicit env vars / yaml, ignoring real .env."""
    with (
        patch.dict(os.environ, env, clear=False),
        patch.object(config_mod, "_config_file", yaml_file),
    ):
        return Settings(_env_file=None)


# ── Defaults ──────────────────────────────────────────────────────────────────


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

    def test_agent_defaults(self):
        s = _settings()
        assert s.agent.agent_file == ""
        assert s.agent.workspace == ""

    def test_vision_default(self):
        s = _settings()
        assert s.enable_vision is False


# ── Env overrides ─────────────────────────────────────────────────────────────


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

    def test_enable_vision(self):
        s = _settings(ENABLE_VISION="true")
        assert s.enable_vision is True


# ── Allowed user ids parsing ──────────────────────────────────────────────────


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


# ── YAML config loading ──────────────────────────────────────────────────────


class TestYamlConfig:
    def test_load_agent_from_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("agent:\n  agent_file: my-agent.yaml\n  workspace: /tmp/ws\n")
        s = _settings(yaml_file=str(f))
        assert s.agent.agent_file == "my-agent.yaml"
        assert s.agent.workspace == "/tmp/ws"

    def test_yaml_overrides_defaults(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("kimi_model: yaml-model\n")
        s = _settings(yaml_file=str(f))
        assert s.kimi_model == "yaml-model"

    def test_env_overrides_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("kimi_model: yaml-model\n")
        s = _settings(yaml_file=str(f), KIMI_MODEL="env-model")
        assert s.kimi_model == "env-model"

    def test_missing_yaml_ignored(self):
        s = _settings(yaml_file="/nonexistent/config.yaml")
        assert s.kimi_model == "kimi-k2.5"
        assert s.agent.agent_file == ""

    def test_partial_agent_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("agent:\n  workspace: /work\n")
        s = _settings(yaml_file=str(f))
        assert s.agent.workspace == "/work"
        assert s.agent.agent_file == ""  # default preserved
