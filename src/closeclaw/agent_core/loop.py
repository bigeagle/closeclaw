"""Agent session & loop – drives the kosong step loop."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

import kosong
from kosong.chat_provider import StreamedMessagePart
from kosong.chat_provider.kimi import Kimi
from kosong.message import Message, TextPart, ThinkPart
from closeclaw.agent_core.agent_config import (
    AgentConfig,
    load_agent_config,
    load_system_prompt,
)
from closeclaw.agent_core.loader import load_tools
from closeclaw.agent_core.runtime import Runtime
from closeclaw.config import Settings

MAX_STEPS = 20

_SENTINEL = object()


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
        agent_config: AgentConfig | None = None,
        config_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.history: list[Message] = []

        # Apply workspace before anything that depends on cwd
        workspace = settings.agent.workspace
        if workspace:
            os.chdir(workspace)
        logger.info("Workspace: {ws}", ws=os.getcwd())

        # Load agent config
        agent_file = settings.agent.agent_file
        if agent_config is None:
            if agent_file:
                config_dir = Path(agent_file).parent
            agent_config = load_agent_config(config_dir)
        logger.info(
            "Agent: {name} (config={cfg})",
            name=agent_config.agent.name or "default",
            cfg=agent_file or "built-in",
        )
        logger.info("Model: {model}", model=settings.kimi_model)

        # System prompt
        self.system_prompt = load_system_prompt(agent_config, config_dir)

        # Chat provider
        self._provider = Kimi(
            model=settings.kimi_model,
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
        )

        runtime = Runtime.from_cwd()
        self._toolset = load_tools(agent_config.agent.tools, runtime)
        logger.info(
            "Loaded tools: {tools}", tools=[t.name for t in self._toolset.tools]
        )

    # ── public API ────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """Send a user message and yield events as the agent responds.

        Yields ``TextDelta`` / ``ThinkDelta`` in real-time as the model
        streams, then tool events, and finally ``TurnDone``.
        """
        self.history.append(Message(role="user", content=user_message))

        for _step in range(MAX_STEPS):
            queue: asyncio.Queue[AgentEvent | object] = asyncio.Queue()

            def on_message_part(part: StreamedMessagePart) -> None:
                if isinstance(part, TextPart):
                    queue.put_nowait(TextDelta(text=part.text))
                elif isinstance(part, ThinkPart):
                    queue.put_nowait(ThinkDelta(text=part.think))

            async def _run_step() -> kosong.StepResult:
                try:
                    return await kosong.step(
                        chat_provider=self._provider,
                        system_prompt=self.system_prompt,
                        toolset=self._toolset,
                        history=self.history,
                        on_message_part=on_message_part,
                    )
                finally:
                    queue.put_nowait(_SENTINEL)

            task = asyncio.create_task(_run_step())

            # Yield streaming deltas as they arrive from on_message_part
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    break
                yield event  # type: ignore[misc]

            result = await task  # re-raises if step failed

            logger.debug(
                "Assistant message: {msg}",
                msg=result.message.model_dump(exclude_none=True),
            )
            self.history.append(result.message)

            # No tool calls → done
            if not result.tool_calls:
                yield TurnDone(text=result.message.extract_text())
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
