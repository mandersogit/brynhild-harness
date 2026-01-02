"""
Tests for skill discovery.

Tests verify that:
- Skills are discovered from builtin, global, env, and project paths
- Later sources override earlier sources by name
- Invalid skills are skipped
"""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import brynhild.skills.discovery as discovery


class TestSkillSearchPaths:
    """Tests for get_skill_search_paths function."""

    def test_includes_builtin_path_first(self) -> None:
        """Builtin skills path is always included first (lowest priority)."""
        paths = discovery.get_skill_search_paths()
        assert paths[0] == discovery.get_builtin_skills_path()

    def test_includes_global_path_second(self) -> None:
        """Global skills path is included second."""
        paths = discovery.get_skill_search_paths()
        assert paths[1] == discovery.get_global_skills_path()

    def test_includes_project_path_last(self, tmp_path: _pathlib.Path) -> None:
        """Project-local path is included last (highest priority)."""
        paths = discovery.get_skill_search_paths(tmp_path)
        assert paths[-1] == discovery.get_project_skills_path(tmp_path)

    def test_includes_env_paths_in_middle(self, tmp_path: _pathlib.Path) -> None:
        """BRYNHILD_SKILL_PATH env var paths are included."""
        env_path1 = tmp_path / "env1"
        env_path2 = tmp_path / "env2"
        env_path1.mkdir()
        env_path2.mkdir()

        with _mock.patch.dict(_os.environ, {"BRYNHILD_SKILL_PATH": f"{env_path1}:{env_path2}"}):
            paths = discovery.get_skill_search_paths(tmp_path)

        assert paths[0] == discovery.get_builtin_skills_path()
        assert paths[1] == discovery.get_global_skills_path()
        assert env_path1.resolve() in paths
        assert env_path2.resolve() in paths
        assert paths[-1] == discovery.get_project_skills_path(tmp_path)

    def test_can_exclude_builtin(self) -> None:
        """Builtin skills can be excluded."""
        paths = discovery.get_skill_search_paths(include_builtin=False)
        assert discovery.get_builtin_skills_path() not in paths
        assert paths[0] == discovery.get_global_skills_path()


class TestSkillDiscovery:
    """Tests for SkillDiscovery class."""

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

    def test_discovers_skills_in_directory(self, tmp_path: _pathlib.Path) -> None:
        """Skills in search path are discovered."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        self._create_skill(skills_dir, "skill-a")
        self._create_skill(skills_dir, "skill-b")

        disc = discovery.SkillDiscovery(search_paths=[skills_dir])
        skills = disc.discover()

        assert len(skills) == 2
        assert "skill-a" in skills
        assert "skill-b" in skills

    def test_later_sources_override_earlier_by_name(self, tmp_path: _pathlib.Path) -> None:
        """Skill with same name from later source replaces earlier."""
        global_dir = tmp_path / "global"
        project_dir = tmp_path / "project"
        global_dir.mkdir()
        project_dir.mkdir()

        self._create_skill(global_dir, "shared-skill", "Global version")
        self._create_skill(project_dir, "shared-skill", "Project version")

        disc = discovery.SkillDiscovery(search_paths=[global_dir, project_dir])
        skills = disc.discover()

        assert len(skills) == 1
        assert skills["shared-skill"].description == "Project version"

    def test_skips_directories_without_skill_md(self, tmp_path: _pathlib.Path) -> None:
        """Directories without SKILL.md are skipped."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        self._create_skill(skills_dir, "valid-skill")

        # Create directory without SKILL.md
        (skills_dir / "not-a-skill").mkdir()
        (skills_dir / "not-a-skill" / "README.md").write_text("Not a skill")

        disc = discovery.SkillDiscovery(search_paths=[skills_dir])
        skills = disc.discover()

        assert len(skills) == 1
        assert "valid-skill" in skills

    def test_skips_invalid_skills(self, tmp_path: _pathlib.Path) -> None:
        """Skills with invalid SKILL.md are skipped."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        self._create_skill(skills_dir, "valid-skill")

        # Create skill with invalid SKILL.md
        bad_skill = skills_dir / "bad-skill"
        bad_skill.mkdir()
        (bad_skill / "SKILL.md").write_text("no frontmatter")

        disc = discovery.SkillDiscovery(search_paths=[skills_dir])
        skills = disc.discover()

        assert len(skills) == 1
        assert "valid-skill" in skills

    def test_discover_all_with_errors(self, tmp_path: _pathlib.Path) -> None:
        """discover_all with include_errors yields exceptions."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        self._create_skill(skills_dir, "valid-skill")

        bad_skill = skills_dir / "bad-skill"
        bad_skill.mkdir()
        (bad_skill / "SKILL.md").write_text("invalid")

        disc = discovery.SkillDiscovery(search_paths=[skills_dir])
        results = list(disc.discover_all(include_errors=True))

        assert len(results) == 2
        errors = [r for r in results if isinstance(r, tuple)]
        skills = [r for r in results if not isinstance(r, tuple)]

        assert len(errors) == 1
        assert len(skills) == 1


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_global_skills_path_is_in_config(self) -> None:
        """Global skills path is under ~/.config/brynhild/."""
        path = discovery.get_global_skills_path()
        assert path.parts[-3:] == (".config", "brynhild", "skills")

    def test_project_skills_path(self, tmp_path: _pathlib.Path) -> None:
        """Project skills path is under .brynhild/skills/."""
        path = discovery.get_project_skills_path(tmp_path)
        assert path == tmp_path / ".brynhild" / "skills"
