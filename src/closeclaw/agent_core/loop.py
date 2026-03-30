"""Agent session & loop – drives the kosong step loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from loguru import logger

import kosong
from kosong.chat_provider.kimi import Kimi
from kosong.message import Message, TextPart
from kosong.tooling.simple import SimpleToolset

from closeclaw.agent_core.tools import BashTool
from closeclaw.config import Settings

DEFAULT_SYSTEM_PROMPT = """\
You are CloseClaw, a helpful AI assistant with access to a bash shell.
Use the bash tool to run commands when the user asks you to interact with the system.
Always be concise and helpful.\
"""

MAX_STEPS = 20


# ── Events yielded by the agent loop ──────────────────────────────────────────


@dataclass
class AgentEvent:
    """Base class for events produced by the agent loop."""


@dataclass
class TextDelta(AgentEvent):
    """A chunk of streamed text from the model."""
    text: str


@dataclass
class ThinkDelta(AgentEvent):
    """A chunk of model thinking/reasoning."""
    text: str


@dataclass
class ToolCallStart(AgentEvent):
    """The model invoked a tool."""
    name: str
    arguments: str


@dataclass
class ToolCallDone(AgentEvent):
    """A tool call completed."""
    name: str
    output: str
    is_error: bool


@dataclass
class TurnDone(AgentEvent):
    """The agent finished a full turn (no more tool calls)."""
    text: str


# ── AgentSession ──────────────────────────────────────────────────────────────


class AgentSession:
    """Manages a single conversation with the agent."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self.settings = settings
        self.system_prompt = system_prompt
        self.history: list[Message] = []

        self._provider = Kimi(
            model=settings.kimi_model,
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
        )

        self._toolset = SimpleToolset()
        self._toolset += BashTool()

    # ── public API ────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """Send a user message and yield events as the agent responds.

        The caller iterates the generator to receive streaming deltas, tool
        events, and the final ``TurnDone`` event.
        """
        self.history.append(Message(role="user", content=user_message))

        for _step in range(MAX_STEPS):
            result = await kosong.step(
                chat_provider=self._provider,
                system_prompt=self.system_prompt,
                toolset=self._toolset,
                history=self.history,
            )

            self.history.append(result.message)

            # No tool calls → we are done
            if not result.tool_calls:
                final_text = result.message.extract_text()
                yield TurnDone(text=final_text)
                return

            # Process tool calls
            tool_results = await result.tool_results()
            for tc, tr in zip(result.tool_calls, tool_results):
                yield ToolCallStart(
                    name=tc.function.name,
                    arguments=tc.function.arguments or "",
                )

                output = tr.return_value.output
                if isinstance(output, list):
                    output_text = " ".join(
                        p.text for p in output if isinstance(p, TextPart)
                    )
                else:
                    output_text = output

                yield ToolCallDone(
                    name=tc.function.name,
                    output=output_text,
                    is_error=tr.return_value.is_error,
                )

                self.history.append(
                    Message(
                        role="tool",
                        content=tr.return_value.output,
                        tool_call_id=tr.tool_call_id,
                    )
                )

        # Reached max steps
        logger.warning("Agent reached max steps ({max_steps})", max_steps=MAX_STEPS)
        yield TurnDone(text="(Reached maximum number of steps.)")

    async def chat_simple(self, user_message: str) -> str:
        """Convenience wrapper – returns the final text only."""
        final = ""
        async for event in self.chat(user_message):
            if isinstance(event, TurnDone):
                final = event.text
        return final
