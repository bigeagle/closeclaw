"""Tests for closeclaw.agent_core.agent_config (skills & AGENTS.md)."""

from __future__ import annotations

from closeclaw.agent_core.agent_config import (
    AgentConfig,
    AgentSpec,
    _load_skills,
    load_system_prompt,
)


# ── _load_skills ──────────────────────────────────────────────────────────────


class TestLoadSkills:
    def test_no_skills_dir(self, tmp_path):
        assert _load_skills(tmp_path) == []

    def test_empty_skills_dir(self, tmp_path):
        (tmp_path / "skills").mkdir()
        assert _load_skills(tmp_path) == []

    def test_dir_without_skill_md(self, tmp_path):
        (tmp_path / "skills" / "foo").mkdir(parents=True)
        assert _load_skills(tmp_path) == []

    def test_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: my-skill\ndescription: A test skill.\n---\n# Content\n"
        )
        skills = _load_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].description == "A test skill."
        assert skills[0].skill_md_path == str(skill_md.resolve())

    def test_name_defaults_to_dir_name(self, tmp_path):
        skill_dir = tmp_path / "skills" / "fallback-name"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# No front matter\n")
        skills = _load_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "fallback-name"
        assert skills[0].description == ""

    def test_multiple_skills_sorted(self, tmp_path):
        for name in ["beta", "alpha"]:
            d = tmp_path / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Skill {name}.\n---\n"
            )
        skills = _load_skills(tmp_path)
        assert [s.name for s in skills] == ["alpha", "beta"]

    def test_non_dir_in_skills_ignored(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "readme.txt").write_text("not a skill")
        assert _load_skills(tmp_path) == []


# ── WORKSPACE_AGENTS_MD in prompt ─────────────────────────────────────────────


class TestWorkspaceAgentsMd:
    def _render(
        self, tmp_path, template_text, monkeypatch, *, agents_md=None, memory_md=None
    ):
        workspace = tmp_path / "ws"
        workspace.mkdir(exist_ok=True)
        if agents_md is not None:
            (workspace / "AGENTS.md").write_text(agents_md)
        if memory_md is not None:
            (workspace / "MEMORY.md").write_text(memory_md)
        monkeypatch.chdir(workspace)
        config_dir = tmp_path / "cfg"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "prompt.md").write_text(template_text)
        config = AgentConfig(agent=AgentSpec(system_prompt_path="prompt.md"))
        return load_system_prompt(config, config_dir)

    def test_agents_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ WORKSPACE_AGENTS_MD }}",
            monkeypatch,
            agents_md="Project guidelines here.",
        )
        assert result == "Project guidelines here."

    def test_agents_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ WORKSPACE_AGENTS_MD }}]", monkeypatch)
        assert result == "[]"

    def test_memory_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ AGENT_MEMORY_MD }}",
            monkeypatch,
            memory_md="User prefers dark mode.",
        )
        assert result == "User prefers dark mode."

    def test_memory_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ AGENT_MEMORY_MD }}]", monkeypatch)
        assert result == "[]"


# ── AGENT_SKILLS in prompt ────────────────────────────────────────────────────


class TestSkillsInPrompt:
    def test_skills_injected(self, tmp_path, monkeypatch):
        workspace = tmp_path / "ws"
        skill_dir = workspace / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: Does things.\n---\n"
        )
        monkeypatch.chdir(workspace)
        config_dir = tmp_path / "cfg"
        config_dir.mkdir()
        (config_dir / "prompt.md").write_text(
            "{% for s in AGENT_SKILLS %}{{ s.name }}:{{ s.description }}{% endfor %}"
        )
        config = AgentConfig(agent=AgentSpec(system_prompt_path="prompt.md"))
        result = load_system_prompt(config, config_dir)
        assert result == "test-skill:Does things."

    def test_no_skills(self, tmp_path, monkeypatch):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.chdir(workspace)
        config_dir = tmp_path / "cfg"
        config_dir.mkdir()
        (config_dir / "prompt.md").write_text("skills:{{ AGENT_SKILLS | length }}")
        config = AgentConfig(agent=AgentSpec(system_prompt_path="prompt.md"))
        result = load_system_prompt(config, config_dir)
        assert result == "skills:0"
