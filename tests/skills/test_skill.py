"""
Tests for skill parsing and Skill dataclass.

Tests verify that:
- SKILL.md files are parsed correctly
- Required fields are validated
- Skill properties work correctly
- Reference files and scripts are listed
"""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.skills.skill as skill


class TestSkillFrontmatter:
    """Tests for SkillFrontmatter pydantic model."""

    def test_minimal_frontmatter_requires_name_and_description(self) -> None:
        """Name and description are required."""
        fm = skill.SkillFrontmatter(
            name="test",
            description="A test skill",
        )
        assert fm.name == "test"
        assert fm.description == "A test skill"
        assert fm.license is None
        assert fm.allowed_tools == []

    def test_full_frontmatter_preserves_all_fields(self) -> None:
        """All fields are preserved when provided."""
        fm = skill.SkillFrontmatter(
            name="debugging",
            description="Systematic debugging workflow",
            license="MIT",
            **{"allowed-tools": ["bash", "read_file"]},
            metadata={"author": "test"},
        )
        assert fm.name == "debugging"
        assert fm.description == "Systematic debugging workflow"
        assert fm.license == "MIT"
        assert fm.allowed_tools == ["bash", "read_file"]
        assert fm.metadata == {"author": "test"}

    def test_name_requires_lowercase(self) -> None:
        """Name must be lowercase with optional hyphens."""
        # Valid
        skill.SkillFrontmatter(name="a", description="test")
        skill.SkillFrontmatter(name="my-skill", description="test")
        skill.SkillFrontmatter(name="skill123", description="test")

        # Invalid: uppercase
        with _pytest.raises(ValueError, match="String should match pattern"):
            skill.SkillFrontmatter(name="MySkill", description="test")

    def test_name_length_limits(self) -> None:
        """Name must be 1-64 characters."""
        with _pytest.raises(ValueError, match="at least 1"):
            skill.SkillFrontmatter(name="", description="test")

        # Max allowed
        skill.SkillFrontmatter(name="a" * 64, description="test")

        with _pytest.raises(ValueError, match="at most 64"):
            skill.SkillFrontmatter(name="a" * 65, description="test")

    def test_description_required(self) -> None:
        """Description cannot be empty."""
        with _pytest.raises(ValueError, match="at least 1"):
            skill.SkillFrontmatter(name="test", description="")

    def test_description_length_limit(self) -> None:
        """Description must be at most 1024 characters."""
        skill.SkillFrontmatter(name="test", description="a" * 1024)

        with _pytest.raises(ValueError, match="at most 1024"):
            skill.SkillFrontmatter(name="test", description="a" * 1025)


class TestParseSkillMarkdown:
    """Tests for parse_skill_markdown function."""

    def test_parses_valid_skill_md(self) -> None:
        """Valid SKILL.md parses correctly."""
        content = """---
name: test-skill
description: A test skill for testing
---

# Test Skill

Instructions here.
"""
        fm, body = skill.parse_skill_markdown(content)
        assert fm.name == "test-skill"
        assert fm.description == "A test skill for testing"
        assert "# Test Skill" in body
        assert "Instructions here." in body

    def test_missing_frontmatter_raises_error(self) -> None:
        """Missing frontmatter raises ValueError."""
        content = "# No frontmatter"
        with _pytest.raises(ValueError, match="must have YAML frontmatter"):
            skill.parse_skill_markdown(content)

    def test_invalid_yaml_raises_error(self) -> None:
        """Invalid YAML raises ValueError."""
        content = """---
name: [invalid {{
---

Body
"""
        with _pytest.raises(ValueError, match="Invalid YAML"):
            skill.parse_skill_markdown(content)

    def test_missing_required_field_raises_error(self) -> None:
        """Missing required field raises ValueError."""
        content = """---
name: test
---

Missing description
"""
        with _pytest.raises(ValueError, match="Invalid skill frontmatter"):
            skill.parse_skill_markdown(content)


