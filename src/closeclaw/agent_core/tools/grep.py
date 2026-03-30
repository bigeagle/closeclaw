"""Grep tool (forked from kimi_cli, simplified)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import override

import ripgrepy
from kosong.tooling import CallableTool2, ToolError, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.tools._utils import ToolResultBuilder, load_desc


class Params(BaseModel):
    pattern: str = Field(
        description="The regular expression pattern to search for in file contents"
    )
    path: str = Field(
        description="File or directory to search in. Defaults to current working directory. If specified, it must be an absolute path.",
        default=".",
    )
    glob: str | None = Field(
        description="Glob pattern to filter files (e.g. `*.js`, `*.{ts,tsx}`). No filter by default.",
        default=None,
    )
    output_mode: str = Field(
        description="`content`: Show matching lines (supports `-B`, `-A`, `-C`, `-n`, `head_limit`); `files_with_matches`: Show file paths (supports `head_limit`); `count_matches`: Show total number of matches. Defaults to `files_with_matches`.",
        default="files_with_matches",
    )
    before_context: int | None = Field(
        alias="-B",
        description="Number of lines to show before each match (the `-B` option). Requires `output_mode` to be `content`.",
        default=None,
    )
    after_context: int | None = Field(
        alias="-A",
        description="Number of lines to show after each match (the `-A` option). Requires `output_mode` to be `content`.",
        default=None,
    )
    context: int | None = Field(
        alias="-C",
        description="Number of lines to show before and after each match (the `-C` option). Requires `output_mode` to be `content`.",
        default=None,
    )
    line_number: bool = Field(
        alias="-n",
        description="Show line numbers in output (the `-n` option). Requires `output_mode` to be `content`.",
        default=False,
    )
    ignore_case: bool = Field(
        alias="-i",
        description="Case insensitive search (the `-i` option).",
        default=False,
    )
    type: str | None = Field(
        description="File type to search. Examples: py, rust, js, ts, go, java, etc.",
        default=None,
    )
    head_limit: int | None = Field(
        description="Limit output to first N lines, equivalent to `| head -N`.",
        default=None,
    )
    multiline: bool = Field(
        description="Enable multiline mode where `.` matches newlines and patterns can span lines (the `-U` and `--multiline-dotall` options).",
        default=False,
    )


def _find_rg() -> str:
    rg = shutil.which("rg")
    if rg:
        return rg
    raise RuntimeError(
        "ripgrep (rg) is not installed. Install it via `brew install ripgrep` or equivalent."
    )


class Grep(CallableTool2[Params]):
    name: str = "Grep"
    description: str = load_desc(Path(__file__).parent / "descs" / "grep.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            builder = ToolResultBuilder()
            message = ""
            rg_path = _find_rg()
            rg = ripgrepy.Ripgrepy(params.pattern, params.path, rg_path=rg_path)

            if params.ignore_case:
                rg = rg.ignore_case()
            if params.multiline:
                rg = rg.multiline().multiline_dotall()
            if params.output_mode == "content":
                if params.before_context is not None:
                    rg = rg.before_context(params.before_context)
                if params.after_context is not None:
                    rg = rg.after_context(params.after_context)
                if params.context is not None:
                    rg = rg.context(params.context)
                if params.line_number:
                    rg = rg.line_number()
            if params.glob:
                rg = rg.glob(params.glob)
            if params.type:
                rg = rg.type_(params.type)
            if params.output_mode == "files_with_matches":
                rg = rg.files_with_matches()
            elif params.output_mode == "count_matches":
                rg = rg.count_matches()

            result = rg.run(universal_newlines=False)
            output = result.as_string

            if params.head_limit is not None:
                lines = output.split("\n")
                if len(lines) > params.head_limit:
                    lines = lines[: params.head_limit]
                    output = "\n".join(lines)
                    message = f"Results truncated to first {params.head_limit} lines"
                    output += f"\n... (results truncated to {params.head_limit} lines)"

            if not output:
                return builder.ok(message="No matches found")
            builder.write(output)
            return builder.ok(message=message)
        except Exception as e:
            return ToolError(
                message=f"Failed to grep. Error: {e!s}", brief="Failed to grep"
            )
