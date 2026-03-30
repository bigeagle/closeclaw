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


class TestWorkspaceFiles:
    def _render(self, tmp_path, template_text, monkeypatch, **files):
        workspace = tmp_path / "ws"
        workspace.mkdir(exist_ok=True)
        for name, content in files.items():
            (workspace / name).write_text(content)
        monkeypatch.chdir(workspace)
        config_dir = tmp_path / "cfg"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "prompt.md").write_text(template_text)
        config = AgentConfig(agent=AgentSpec(system_prompt_path="prompt.md"))
        return load_system_prompt(config, config_dir)

    # AGENTS.md

    def test_agents_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ WORKSPACE_AGENTS_MD }}",
            monkeypatch,
            **{"AGENTS.md": "Project guidelines here."},
        )
        assert result == "Project guidelines here."

    def test_agents_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ WORKSPACE_AGENTS_MD }}]", monkeypatch)
        assert result == "[]"

    # MEMORY.md

    def test_memory_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ AGENT_MEMORY_MD }}",
            monkeypatch,
            **{"MEMORY.md": "User prefers dark mode."},
        )
        assert result == "User prefers dark mode."

    def test_memory_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ AGENT_MEMORY_MD }}]", monkeypatch)
        assert result == "[]"

    # IDENTITY.md

    def test_identity_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ AGENT_IDENTITY }}",
            monkeypatch,
            **{"IDENTITY.md": "I am CloseClaw."},
        )
        assert result == "I am CloseClaw."

    def test_identity_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ AGENT_IDENTITY }}]", monkeypatch)
        assert result == "[]"

    # SOUL.md

    def test_soul_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ AGENT_SOUL }}",
            monkeypatch,
            **{"SOUL.md": "Be kind and helpful."},
        )
        assert result == "Be kind and helpful."

    def test_soul_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ AGENT_SOUL }}]", monkeypatch)
        assert result == "[]"

    # USER.md

    def test_user_md_loaded(self, tmp_path, monkeypatch):
        result = self._render(
            tmp_path,
            "{{ USER_PROFILE }}",
            monkeypatch,
            **{"USER.md": "Name: Alice. Loves Python."},
        )
        assert result == "Name: Alice. Loves Python."

    def test_user_md_missing(self, tmp_path, monkeypatch):
        result = self._render(tmp_path, "[{{ USER_PROFILE }}]", monkeypatch)
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
