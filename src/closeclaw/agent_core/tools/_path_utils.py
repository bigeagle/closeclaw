"""Path safety utilities (forked from kimi_cli.utils.path)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath
from stat import S_ISDIR

from kaos.path import KaosPath


async def list_directory(work_dir: KaosPath) -> str:
    entries: list[str] = []
    async for entry in work_dir.iterdir():
        try:
            st = await entry.stat()
        except OSError:
            entries.append(f"?--------- {'?':>10} {entry.name} [stat failed]")
            continue
        mode = "d" if S_ISDIR(st.st_mode) else "-"
        mode += "r" if st.st_mode & 0o400 else "-"
        mode += "w" if st.st_mode & 0o200 else "-"
        mode += "x" if st.st_mode & 0o100 else "-"
        mode += "r" if st.st_mode & 0o040 else "-"
        mode += "w" if st.st_mode & 0o020 else "-"
        mode += "x" if st.st_mode & 0o010 else "-"
        mode += "r" if st.st_mode & 0o004 else "-"
        mode += "w" if st.st_mode & 0o002 else "-"
        mode += "x" if st.st_mode & 0o001 else "-"
        entries.append(f"{mode} {st.st_size:>10} {entry.name}")
    return "\n".join(entries)


def is_within_directory(path: KaosPath, directory: KaosPath) -> bool:
    candidate = PurePath(str(path))
    base = PurePath(str(directory))
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def is_within_workspace(
    path: KaosPath,
    work_dir: KaosPath,
    additional_dirs: Sequence[KaosPath] = (),
) -> bool:
    if is_within_directory(path, work_dir):
        return True
    return any(is_within_directory(path, d) for d in additional_dirs)
