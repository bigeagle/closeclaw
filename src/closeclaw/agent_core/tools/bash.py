"""Bash shell tool – lets the agent execute shell commands."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue

MAX_OUTPUT_CHARS = 30_000


class BashParams(BaseModel):
    command: str = Field(description="The bash command to execute.")
    timeout: int = Field(
        default=60,
        description="Timeout in seconds for the command.",
        ge=1,
        le=600,
    )


class BashTool(CallableTool2[BashParams]):
    name: str = "bash"
    description: str = (
        "Execute a bash command in the system shell and return its combined "
        "stdout + stderr output."
    )
    params: type[BashParams] = BashParams

    async def __call__(self, params: BashParams) -> ToolReturnValue:
        try:
            proc = await asyncio.create_subprocess_shell(
                params.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=params.timeout,
            )
        except asyncio.TimeoutError:
            return ToolError(
                message=f"Command timed out after {params.timeout}s.",
                brief="timeout",
            )
        except Exception as exc:
            return ToolError(message=str(exc), brief="exec error")

        output = ""
        if stdout:
            output += stdout.decode(errors="replace")
        if stderr:
            output += stderr.decode(errors="replace")

        if not output:
            output = "(no output)"
        elif len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (output truncated)"

        exit_code = proc.returncode
        brief = f"exit {exit_code}"
        if exit_code != 0:
            output = f"[exit code {exit_code}]\n{output}"

        return ToolOk(output=output, brief=brief)
