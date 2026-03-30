"""Shell tool (forked from kimi_cli, simplified: no Approval, no background tasks)."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import override

import kaos
from kaos import AsyncReadable
from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._utils import ToolResultBuilder, load_desc

MAX_FOREGROUND_TIMEOUT = 5 * 60


def _get_noninteractive_env() -> dict[str, str]:
    """Get an environment for subprocesses that must not block on interactive prompts."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False) and sys.platform == "linux":
        for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            orig_key = f"{var}_ORIG"
            if orig_key in env:
                env[var] = env[orig_key]
            elif var in env:
                del env[var]
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


class Params(BaseModel):
    command: str = Field(description="The bash command to execute.")
    timeout: int = Field(
        description="The timeout in seconds for the command to execute. "
        "If the command takes longer than this, it will be killed.",
        default=60,
        ge=1,
        le=MAX_FOREGROUND_TIMEOUT,
    )


class Shell(CallableTool2[Params]):
    name: str = "Shell"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        super().__init__(
            description=load_desc(Path(__file__).parent / "descs" / "shell.md")
        )
        self._work_dir = str(runtime.work_dir)

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        if not params.command:
            return builder.error("Command cannot be empty.", brief="Empty command")

        def stdout_cb(line: bytes) -> None:
            builder.write(line.decode(encoding="utf-8", errors="replace"))

        def stderr_cb(line: bytes) -> None:
            builder.write(line.decode(encoding="utf-8", errors="replace"))

        try:
            exitcode = await self._run_shell_command(
                params.command, stdout_cb, stderr_cb, params.timeout
            )
            if exitcode == 0:
                return builder.ok("Command executed successfully.")
            else:
                return builder.error(
                    f"Command failed with exit code: {exitcode}.",
                    brief=f"Failed with exit code: {exitcode}",
                )
        except TimeoutError:
            return builder.error(
                f"Command killed by timeout ({params.timeout}s)",
                brief=f"Killed by timeout ({params.timeout}s)",
            )

    async def _run_shell_command(
        self,
        command: str,
        stdout_cb: Callable[[bytes], None],
        stderr_cb: Callable[[bytes], None],
        timeout: int,
    ) -> int:
        async def _read_stream(
            stream: AsyncReadable, cb: Callable[[bytes], None]
        ) -> None:
            while True:
                line = await stream.readline()
                if line:
                    cb(line)
                else:
                    break

        process = await kaos.exec(
            "/bin/bash",
            "-c",
            command,
            env=_get_noninteractive_env(),
        )
        process.stdin.close()

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    _read_stream(process.stdout, stdout_cb),
                    _read_stream(process.stderr, stderr_cb),
                ),
                timeout,
            )
            return await process.wait()
        except asyncio.CancelledError:
            await process.kill()
            raise
        except TimeoutError:
            await process.kill()
            raise
