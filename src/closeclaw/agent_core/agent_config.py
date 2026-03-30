"""Agent configuration model and loading."""

from __future__ import annotations

import datetime
import os
from pathlib import Path

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
    builtin_args = {
        "AGENT_WORKING_DIR": os.getcwd(),
        "SESSION_START_TIME": now,
    }
    # User-defined args override builtins
    template_args = {**builtin_args, **config.agent.system_prompt_args}
    return template.render(**template_args).strip()
