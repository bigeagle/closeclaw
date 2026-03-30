"""StrReplaceFile tool (forked from kimi_cli, simplified)."""

from __future__ import annotations

from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolReturnValue, ToolOk
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._path_utils import is_within_workspace
from closeclaw.agent_core.tools._utils import load_desc

_DESCRIPTION = load_desc(Path(__file__).parent / "descs" / "replace.md")


class Edit(BaseModel):
    old: str = Field(description="The old string to replace. Can be multi-line.")
    new: str = Field(description="The new string to replace with. Can be multi-line.")
    replace_all: bool = Field(
        description="Whether to replace all occurrences.", default=False
    )


class Params(BaseModel):
    path: str = Field(
        description="The path to the file to edit. Absolute paths are required when editing files outside the working directory."
    )
    edit: Edit | list[Edit] = Field(
        description="The edit(s) to apply to the file. You can provide a single edit or a list of edits here."
    )


class StrReplaceFile(CallableTool2[Params]):
    name: str = "StrReplaceFile"
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
                message=f"`{path}` is not an absolute path. You must provide an absolute path to edit a file outside the working directory.",
                brief="Invalid path",
            )
        return None

    @staticmethod
    def _apply_edit(content: str, edit: Edit) -> str:
        if edit.replace_all:
            return content.replace(edit.old, edit.new)
        return content.replace(edit.old, edit.new, 1)

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

            content = await p.read_text(errors="replace")
            original_content = content
            edits = [params.edit] if isinstance(params.edit, Edit) else params.edit
            for edit in edits:
                content = StrReplaceFile._apply_edit(content, edit)
            if content == original_content:
                return ToolError(
                    message="No replacements were made. The old string was not found in the file.",
                    brief="No replacements made",
                )

            await p.write_text(content, errors="replace")
            total_replacements = 0
            for edit in edits:
                if edit.replace_all:
                    total_replacements += original_content.count(edit.old)
                else:
                    total_replacements += 1 if edit.old in original_content else 0
            return ToolOk(
                output="",
                message=f"File successfully edited. Applied {len(edits)} edit(s) with {total_replacements} total replacement(s).",
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to edit. Error: {e}", brief="Failed to edit file"
            )
