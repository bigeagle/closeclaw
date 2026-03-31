"""SendImage tool — sends an image file to the user."""

from __future__ import annotations

import json
from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._file_utils import MEDIA_SNIFF_BYTES, detect_file_type
from closeclaw.agent_core.tools._path_utils import is_within_workspace
from closeclaw.agent_core.tools._utils import load_desc

MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB (Telegram limit for photos)


class Params(BaseModel):
    path: str = Field(
        description="The path to the image file to send. Supports JPEG, PNG, GIF, BMP, TIFF, and WebP formats."
    )
    caption: str = Field(
        default="",
        description="Optional caption for the image (Markdown supported).",
    )


class SendImage(CallableTool2[Params]):
    name: str = "SendImage"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        description = load_desc(Path(__file__).parent / "descs" / "send_image.md")
        super().__init__(description=description)
        self._work_dir = runtime.work_dir
        self._additional_dirs = runtime.additional_dirs

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if not params.path:
            return ToolError(
                message="File path cannot be empty.", brief="Empty file path"
            )
        try:
            p = KaosPath(params.path).expanduser()
            resolved = p.canonical()

            # Path safety check
            if (
                not is_within_workspace(resolved, self._work_dir, self._additional_dirs)
                and not p.is_absolute()
            ):
                return ToolError(
                    message=f"`{params.path}` is not an absolute path. You must provide an absolute path to send a file outside the working directory.",
                    brief="Invalid path",
                )

            if not await resolved.exists():
                return ToolError(
                    message=f"`{params.path}` does not exist.",
                    brief="File not found",
                )
            if not await resolved.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                    brief="Not a file",
                )

            # Verify it's an image
            header = await resolved.read_bytes(MEDIA_SNIFF_BYTES)
            file_type = detect_file_type(str(resolved), header=header)
            if file_type.kind != "image":
                return ToolError(
                    message=f"`{params.path}` is not a supported image file (detected: {file_type.kind}).",
                    brief="Not an image",
                )

            # Check file size
            stat = await resolved.stat()
            if stat.st_size > MAX_PHOTO_SIZE:
                size_mb = stat.st_size / (1024 * 1024)
                return ToolError(
                    message=f"`{params.path}` is too large ({size_mb:.1f} MB). Maximum photo size is 10 MB.",
                    brief="File too large",
                )

            result = json.dumps(
                {"path": str(resolved), "caption": params.caption},
                ensure_ascii=False,
            )
            return ToolOk(
                output=result,
                message=f"Image `{params.path}` queued for sending.",
                brief="Image sent",
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to process {params.path}. Error: {e}",
                brief="SendPhoto failed",
            )
