"""
Tests for skill loader.

Tests verify that:
- Progressive loading works correctly
- Metadata, body, and reference files load properly
- Caching works
"""

import pathlib as _pathlib

import brynhild.skills.loader as loader
import brynhild.skills.skill as skill


class TestSkillLoader:
    """Tests for SkillLoader class."""

    def _make_skill(
        self,
        tmp_path: _pathlib.Path,
        name: str,
        description: str = "Test skill",
        body: str = "Instructions",
    ) -> skill.Skill:
        """Helper to create a Skill."""
        skill_dir = tmp_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        fm = skill.SkillFrontmatter(name=name, description=description)
        return skill.Skill(
            frontmatter=fm,
            body=body,
            path=skill_dir,
            source="project",
        )

    def test_get_skill_returns_skill(self, tmp_path: _pathlib.Path) -> None:
        """get_skill returns skill by name."""
        s = self._make_skill(tmp_path, "test-skill")
        ldr = loader.SkillLoader({"test-skill": s})

        result = ldr.get_skill("test-skill")
        assert result is s

    def test_get_skill_returns_none_for_unknown(self) -> None:
        """get_skill returns None for unknown name."""
        ldr = loader.SkillLoader({})
        assert ldr.get_skill("nonexistent") is None

    def test_list_skills_returns_all(self, tmp_path: _pathlib.Path) -> None:
        """list_skills returns all skills."""
        s1 = self._make_skill(tmp_path, "skill-a")
        s2 = self._make_skill(tmp_path, "skill-b")
        ldr = loader.SkillLoader({"skill-a": s1, "skill-b": s2})

        result = ldr.list_skills()
        assert len(result) == 2

    def test_get_all_metadata_formats_skills(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_all_metadata returns formatted skill list."""
        s = self._make_skill(tmp_path, "debugging", "Debug systematically")
        ldr = loader.SkillLoader({"debugging": s})

        meta = ldr.get_all_metadata()
        assert "## Available Skills" in meta
        assert "**debugging**" in meta
        assert "Debug systematically" in meta

    def test_get_all_metadata_empty_returns_empty(self) -> None:
        """get_all_metadata returns empty string when no skills."""
        ldr = loader.SkillLoader({})
        assert ldr.get_all_metadata() == ""

    def test_get_skill_body_returns_body(self, tmp_path: _pathlib.Path) -> None:
        """get_skill_body returns skill body content."""
        s = self._make_skill(tmp_path, "test", body="Do these steps:\n1. First\n2. Second")
        ldr = loader.SkillLoader({"test": s})

        body = ldr.get_skill_body("test")
        assert body == "Do these steps:\n1. First\n2. Second"

    def test_trigger_skill_wraps_in_tags(self, tmp_path: _pathlib.Path) -> None:
        """trigger_skill returns body wrapped in skill tags."""
        s = self._make_skill(tmp_path, "debugging", body="Debug steps here")
        ldr = loader.SkillLoader({"debugging": s})

        result = ldr.trigger_skill("debugging")
        assert result is not None
        assert '<skill name="debugging">' in result
        assert "Debug steps here" in result
        assert "</skill>" in result

    def test_trigger_skill_returns_none_for_unknown(self) -> None:
        """trigger_skill returns None for unknown skill."""
        ldr = loader.SkillLoader({})
        assert ldr.trigger_skill("nonexistent") is None

    def test_get_reference_file_loads_from_disk(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_reference_file loads file content."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "examples.md").write_text("Example content here")

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        content = ldr.get_reference_file("test-skill", "examples.md")
        assert content == "Example content here"

    def test_get_reference_file_caches_content(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_reference_file caches loaded content."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        ref_file = skill_dir / "examples.md"
        ref_file.write_text("Original content")

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        # First load
        content1 = ldr.get_reference_file("test-skill", "examples.md")
        assert content1 == "Original content"

        # Modify file
        ref_file.write_text("Modified content")

        # Should return cached
        content2 = ldr.get_reference_file("test-skill", "examples.md")
        assert content2 == "Original content"

    def test_get_reference_file_returns_none_for_missing(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_reference_file returns None for missing file."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        content = ldr.get_reference_file("test-skill", "nonexistent.md")
        assert content is None

    def test_list_reference_files(self, tmp_path: _pathlib.Path) -> None:
        """list_reference_files returns file names."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: test\n---\nbody")
        (skill_dir / "examples.md").write_text("examples")
        (skill_dir / "advanced.md").write_text("advanced")

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        refs = ldr.list_reference_files("test-skill")
        assert set(refs) == {"examples.md", "advanced.md"}

    def test_list_scripts(self, tmp_path: _pathlib.Path) -> None:
        """list_scripts returns script names."""
        skill_dir = tmp_path / "test-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "helper.sh").write_text("#!/bin/bash")
        (scripts_dir / "tool.py").write_text("# python")

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        scripts = ldr.list_scripts("test-skill")
        assert set(scripts) == {"helper.sh", "tool.py"}

    def test_get_script_path(self, tmp_path: _pathlib.Path) -> None:
        """get_script_path returns path to script."""
        skill_dir = tmp_path / "test-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        script_file = scripts_dir / "helper.sh"
        script_file.write_text("#!/bin/bash")

        fm = skill.SkillFrontmatter(name="test-skill", description="test")
        s = skill.Skill(frontmatter=fm, body="body", path=skill_dir)
        ldr = loader.SkillLoader({"test-skill": s})

        path = ldr.get_script_path("test-skill", "helper.sh")
        assert path == script_file

    def test_to_dict_includes_all_info(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes skill count and cached refs."""
        s = self._make_skill(tmp_path, "test-skill")
        ldr = loader.SkillLoader({"test-skill": s})

        d = ldr.to_dict()
        assert d["skill_count"] == 1
        assert len(d["skills"]) == 1

