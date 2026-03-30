"""Lightweight runtime context for closeclaw tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kaos.path import KaosPath


@dataclass
class Runtime:
    """Minimal runtime providing workspace context to tools."""

    work_dir: KaosPath
    additional_dirs: list[KaosPath] = field(default_factory=list)
    skills_dirs: list[KaosPath] = field(default_factory=list)

    @staticmethod
    def from_cwd() -> Runtime:
        return Runtime(work_dir=KaosPath(str(Path.cwd())))
