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
