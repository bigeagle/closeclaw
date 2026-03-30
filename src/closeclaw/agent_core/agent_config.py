"""Agent configuration model and loading."""

from __future__ import annotations

from pathlib import Path

import yaml
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
    """Read the system prompt file and apply template args."""
    if config_dir is None:
        config_dir = DEFAULT_AGENT_DIR
    prompt_path = config_dir / config.agent.system_prompt_path
    if not prompt_path.exists():
        return ""
    text = prompt_path.read_text()
    # Simple {KEY} replacement from system_prompt_args
    for key, value in config.agent.system_prompt_args.items():
        text = text.replace(f"{{{key}}}", value)
    return text.strip()
