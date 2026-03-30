"""Glob tool (forked from kimi_cli)."""

from __future__ import annotations

from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._path_utils import (
    is_within_directory,
    is_within_workspace,
    list_directory,
)
from closeclaw.agent_core.tools._utils import load_desc

MAX_MATCHES = 1000


class Params(BaseModel):
    pattern: str = Field(description="Glob pattern to match files/directories.")
    directory: str | None = Field(
        description="Absolute path to the directory to search in (defaults to working directory).",
        default=None,
    )
    include_dirs: bool = Field(
        description="Whether to include directories in results.", default=True
    )


class Glob(CallableTool2[Params]):
    name: str = "Glob"
    description: str = load_desc(
        Path(__file__).parent / "descs" / "glob.md", {"MAX_MATCHES": str(MAX_MATCHES)}
    )
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._work_dir = runtime.work_dir
        self._additional_dirs = runtime.additional_dirs
        self._skills_dirs = runtime.skills_dirs

    async def _validate_pattern(self, pattern: str) -> ToolError | None:
        if pattern.startswith("**"):
            ls_result = await list_directory(self._work_dir)
            return ToolError(
                output=ls_result,
                message=f"Pattern `{pattern}` starts with '**' which is not allowed. Use more specific patterns instead.",
                brief="Unsafe pattern",
            )
        return None

    async def _validate_directory(self, directory: KaosPath) -> ToolError | None:
        resolved_dir = directory.canonical()
        if is_within_workspace(resolved_dir, self._work_dir, self._additional_dirs):
            return None
        if any(is_within_directory(resolved_dir, d) for d in self._skills_dirs):
            return None
        return ToolError(
            message=f"`{directory}` is outside the workspace.",
            brief="Directory outside workspace",
        )

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            pattern_error = await self._validate_pattern(params.pattern)
            if pattern_error:
                return pattern_error

            dir_path = (
                KaosPath(params.directory).expanduser()
                if params.directory
                else self._work_dir
            )
            if not dir_path.is_absolute():
                return ToolError(
                    message=f"`{params.directory}` is not an absolute path.",
                    brief="Invalid directory",
                )
            dir_error = await self._validate_directory(dir_path)
            if dir_error:
                return dir_error
            if not await dir_path.exists():
                return ToolError(
                    message=f"`{params.directory}` does not exist.",
                    brief="Directory not found",
                )
            if not await dir_path.is_dir():
                return ToolError(
                    message=f"`{params.directory}` is not a directory.",
                    brief="Invalid directory",
                )

            matches: list[KaosPath] = []
            async for match in dir_path.glob(params.pattern):
                matches.append(match)
            if not params.include_dirs:
                matches = [p for p in matches if await p.is_file()]
            matches.sort()

            message = (
                f"Found {len(matches)} matches for pattern `{params.pattern}`."
                if len(matches) > 0
                else f"No matches found for pattern `{params.pattern}`."
            )
            if len(matches) > MAX_MATCHES:
                matches = matches[:MAX_MATCHES]
                message += f" Only the first {MAX_MATCHES} matches are returned."
            return ToolOk(
                output="\n".join(str(p.relative_to(dir_path)) for p in matches),
                message=message,
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to search for pattern {params.pattern}. Error: {e}",
                brief="Glob failed",
            )