class TestSkill:
    """Tests for Skill dataclass."""

    def _make_skill(
        self,
        tmp_path: _pathlib.Path,
        name: str = "test-skill",
        description: str = "Test description",
        body: str = "Test body",
    ) -> skill.Skill:
        """Helper to create a Skill."""
        fm = skill.SkillFrontmatter(name=name, description=description)
        skill_dir = tmp_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        return skill.Skill(
            frontmatter=fm,
            body=body,
            path=skill_dir,
            source="project",
        )

    def test_properties_expose_frontmatter(self, tmp_path: _pathlib.Path) -> None:
        """Properties delegate to frontmatter."""
        s = self._make_skill(tmp_path, name="my-skill", description="My description")
        assert s.name == "my-skill"
        assert s.description == "My description"

    def test_skill_file_property(self, tmp_path: _pathlib.Path) -> None:
        """skill_file returns path to SKILL.md."""
        s = self._make_skill(tmp_path, name="test")
        assert s.skill_file == s.path / "SKILL.md"

    def test_body_line_count(self, tmp_path: _pathlib.Path) -> None:
        """body_line_count returns correct count."""
        s = self._make_skill(tmp_path, body="line1\nline2\nline3")
        assert s.body_line_count == 3

    def test_exceeds_soft_limit(self, tmp_path: _pathlib.Path) -> None:
        """exceeds_soft_limit detects long bodies."""
        short = self._make_skill(tmp_path, name="short", body="x\n" * 100)
        long = self._make_skill(tmp_path, name="long", body="x\n" * 600)

        assert short.exceeds_soft_limit is False
        assert long.exceeds_soft_limit is True

    def test_list_reference_files(self, tmp_path: _pathlib.Path) -> None:
        """list_reference_files finds .md files except SKILL.md."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\nBody")
        (skill_dir / "examples.md").write_text("Examples")
        (skill_dir / "advanced.md").write_text("Advanced")
        (skill_dir / "readme.txt").write_text("Not markdown")

        fm = skill.SkillFrontmatter(name="test", description="test")
        s = skill.Skill(frontmatter=fm, body="Body", path=skill_dir)

        refs = s.list_reference_files()
        names = {f.name for f in refs}
        assert names == {"examples.md", "advanced.md"}
        assert "SKILL.md" not in names

    def test_list_scripts(self, tmp_path: _pathlib.Path) -> None:
        """list_scripts finds files in scripts/ directory."""
        skill_dir = tmp_path / "test-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "helper.sh").write_text("#!/bin/bash")
        (scripts_dir / "tool.py").write_text("# python")
        (scripts_dir / ".hidden").write_text("hidden")

        fm = skill.SkillFrontmatter(name="test", description="test")
        s = skill.Skill(frontmatter=fm, body="Body", path=skill_dir)

        scripts = s.list_scripts()
        names = {f.name for f in scripts}
        assert names == {"helper.sh", "tool.py"}
        assert ".hidden" not in names

    def test_get_metadata_for_prompt(self, tmp_path: _pathlib.Path) -> None:
        """get_metadata_for_prompt returns compact format."""
        s = self._make_skill(tmp_path, name="debugging", description="Debug systematically")
        meta = s.get_metadata_for_prompt()
        assert "**debugging**" in meta
        assert "Debug systematically" in meta

    def test_to_dict_includes_all_fields(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes all relevant fields."""
        skill_dir = tmp_path / "test"
        skill_dir.mkdir()
        fm = skill.SkillFrontmatter(
            name="test",
            description="Test skill",
            license="MIT",
            **{"allowed-tools": ["bash"]},
        )
        s = skill.Skill(
            frontmatter=fm,
            body="Body\nLine2",
            path=skill_dir,
            source="global",
        )
        d = s.to_dict()

        assert d["name"] == "test"
        assert d["description"] == "Test skill"
        assert d["source"] == "global"
        assert d["license"] == "MIT"
        assert d["allowed_tools"] == ["bash"]
        assert d["body_lines"] == 2


class TestLoadSkill:
    """Tests for load_skill function."""

    def test_loads_valid_skill(self, tmp_path: _pathlib.Path) -> None:
        """Valid skill directory loads correctly."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

Do the thing.
""")

        s = skill.load_skill(skill_dir, source="project")
        assert s.name == "test-skill"
        assert s.description == "A test skill"
        assert "Do the thing." in s.body
        assert s.source == "project"

    def test_missing_skill_md_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Missing SKILL.md raises FileNotFoundError."""
        skill_dir = tmp_path / "no-skill"
        skill_dir.mkdir()

        with _pytest.raises(FileNotFoundError, match="SKILL.md not found"):
            skill.load_skill(skill_dir)

    def test_invalid_skill_md_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Invalid SKILL.md raises ValueError."""
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("No frontmatter")

        with _pytest.raises(ValueError, match="must have YAML frontmatter"):
            skill.load_skill(skill_dir)
