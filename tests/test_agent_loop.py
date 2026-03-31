"""Tests for closeclaw.agent_core.loop (AgentSession)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch


import kosong
from kosong.message import Message, TextPart, ToolCall
from kosong.tooling import ToolError, ToolOk, ToolResult

from closeclaw.agent_core.loop import (
    AgentSession,
    ImageOutput,
    TextDelta,
    ToolCallDone,
    ToolCallStart,
    TurnDone,
)
from closeclaw.config import Settings


def _make_settings() -> Settings:
    return Settings(
        _env_file=None,
        kimi_api_key="fake-key",
        kimi_model="test-model",
        kimi_base_url="https://fake.test",
    )


def _make_step_result(
    *,
    content: str = "",
    tool_calls: list[ToolCall] | None = None,
    tool_outputs: dict[str, str] | None = None,
    tool_errors: dict[str, bool] | None = None,
) -> kosong.StepResult:
    """Build a StepResult, optionally with pre-resolved tool futures."""
    tc_list = tool_calls or []
    futures: dict[str, asyncio.Future[ToolResult]] = {}
    errors = tool_errors or {}

    for tc in tc_list:
        fut: asyncio.Future[ToolResult] = asyncio.get_event_loop().create_future()
        output = (tool_outputs or {}).get(tc.id, "")
        if tc.id in errors:
            rv = ToolError(message=output, brief="error")
        else:
            rv = ToolOk(output=output)
        fut.set_result(ToolResult(tool_call_id=tc.id, return_value=rv))
        futures[tc.id] = fut

    return kosong.StepResult(
        id="test",
        message=Message(role="assistant", content=content, tool_calls=tc_list or None),
        usage=None,
        tool_calls=tc_list,
        _tool_result_futures=futures,
    )


class TestSimpleResponse:
    async def test_text_deltas_and_turn_done(self):
        """No tool calls → TextDelta stream + TurnDone."""

        async def mock_step(*_args, **kwargs):
            omp = kwargs.get("on_message_part")
            if omp:
                omp(TextPart(text="Hello"))
                omp(TextPart(text=" world"))
            return _make_step_result(content="Hello world")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            events = [e async for e in session.chat("Hi")]

        deltas = [e for e in events if isinstance(e, TextDelta)]
        assert [d.text for d in deltas] == ["Hello", " world"]

        dones = [e for e in events if isinstance(e, TurnDone)]
        assert len(dones) == 1
        assert dones[0].text == "Hello world"

    async def test_history_appended(self):
        """User + assistant messages are added to history."""

        async def mock_step(*_args, **kwargs):
            return _make_step_result(content="reply")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            _ = [e async for e in session.chat("hello")]

        assert len(session.history) == 2
        assert session.history[0].role == "user"
        assert session.history[1].role == "assistant"


class TestToolCallLoop:
    async def test_tool_call_then_final_response(self):
        """Step 1: tool call → Step 2: final text."""
        call_count = 0

        async def mock_step(*_args, **kwargs):
            nonlocal call_count
            call_count += 1
            omp = kwargs.get("on_message_part")

            if call_count == 1:
                tc = ToolCall(
                    id="tc-1",
                    function=ToolCall.FunctionBody(
                        name="bash", arguments='{"command":"date"}'
                    ),
                )
                return _make_step_result(
                    tool_calls=[tc], tool_outputs={"tc-1": "Mon Mar 30"}
                )
            else:
                if omp:
                    omp(TextPart(text="Today is March 30."))
                return _make_step_result(content="Today is March 30.")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            events = [e async for e in session.chat("date?")]

        types = [type(e).__name__ for e in events]
        assert "ToolCallStart" in types
        assert "ToolCallDone" in types
        assert "TextDelta" in types
        assert "TurnDone" in types

        tc_start = next(e for e in events if isinstance(e, ToolCallStart))
        assert tc_start.name == "bash"

        tc_done = next(e for e in events if isinstance(e, ToolCallDone))
        assert tc_done.output == "Mon Mar 30"
        assert tc_done.is_error is False

    async def test_tool_result_in_history(self):
        """Tool message is added to history between steps."""
        call_count = 0

        async def mock_step(*_args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                tc = ToolCall(
                    id="tc-1",
                    function=ToolCall.FunctionBody(name="bash", arguments="{}"),
                )
                return _make_step_result(
                    tool_calls=[tc], tool_outputs={"tc-1": "output"}
                )
            return _make_step_result(content="done")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            _ = [e async for e in session.chat("go")]

        roles = [m.role for m in session.history]
        assert roles == ["user", "assistant", "tool", "assistant"]


class TestImageOutput:
    async def test_send_photo_yields_image_output(self):
        """SendPhoto tool call yields an ImageOutput event."""
        call_count = 0

        async def mock_step(*_args, **kwargs):
            nonlocal call_count
            call_count += 1
            omp = kwargs.get("on_message_part")

            if call_count == 1:
                tc = ToolCall(
                    id="tc-photo",
                    function=ToolCall.FunctionBody(
                        name="SendImage",
                        arguments='{"path": "/tmp/test.png"}',
                    ),
                )
                return _make_step_result(
                    tool_calls=[tc],
                    tool_outputs={
                        "tc-photo": '{"path": "/tmp/test.png", "caption": "a chart"}'
                    },
                )
            else:
                if omp:
                    omp(TextPart(text="Here is the image."))
                return _make_step_result(content="Here is the image.")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            events = [e async for e in session.chat("show chart")]

        img_events = [e for e in events if isinstance(e, ImageOutput)]
        assert len(img_events) == 1
        assert img_events[0].path == "/tmp/test.png"
        assert img_events[0].caption == "a chart"

    async def test_no_image_output_on_error(self):
        """Failed SendPhoto tool call does NOT yield ImageOutput."""
        call_count = 0

        async def mock_step(*_args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                tc = ToolCall(
                    id="tc-fail",
                    function=ToolCall.FunctionBody(
                        name="SendImage",
                        arguments='{"path": "/no/such/file.png"}',
                    ),
                )
                return _make_step_result(
                    tool_calls=[tc],
                    tool_outputs={"tc-fail": "File not found"},
                    tool_errors={"tc-fail": True},
                )
            return _make_step_result(content="Sorry, failed.")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            events = [e async for e in session.chat("send pic")]

        img_events = [e for e in events if isinstance(e, ImageOutput)]
        assert len(img_events) == 0


class TestMultimodalInput:
    async def test_chat_with_content_parts(self):
        """chat() accepts list[ContentPart] for multi-modal input."""
        from kosong.message import ImageURLPart

        async def mock_step(*_args, **kwargs):
            omp = kwargs.get("on_message_part")
            if omp:
                omp(TextPart(text="I see an image."))
            return _make_step_result(content="I see an image.")

        with patch("closeclaw.agent_core.loop.kosong.step", side_effect=mock_step):
            session = AgentSession(_make_settings())
            content = [
                TextPart(text="describe this"),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,iVBOR")
                ),
            ]
            events = [e async for e in session.chat(content)]

        dones = [e for e in events if isinstance(e, TurnDone)]
        assert len(dones) == 1
        assert dones[0].text == "I see an image."

        # History should contain the multi-modal user message
        assert session.history[0].role == "user"
        assert isinstance(session.history[0].content, list)
