"""ReadFile tool (forked from kimi_cli)."""

from __future__ import annotations

from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._file_utils import MEDIA_SNIFF_BYTES, detect_file_type
from closeclaw.agent_core.tools._path_utils import is_within_workspace
from closeclaw.agent_core.tools._utils import load_desc, truncate_line

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10


class Params(BaseModel):
    path: str = Field(
        description="The path to the file to read. Absolute paths are required when reading files outside the working directory."
    )
    line_offset: int = Field(
        description="The line number to start reading from. By default read from the beginning of the file. Set this when the file is too large to read at once.",
        default=1,
        ge=1,
    )
    n_lines: int = Field(
        description=f"The number of lines to read. By default read up to {MAX_LINES} lines, which is the max allowed value. Set this value when the file is too large to read at once.",
        default=MAX_LINES,
        ge=1,
    )


class ReadFile(CallableTool2[Params]):
    name: str = "ReadFile"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        description = load_desc(
            Path(__file__).parent / "descs" / "read.md",
            {
                "MAX_LINES": MAX_LINES,
                "MAX_LINE_LENGTH": MAX_LINE_LENGTH,
                "MAX_BYTES": MAX_BYTES,
            },
        )
        super().__init__(description=description)
        self._work_dir = runtime.work_dir
        self._additional_dirs = runtime.additional_dirs

    async def _validate_path(self, path: KaosPath) -> ToolError | None:
        resolved_path = path.canonical()
        if (
            not is_within_workspace(
                resolved_path, self._work_dir, self._additional_dirs
            )
            and not path.is_absolute()
        ):
            return ToolError(
                message=f"`{path}` is not an absolute path. You must provide an absolute path to read a file outside the working directory.",
                brief="Invalid path",
            )
        return None

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if not params.path:
            return ToolError(
                message="File path cannot be empty.", brief="Empty file path"
            )
        try:
            p = KaosPath(params.path).expanduser()
            if err := await self._validate_path(p):
                return err
            p = p.canonical()
            if not await p.exists():
                return ToolError(
                    message=f"`{params.path}` does not exist.", brief="File not found"
                )
            if not await p.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.", brief="Invalid path"
                )
            header = await p.read_bytes(MEDIA_SNIFF_BYTES)
            file_type = detect_file_type(str(p), header=header)
            if file_type.kind in ("image", "video"):
                return ToolError(
                    message=f"`{params.path}` is a {file_type.kind} file. Use other appropriate tools to read image or video files.",
                    brief="Unsupported file type",
                )
            if file_type.kind == "unknown":
                return ToolError(
                    message=f"`{params.path}` seems not readable. You may need to read it with proper shell commands.",
                    brief="File not readable",
                )

            lines: list[str] = []
            n_bytes = 0
            truncated_line_numbers: list[int] = []
            max_lines_reached = False
            max_bytes_reached = False
            current_line_no = 0
            async for line in p.read_lines(errors="replace"):
                current_line_no += 1
                if current_line_no < params.line_offset:
                    continue
                truncated = truncate_line(line, MAX_LINE_LENGTH)
                if truncated != line:
                    truncated_line_numbers.append(current_line_no)
                lines.append(truncated)
                n_bytes += len(truncated.encode("utf-8"))
                if len(lines) >= params.n_lines:
                    break
                if len(lines) >= MAX_LINES:
                    max_lines_reached = True
                    break
                if n_bytes >= MAX_BYTES:
                    max_bytes_reached = True
                    break

            lines_with_no: list[str] = []
            for line_num, line in zip(
                range(params.line_offset, params.line_offset + len(lines)),
                lines,
                strict=True,
            ):
                lines_with_no.append(f"{line_num:6d}\t{line}")

            message = (
                f"{len(lines)} lines read from file starting from line {params.line_offset}."
                if len(lines) > 0
                else "No lines read from file."
            )
            if max_lines_reached:
                message += f" Max {MAX_LINES} lines reached."
            elif max_bytes_reached:
                message += f" Max {MAX_BYTES} bytes reached."
            elif len(lines) < params.n_lines:
                message += " End of file reached."
            if truncated_line_numbers:
                message += f" Lines {truncated_line_numbers} were truncated."
            return ToolOk(output="".join(lines_with_no), message=message)
        except Exception as e:
            return ToolError(
                message=f"Failed to read {params.path}. Error: {e}",
                brief="Failed to read file",
            )
