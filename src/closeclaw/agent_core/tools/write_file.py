"""WriteFile tool (forked from kimi_cli, simplified)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolReturnValue, ToolOk
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._path_utils import is_within_workspace
from closeclaw.agent_core.tools._utils import load_desc

_DESCRIPTION = load_desc(Path(__file__).parent / "descs" / "write.md")


class Params(BaseModel):
    path: str = Field(
        description="The path to the file to write. Absolute paths are required when writing files outside the working directory."
    )
    content: str = Field(description="The content to write to the file")
    mode: Literal["overwrite", "append"] = Field(
        description="The mode to use to write to the file. Two modes are supported: `overwrite` for overwriting the whole file and `append` for appending to the end of an existing file.",
        default="overwrite",
    )


class WriteFile(CallableTool2[Params]):
    name: str = "WriteFile"
    description: str = _DESCRIPTION
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
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
                message=f"`{path}` is not an absolute path. You must provide an absolute path to write a file outside the working directory.",
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
            if not await p.parent.exists():
                return ToolError(
                    message=f"`{params.path}` parent directory does not exist.",
                    brief="Parent directory not found",
                )

            match params.mode:
                case "overwrite":
                    await p.write_text(params.content)
                case "append":
                    await p.append_text(params.content)

            file_size = (await p.stat()).st_size
            action = "overwritten" if params.mode == "overwrite" else "appended to"
            return ToolOk(
                output="",
                message=f"File successfully {action}. Current size: {file_size} bytes.",
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to write to {params.path}. Error: {e}",
                brief="Failed to write file",
            )
