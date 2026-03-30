"""Tool utility functions (forked from kimi_cli.tools.utils)."""

import re
from pathlib import Path

from jinja2 import Environment, Undefined
from kosong.tooling import BriefDisplayBlock, DisplayBlock, ToolReturnValue
from kosong.utils.typing import JsonType


class _KeepPlaceholderUndefined(Undefined):
    def __str__(self) -> str:
        if self._undefined_name is None:
            return ""
        return f"${{{self._undefined_name}}}"

    __repr__ = __str__


def load_desc(path: Path, context: dict[str, object] | None = None) -> str:
    """Load a tool description from a file, rendered via Jinja2."""
    description = path.read_text(encoding="utf-8")
    env = Environment(
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
        variable_start_string="${",
        variable_end_string="}",
        undefined=_KeepPlaceholderUndefined,
    )
    template = env.from_string(description)
    return template.render(context or {})


def truncate_line(line: str, max_length: int, marker: str = "...") -> str:
    if len(line) <= max_length:
        return line
    m = re.search(r"[\r\n]+$", line)
    linebreak = m.group(0) if m else ""
    end = marker + linebreak
    max_length = max(max_length, len(end))
    return line[: max_length - len(end)] + end


DEFAULT_MAX_CHARS = 50_000
DEFAULT_MAX_LINE_LENGTH = 2000


class ToolResultBuilder:
    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_line_length: int | None = DEFAULT_MAX_LINE_LENGTH,
    ):
        self.max_chars = max_chars
        self.max_line_length = max_line_length
        self._marker = "[...truncated]"
        if max_line_length is not None:
            assert max_line_length > len(self._marker)
        self._buffer: list[str] = []
        self._n_chars = 0
        self._n_lines = 0
        self._truncation_happened = False
        self._display: list[DisplayBlock] = []
        self._extras: dict[str, JsonType] | None = None

    @property
    def is_full(self) -> bool:
        return self._n_chars >= self.max_chars

    def write(self, text: str) -> int:
        if self.is_full:
            return 0
        lines = text.splitlines(keepends=True)
        if not lines:
            return 0
        chars_written = 0
        for line in lines:
            if self.is_full:
                break
            original_line = line
            remaining_chars = self.max_chars - self._n_chars
            limit = (
                min(remaining_chars, self.max_line_length)
                if self.max_line_length is not None
                else remaining_chars
            )
            line = truncate_line(line, limit, self._marker)
            if line != original_line:
                self._truncation_happened = True
            self._buffer.append(line)
            chars_written += len(line)
            self._n_chars += len(line)
            if line.endswith("\n"):
                self._n_lines += 1
        return chars_written

    def display(self, *blocks: DisplayBlock) -> None:
        self._display.extend(blocks)

    def ok(self, message: str = "", *, brief: str = "") -> ToolReturnValue:
        output = "".join(self._buffer)
        final_message = message
        if final_message and not final_message.endswith("."):
            final_message += "."
        truncation_msg = "Output is truncated to fit in the message."
        if self._truncation_happened:
            if final_message:
                final_message += f" {truncation_msg}"
            else:
                final_message = truncation_msg
        return ToolReturnValue(
            is_error=False,
            output=output,
            message=final_message,
            display=([BriefDisplayBlock(text=brief)] if brief else []) + self._display,
            extras=self._extras,
        )

    def error(self, message: str, *, brief: str) -> ToolReturnValue:
        output = "".join(self._buffer)
        final_message = message
        if self._truncation_happened:
            truncation_msg = "Output is truncated to fit in the message."
            if final_message:
                final_message += f" {truncation_msg}"
            else:
                final_message = truncation_msg
        return ToolReturnValue(
            is_error=True,
            output=output,
            message=final_message,
            display=([BriefDisplayBlock(text=brief)] if brief else []) + self._display,
            extras=self._extras,
        )
