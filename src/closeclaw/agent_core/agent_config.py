"""Agent configuration model and loading."""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

import frontmatter
import yaml
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel


class AgentSpec(BaseModel):
    name: str = ""
    system_prompt_path: str = ""
    system_prompt_args: dict[str, str] = {}
    tools: list[str] = []


class AgentConfig(BaseModel):
    version: int = 1
    agent: AgentSpec = AgentSpec()


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_AGENT_DIR = Path(__file__).parent.parent / "default_agent"


# ── Skills ────────────────────────────────────────────────────────────────────


@dataclass
class SkillInfo:
    """Metadata for a loaded skill."""

    name: str
    description: str
    skill_md_path: str  # absolute path


def _load_skills(workspace: Path) -> list[SkillInfo]:
    """Scan ``<workspace>/skills/`` for valid skill directories."""
    skills_dir = workspace / "skills"
    if not skills_dir.is_dir():
        return []
    skills: list[SkillInfo] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        post = frontmatter.loads(skill_md.read_text())
        skills.append(
            SkillInfo(
                name=post.get("name", entry.name),
                description=post.get("description", ""),
                skill_md_path=str(skill_md.resolve()),
            )
        )
    return skills


# ── Loading ───────────────────────────────────────────────────────────────────


def load_agent_config(config_dir: Path | None = None) -> AgentConfig:
    """Load agent config from a directory containing ``agent.yaml``."""
    if config_dir is None:
        config_dir = DEFAULT_AGENT_DIR
    config_path = config_dir / "agent.yaml"
    if not config_path.exists():
        return AgentConfig()
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AgentConfig.model_validate(data)


def load_system_prompt(config: AgentConfig, config_dir: Path | None = None) -> str:
    """Read the system prompt file and render it as a Jinja2 template.

    Uses ``FileSystemLoader`` rooted at *config_dir* so that the template
    can use ``{% include %}`` and other Jinja2 directives.
    """
    if config_dir is None:
        config_dir = DEFAULT_AGENT_DIR
    prompt_path = config_dir / config.agent.system_prompt_path
    if not prompt_path.exists():
        return ""
    env = Environment(
        loader=FileSystemLoader(str(config_dir)),
        keep_trailing_newline=True,
    )
    template = env.get_template(config.agent.system_prompt_path)
    now = datetime.datetime.now(tz=datetime.timezone.utc).astimezone()
    workspace = Path(os.getcwd())

    def _read(name: str) -> str:
        p = workspace / name
        return p.read_text() if p.is_file() else ""

    builtin_args = {
        "AGENT_WORKING_DIR": str(workspace),
        "SESSION_START_TIME": now,
        "AGENT_IDENTITY": _read("IDENTITY.md"),
        "AGENT_SOUL": _read("SOUL.md"),
        "USER_PROFILE": _read("USER.md"),
        "WORKSPACE_AGENTS_MD": _read("AGENTS.md"),
        "AGENT_MEMORY_MD": _read("MEMORY.md"),
        "AGENT_SKILLS": _load_skills(workspace),
    }
    # User-defined args override builtins
    template_args = {**builtin_args, **config.agent.system_prompt_args}
    return template.render(**template_args).strip()
