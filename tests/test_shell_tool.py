"""Tests for closeclaw.agent_core.tools.shell."""

from __future__ import annotations

import pytest

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools.shell import Shell, Params


@pytest.fixture
def tool() -> Shell:
    return Shell(Runtime.from_cwd())


class TestShellExecution:
    async def test_echo(self, tool: Shell):
        result = await tool(Params(command="echo hello"))
        assert not result.is_error
        assert isinstance(result.output, str)
        assert "hello" in result.output

    async def test_multiline(self, tool: Shell):
        result = await tool(Params(command="echo line1; echo line2"))
        assert "line1" in result.output
        assert "line2" in result.output

    async def test_stderr_captured(self, tool: Shell):
        result = await tool(Params(command="echo err >&2"))
        assert "err" in result.output


class TestExitCode:
    async def test_nonzero_exit(self, tool: Shell):
        result = await tool(Params(command="exit 42"))
        assert result.is_error
        assert "42" in result.message

    async def test_no_output(self, tool: Shell):
        result = await tool(Params(command="true"))
        assert not result.is_error


class TestTimeout:
    async def test_command_timeout(self, tool: Shell):
        result = await tool(Params(command="sleep 10", timeout=1))
        assert result.is_error
        assert "timeout" in result.message.lower()


class TestTruncation:
    async def test_long_output_truncated(self, tool: Shell):
        # Generate output longer than the default max_chars (50_000)
        cmd = "python3 -c \"print('x' * 60000)\""
        result = await tool(Params(command=cmd))
        assert not result.is_error
        assert isinstance(result.output, str)
        assert "truncated" in result.message.lower()
