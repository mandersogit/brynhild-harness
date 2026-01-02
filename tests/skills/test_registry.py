"""
Tests for skill registry.

Tests verify that:
- Registry discovers and lists skills
- Progressive loading interface works
- Skill matching finds relevant skills
"""

import pathlib as _pathlib

import brynhild.skills.registry as registry


class TestSkillRegistry:
    """Tests for SkillRegistry class."""

    def _create_skill(
        self,
        parent: _pathlib.Path,
        name: str,
        description: str = "Test skill",
    ) -> _pathlib.Path:
        """Helper to create a minimal skill directory."""
        skill_dir = parent / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: {description}
---

# {name}

Instructions for {name}.
""")
        return skill_dir

    def test_lists_discovered_skills(self, tmp_path: _pathlib.Path) -> None:
        """list_skills returns all discovered skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "skill-a")
        self._create_skill(skills_dir, "skill-b")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None  # Force rediscovery

        skills = reg.list_skills()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"skill-a", "skill-b"}

    def test_get_skill_by_name(self, tmp_path: _pathlib.Path) -> None:
        """get_skill returns specific skill."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "debugging", "Debug things")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        skill = reg.get_skill("debugging")
        assert skill is not None
        assert skill.name == "debugging"
        assert skill.description == "Debug things"

    def test_has_skill_returns_true_for_existing(self, tmp_path: _pathlib.Path) -> None:
        """has_skill returns True for existing skill."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "test-skill")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        assert reg.has_skill("test-skill") is True
        assert reg.has_skill("nonexistent") is False

    def test_get_metadata_for_prompt(self, tmp_path: _pathlib.Path) -> None:
        """get_metadata_for_prompt returns formatted metadata."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "debugging", "Debug systematically")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        meta = reg.get_metadata_for_prompt()
        assert "## Available Skills" in meta
        assert "**debugging**" in meta

    def test_trigger_skill_returns_wrapped_content(self, tmp_path: _pathlib.Path) -> None:
        """trigger_skill returns body wrapped in tags."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "debugging")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        result = reg.trigger_skill("debugging")
        assert result is not None
        assert '<skill name="debugging">' in result
        assert "Instructions for debugging" in result

    def test_get_reference_file(self, tmp_path: _pathlib.Path) -> None:
        """get_reference_file loads file from skill directory."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: Test skill
---
Body
""")
        (skill_dir / "examples.md").write_text("Example content")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        content = reg.get_reference_file("test-skill", "examples.md")
        assert content == "Example content"

    def test_find_matching_skills_by_name(self, tmp_path: _pathlib.Path) -> None:
        """find_matching_skills finds skills by name in input."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "debugging", "Debug things")
        self._create_skill(skills_dir, "testing", "Test things")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        matches = reg.find_matching_skills("I need help debugging this issue")
        assert len(matches) >= 1
        assert any(s.name == "debugging" for s in matches)

    def test_find_matching_skills_by_description(self, tmp_path: _pathlib.Path) -> None:
        """find_matching_skills finds skills by description keywords."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "systematic-debugging", "Use when encountering failures")
        self._create_skill(skills_dir, "tdd", "Test driven development")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        # "failures" appears in description and in user input
        matches = reg.find_matching_skills("I have some failures in my tests")
        assert len(matches) >= 1
        assert any(s.name == "systematic-debugging" for s in matches)

    def test_find_matching_skills_max_results(self, tmp_path: _pathlib.Path) -> None:
        """find_matching_skills respects max_results."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for i in range(5):
            self._create_skill(skills_dir, f"skill-{i}", f"Test skill {i}")

        reg = registry.SkillRegistry()
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        matches = reg.find_matching_skills("test skill", max_results=2)
        assert len(matches) <= 2

    def test_to_dict_includes_all_info(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes project_root and skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._create_skill(skills_dir, "test-skill")

        reg = registry.SkillRegistry(project_root=tmp_path)
        reg._discovery._search_paths = [skills_dir]
        reg._skills = None

        d = reg.to_dict()
        assert d["project_root"] == str(tmp_path)
        assert d["skill_count"] == 1
        assert len(d["skills"]) == 1
