"""ReadMediaFile tool (forked from kimi_cli)."""

from __future__ import annotations

import base64
from html import escape
from io import BytesIO
from pathlib import Path
from typing import override

from kaos.path import KaosPath
from kosong.message import ContentPart, ImageURLPart, TextPart
from kosong.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from closeclaw.agent_core.runtime import Runtime
from closeclaw.agent_core.tools._file_utils import (
    MEDIA_SNIFF_BYTES,
    FileType,
    detect_file_type,
)
from closeclaw.agent_core.tools._path_utils import is_within_workspace
from closeclaw.agent_core.tools._utils import load_desc

MAX_MEDIA_MEGABYTES = 100


def _to_data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_image_size(data: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.size
    except Exception:
        return None


def _wrap_media_part(
    part: ContentPart,
    *,
    tag: str,
    attrs: dict[str, str | None] | None = None,
) -> list[ContentPart]:
    """Wrap a media ContentPart with XML open/close tags."""
    if attrs:
        rendered = [
            f'{k}="{escape(str(v), quote=True)}"' for k, v in sorted(attrs.items()) if v
        ]
        open_tag = f"<{tag} " + " ".join(rendered) + ">" if rendered else f"<{tag}>"
    else:
        open_tag = f"<{tag}>"
    return [
        TextPart(text=open_tag),
        part,
        TextPart(text=f"</{tag}>"),
    ]


class Params(BaseModel):
    path: str = Field(
        description=(
            "The path to the file to read. Absolute paths are required "
            "when reading files outside the working directory."
        )
    )


class ReadMediaFile(CallableTool2[Params]):
    name: str = "ReadMediaFile"
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        if not runtime.enable_vision:
            raise RuntimeError("ReadMediaFile requires enable_vision=true")
        description = load_desc(
            Path(__file__).parent / "descs" / "read_media.md",
            {"MAX_MEDIA_MEGABYTES": MAX_MEDIA_MEGABYTES},
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
                message=(
                    f"`{path}` is not an absolute path. "
                    "You must provide an absolute path to read a file "
                    "outside the working directory."
                ),
                brief="Invalid path",
            )
        return None

    async def _read_media(self, path: KaosPath, file_type: FileType) -> ToolReturnValue:
        assert file_type.kind == "image"

        media_path = str(path)
        stat = await path.stat()
        size = stat.st_size
        if size == 0:
            return ToolError(message=f"`{path}` is empty.", brief="Empty file")
        if size > (MAX_MEDIA_MEGABYTES << 20):
            return ToolError(
                message=(
                    f"`{path}` is {size} bytes, which exceeds the max "
                    f"{MAX_MEDIA_MEGABYTES}MB for media files."
                ),
                brief="File too large",
            )

        data = await path.read_bytes()
        data_url = _to_data_url(file_type.mime_type, data)
        part = ImageURLPart(image_url=ImageURLPart.ImageURL(url=data_url))
        wrapped = _wrap_media_part(part, tag="image", attrs={"path": media_path})
        image_size = _extract_image_size(data)

        size_hint = ""
        if image_size:
            size_hint = f", original size {image_size[0]}x{image_size[1]}px"
        note = (
            " If you need to output coordinates, output relative coordinates "
            "first and compute absolute coordinates using the original image "
            "size; if you generate or edit images via commands or scripts, "
            "read the result back immediately before continuing."
        )
        return ToolOk(
            output=wrapped,
            message=(
                f"Loaded {file_type.kind} file `{path}` "
                f"({file_type.mime_type}, {size} bytes{size_hint}).{note}"
            ),
        )

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
                    message=f"`{params.path}` does not exist.",
                    brief="File not found",
                )
            if not await p.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                    brief="Invalid path",
                )

            header = await p.read_bytes(MEDIA_SNIFF_BYTES)
            file_type = detect_file_type(str(p), header=header)

            if file_type.kind == "text":
                return ToolError(
                    message=f"`{params.path}` is a text file. Use ReadFile to read text files.",
                    brief="Unsupported file type",
                )
            if file_type.kind == "unknown":
                return ToolError(
                    message=(
                        f"`{params.path}` seems not readable as an image file. "
                        "You may need to read it with proper shell commands."
                    ),
                    brief="File not readable",
                )
            if file_type.kind == "video":
                return ToolError(
                    message="Video input is not supported.",
                    brief="Unsupported media type",
                )
            if file_type.kind != "image":
                return ToolError(
                    message=f"`{params.path}` is not a supported media file.",
                    brief="Unsupported file type",
                )

            return await self._read_media(p, file_type)
        except Exception as e:
            return ToolError(
                message=f"Failed to read {params.path}. Error: {e}",
                brief="Failed to read file",
            )
