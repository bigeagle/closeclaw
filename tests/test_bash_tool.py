"""Tests for closeclaw.agent_core.tools.bash."""

from __future__ import annotations

import pytest

from closeclaw.agent_core.tools.bash import BashTool, BashParams, MAX_OUTPUT_CHARS


@pytest.fixture
def tool() -> BashTool:
    return BashTool()


class TestBashExecution:
    async def test_echo(self, tool: BashTool):
        result = await tool(BashParams(command="echo hello"))
        assert not result.is_error
        assert isinstance(result.output, str)
        assert "hello" in result.output

    async def test_multiline(self, tool: BashTool):
        result = await tool(BashParams(command="echo line1; echo line2"))
        assert "line1" in result.output
        assert "line2" in result.output

    async def test_stderr_captured(self, tool: BashTool):
        result = await tool(BashParams(command="echo err >&2"))
        assert "err" in result.output


class TestExitCode:
    async def test_nonzero_exit(self, tool: BashTool):
        result = await tool(BashParams(command="exit 42"))
        assert not result.is_error  # ToolOk, but exit code in output
        assert "exit code 42" in result.output

    async def test_no_output(self, tool: BashTool):
        result = await tool(BashParams(command="true"))
        assert not result.is_error
        assert "(no output)" in result.output


class TestTimeout:
    async def test_command_timeout(self, tool: BashTool):
        result = await tool(BashParams(command="sleep 10", timeout=1))
        assert result.is_error
        assert "timed out" in result.message.lower()


class TestTruncation:
    async def test_long_output_truncated(self, tool: BashTool):
        # Generate output longer than MAX_OUTPUT_CHARS
        cmd = f"python3 -c \"print('x' * {MAX_OUTPUT_CHARS + 1000})\""
        result = await tool(BashParams(command=cmd))
        assert not result.is_error
        assert isinstance(result.output, str)
        assert "truncated" in result.output
        assert len(result.output) <= MAX_OUTPUT_CHARS + 200  # some slack for suffix
