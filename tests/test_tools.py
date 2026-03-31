"""Tests for forked tools: ReadFile, WriteFile, Glob, Grep, StrReplaceFile."""

from __future__ import annotations

import pytest

from kaos.path import KaosPath
from closeclaw.agent_core.runtime import Runtime

from closeclaw.agent_core.tools.read_file import ReadFile, Params as ReadParams
from closeclaw.agent_core.tools.write_file import WriteFile, Params as WriteParams
from closeclaw.agent_core.tools.glob_tool import Glob, Params as GlobParams
from closeclaw.agent_core.tools.grep import Grep, Params as GrepParams
from closeclaw.agent_core.tools.replace_file import (
    StrReplaceFile,
    Params as ReplaceParams,
    Edit,
)
from closeclaw.agent_core.tools.send_image import (
    SendImage,
    Params as SendImageParams,
    MAX_PHOTO_SIZE,
)
from closeclaw.agent_core.tools.read_media import (
    ReadMediaFile,
    Params as ReadMediaParams,
)


@pytest.fixture
def runtime(tmp_path):
    resolved = tmp_path.resolve()
    return Runtime(work_dir=KaosPath(str(resolved)))


# ---------------------------------------------------------------------------
# ReadFile
# ---------------------------------------------------------------------------


class TestReadFile:
    async def test_read_existing_file(self, runtime, tmp_path):
        f = tmp_path.resolve() / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadFile(runtime)
        result = await tool(ReadParams(path=str(f)))
        assert not result.is_error
        # Output should contain line numbers
        assert "1\tline1" in result.output
        assert "2\tline2" in result.output
        assert "3\tline3" in result.output

    async def test_read_nonexistent(self, runtime, tmp_path):
        tool = ReadFile(runtime)
        missing = str(tmp_path.resolve() / "no_such_file.txt")
        result = await tool(ReadParams(path=missing))
        assert result.is_error

    async def test_read_with_offset(self, runtime, tmp_path):
        f = tmp_path.resolve() / "offset.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = ReadFile(runtime)
        result = await tool(ReadParams(path=str(f), line_offset=3))
        assert not result.is_error
        # Should start from line 3 ("c")
        assert "3\tc" in result.output
        # Lines before offset should not appear
        assert "1\ta" not in result.output
        assert "2\tb" not in result.output

    async def test_read_n_lines(self, runtime, tmp_path):
        f = tmp_path.resolve() / "nlines.txt"
        f.write_text("1\n2\n3\n4\n5\n")
        tool = ReadFile(runtime)
        result = await tool(ReadParams(path=str(f), n_lines=2))
        assert not result.is_error
        # Should only have 2 lines
        lines = [line for line in result.output.splitlines() if line.strip()]
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# WriteFile
# ---------------------------------------------------------------------------


class TestWriteFile:
    async def test_write_new_file(self, runtime, tmp_path):
        target = tmp_path.resolve() / "new.txt"
        tool = WriteFile(runtime)
        result = await tool(WriteParams(path=str(target), content="hello world"))
        assert not result.is_error
        assert target.read_text() == "hello world"

    async def test_write_overwrite(self, runtime, tmp_path):
        target = tmp_path.resolve() / "over.txt"
        target.write_text("old content")
        tool = WriteFile(runtime)
        result = await tool(WriteParams(path=str(target), content="new content"))
        assert not result.is_error
        assert target.read_text() == "new content"

    async def test_write_append(self, runtime, tmp_path):
        target = tmp_path.resolve() / "append.txt"
        target.write_text("first\n")
        tool = WriteFile(runtime)
        result = await tool(
            WriteParams(path=str(target), content="second\n", mode="append")
        )
        assert not result.is_error
        assert target.read_text() == "first\nsecond\n"

    async def test_write_missing_parent(self, runtime, tmp_path):
        target = tmp_path.resolve() / "no_parent" / "file.txt"
        tool = WriteFile(runtime)
        result = await tool(WriteParams(path=str(target), content="data"))
        assert result.is_error


# ---------------------------------------------------------------------------
# Glob
# ---------------------------------------------------------------------------


class TestGlob:
    async def test_glob_py_files(self, runtime, tmp_path):
        resolved = tmp_path.resolve()
        (resolved / "a.py").write_text("")
        (resolved / "b.py").write_text("")
        (resolved / "c.txt").write_text("")
        tool = Glob(runtime)
        result = await tool(GlobParams(pattern="*.py", directory=str(resolved)))
        assert not result.is_error
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    async def test_glob_no_matches(self, runtime, tmp_path):
        resolved = tmp_path.resolve()
        (resolved / "a.txt").write_text("")
        tool = Glob(runtime)
        result = await tool(GlobParams(pattern="*.rs", directory=str(resolved)))
        assert not result.is_error
        assert result.output == ""

    async def test_glob_rejects_double_star_prefix(self, runtime):
        tool = Glob(runtime)
        result = await tool(GlobParams(pattern="**/*.py"))
        assert result.is_error


# ---------------------------------------------------------------------------
# Grep
# ---------------------------------------------------------------------------


class TestGrep:
    async def test_grep_finds_match(self, tmp_path):
        resolved = tmp_path.resolve()
        f = resolved / "search.txt"
        f.write_text("apple\nbanana\ncherry\n")
        tool = Grep()
        result = await tool(GrepParams(pattern="banana", path=str(resolved)))
        assert not result.is_error
        assert "search.txt" in result.output

    async def test_grep_no_match(self, tmp_path):
        resolved = tmp_path.resolve()
        f = resolved / "search2.txt"
        f.write_text("apple\nbanana\ncherry\n")
        tool = Grep()
        result = await tool(GrepParams(pattern="dragonfruit", path=str(resolved)))
        assert "No matches found" in result.message


