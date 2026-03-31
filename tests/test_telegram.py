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