# ---------------------------------------------------------------------------
# StrReplaceFile
# ---------------------------------------------------------------------------


class TestStrReplaceFile:
    async def test_replace_single(self, runtime, tmp_path):
        f = tmp_path.resolve() / "replace.txt"
        f.write_text("hello world")
        tool = StrReplaceFile(runtime)
        result = await tool(
            ReplaceParams(
                path=str(f),
                edit=Edit(old="world", new="earth"),
            )
        )
        assert not result.is_error
        assert f.read_text() == "hello earth"

    async def test_replace_not_found(self, runtime, tmp_path):
        f = tmp_path.resolve() / "noreplace.txt"
        f.write_text("hello world")
        tool = StrReplaceFile(runtime)
        result = await tool(
            ReplaceParams(
                path=str(f),
                edit=Edit(old="missing", new="replaced"),
            )
        )
        assert result.is_error

    async def test_replace_all(self, runtime, tmp_path):
        f = tmp_path.resolve() / "replaceall.txt"
        f.write_text("aaa bbb aaa ccc aaa")
        tool = StrReplaceFile(runtime)
        result = await tool(
            ReplaceParams(
                path=str(f),
                edit=Edit(old="aaa", new="xxx", replace_all=True),
            )
        )
        assert not result.is_error
        assert f.read_text() == "xxx bbb xxx ccc xxx"

    async def test_replace_multiple_edits(self, runtime, tmp_path):
        f = tmp_path.resolve() / "multi.txt"
        f.write_text("foo bar baz")
        tool = StrReplaceFile(runtime)
        result = await tool(
            ReplaceParams(
                path=str(f),
                edit=[
                    Edit(old="foo", new="FOO"),
                    Edit(old="baz", new="BAZ"),
                ],
            )
        )
        assert not result.is_error
        assert f.read_text() == "FOO bar BAZ"


# ---------------------------------------------------------------------------
# SendPhoto
# ---------------------------------------------------------------------------

# Minimal valid PNG: magic header + minimal IHDR chunk
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature
    b"\x00\x00\x00\rIHDR"  # IHDR chunk
    b"\x00\x00\x00\x01"  # width: 1
    b"\x00\x00\x00\x01"  # height: 1
    b"\x08\x02"  # bit depth: 8, color type: RGB
    b"\x00\x00\x00"  # compression, filter, interlace
    b"\x90wS\xde"  # CRC
)


class TestSendImage:
    async def test_send_valid_image(self, runtime, tmp_path):
        f = tmp_path.resolve() / "image.png"
        f.write_bytes(_MINIMAL_PNG)
        tool = SendImage(runtime)
        result = await tool(SendImageParams(path=str(f)))
        assert not result.is_error
        import json

        data = json.loads(result.output)
        assert data["path"] == str(f)
        assert data["caption"] == ""

    async def test_send_with_caption(self, runtime, tmp_path):
        f = tmp_path.resolve() / "image.png"
        f.write_bytes(_MINIMAL_PNG)
        tool = SendImage(runtime)
        result = await tool(SendImageParams(path=str(f), caption="Hello!"))
        assert not result.is_error
        import json

        data = json.loads(result.output)
        assert data["caption"] == "Hello!"

    async def test_nonexistent_file(self, runtime, tmp_path):
        tool = SendImage(runtime)
        missing = str(tmp_path.resolve() / "no_such.png")
        result = await tool(SendImageParams(path=missing))
        assert result.is_error

    async def test_not_an_image(self, runtime, tmp_path):
        f = tmp_path.resolve() / "text.txt"
        f.write_text("this is plain text")
        tool = SendImage(runtime)
        result = await tool(SendImageParams(path=str(f)))
        assert result.is_error
        assert "not a supported image" in result.message

    async def test_file_too_large(self, runtime, tmp_path):
        f = tmp_path.resolve() / "big.png"
        # Write PNG header + padding to exceed 10MB
        f.write_bytes(_MINIMAL_PNG + b"\x00" * (MAX_PHOTO_SIZE + 1))
        tool = SendImage(runtime)
        result = await tool(SendImageParams(path=str(f)))
        assert result.is_error
        assert "too large" in result.message

    async def test_empty_path(self, runtime):
        tool = SendImage(runtime)
        result = await tool(SendImageParams(path=""))
        assert result.is_error


# ---------------------------------------------------------------------------
# ReadMediaFile
# ---------------------------------------------------------------------------


class TestReadMediaFile:
    async def test_read_valid_image(self, runtime, tmp_path):
        f = tmp_path.resolve() / "image.png"
        f.write_bytes(_MINIMAL_PNG)
        tool = ReadMediaFile(runtime)
        result = await tool(ReadMediaParams(path=str(f)))
        assert not result.is_error
        # Output should be a list of ContentPart with image tag wrapper
        assert isinstance(result.output, list)
        assert len(result.output) == 3  # TextPart, ImageURLPart, TextPart
        assert "image/png" in result.message

    async def test_read_nonexistent(self, runtime, tmp_path):
        tool = ReadMediaFile(runtime)
        missing = str(tmp_path.resolve() / "no_such.png")
        result = await tool(ReadMediaParams(path=missing))
        assert result.is_error

    async def test_read_text_file_rejected(self, runtime, tmp_path):
        f = tmp_path.resolve() / "readme.txt"
        f.write_text("plain text content")
        tool = ReadMediaFile(runtime)
        result = await tool(ReadMediaParams(path=str(f)))
        assert result.is_error
        assert "text file" in result.message

    async def test_empty_path(self, runtime):
        tool = ReadMediaFile(runtime)
        result = await tool(ReadMediaParams(path=""))
        assert result.is_error
