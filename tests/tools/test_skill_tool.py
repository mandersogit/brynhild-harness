"""
Tests for the LearnSkill tool.

The LearnSkill tool provides models with explicit control over skill loading,
supporting progressive disclosure:
- Level 1: List skills
- Level 2: Load full skill body
- Level 3: Access references and scripts
"""

from __future__ import annotations

import pathlib as _pathlib

import pytest as _pytest

import brynhild.skills as skills
import brynhild.tools.skill as skill_tool


def _create_skill(
    skill_dir: _pathlib.Path,
    name: str,
    description: str = "A test skill",
    body: str = "# Test Skill\n\nThis is the body.",
    references: dict[str, str] | None = None,
    scripts: dict[str, str] | None = None,
) -> None:
    """Helper to create a skill directory structure."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    )

    if references:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for filename, content in references.items():
            (refs_dir / filename).write_text(content)

    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for filename, content in scripts.items():
            script_file = scripts_dir / filename
            script_file.write_text(content)
            script_file.chmod(0o755)


class TestLearnSkillToolBasics:
    """Basic tool property tests."""

    def test_tool_name(self, tmp_path: _pathlib.Path) -> None:
        """Tool name should be 'LearnSkill'."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)
        assert tool.name == "LearnSkill"

    def test_tool_description(self, tmp_path: _pathlib.Path) -> None:
        """Tool should have a helpful description."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)
        assert "skill" in tool.description.lower()
        assert "guidance" in tool.description.lower()

    def test_requires_no_permission(self, tmp_path: _pathlib.Path) -> None:
        """Tool should not require permission (read-only)."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)
        assert tool.requires_permission is False

    def test_schema_has_all_parameters(self, tmp_path: _pathlib.Path) -> None:
        """Schema should have all expected parameters."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)
        schema = tool.input_schema

        assert schema["type"] == "object"
        props = schema["properties"]
        assert "skill" in props
        assert "info" in props
        assert "reference" in props
        assert "script" in props
        # All parameters should be optional
        assert schema.get("required", []) == []


class TestLearnSkillListMode:
    """Tests for listing skills (no skill parameter)."""

    @_pytest.mark.asyncio
    async def test_list_mode_no_args(self, tmp_path: _pathlib.Path) -> None:
        """Empty call should list skills."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({})

        assert result.success is True
        assert "test-skill" in result.output

    @_pytest.mark.asyncio
    async def test_list_mode_shows_all_skills(self, tmp_path: _pathlib.Path) -> None:
        """List mode should show all discovered skills."""
        for name in ["skill-a", "skill-b", "skill-c"]:
            skill_dir = tmp_path / ".brynhild" / "skills" / name
            _create_skill(skill_dir, name, description=f"Description of {name}")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({})

        assert result.success is True
        assert "skill-a" in result.output
        assert "skill-b" in result.output
        assert "skill-c" in result.output

    @_pytest.mark.asyncio
    async def test_list_mode_with_only_builtins(self, tmp_path: _pathlib.Path) -> None:
        """List mode with no project skills should still show builtins."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({})

        assert result.success is True
        # Builtins are always discovered
        assert "commit-helper" in result.output or "skill-creator" in result.output

    @_pytest.mark.asyncio
    async def test_empty_skill_name_lists(self, tmp_path: _pathlib.Path) -> None:
        """Empty string skill parameter should behave like list mode."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": ""})

        assert result.success is True
        assert "test-skill" in result.output


class TestLearnSkillLoadMode:
    """Tests for loading a specific skill (Level 2)."""

    @_pytest.mark.asyncio
    async def test_load_mode_returns_skill_body(self, tmp_path: _pathlib.Path) -> None:
        """Loading a skill should return its full body."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            body="# Test Skill\n\nThis is the full body of the skill.",
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill"})

        assert result.success is True
        assert "full body" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_load_mode_wrapped_in_tags(self, tmp_path: _pathlib.Path) -> None:
        """Loaded skill should be wrapped in <skill> tags."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill"})

        assert result.success is True
        assert '<skill name="test-skill">' in result.output
        assert "</skill>" in result.output

    @_pytest.mark.asyncio
    async def test_load_nonexistent_skill(self, tmp_path: _pathlib.Path) -> None:
        """Loading nonexistent skill should return error with available skills."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "existing-skill"
        _create_skill(skill_dir, "existing-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "nonexistent"})

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "existing-skill" in result.error

    @_pytest.mark.asyncio
    async def test_case_insensitive_skill_name(self, tmp_path: _pathlib.Path) -> None:
        """Skill name should be case-insensitive."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result1 = await tool.execute({"skill": "TEST-SKILL"})
        result2 = await tool.execute({"skill": "Test-Skill"})
        result3 = await tool.execute({"skill": "test-skill"})

        assert result1.success is True
        assert result2.success is True
        assert result3.success is True


class TestLearnSkillInfoMode:
    """Tests for info mode (skill metadata + resources)."""

    @_pytest.mark.asyncio
    async def test_info_mode_shows_metadata(self, tmp_path: _pathlib.Path) -> None:
        """Info mode should show skill metadata."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill", description="A wonderful skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "info": True})

        assert result.success is True
        assert "test-skill" in result.output
        assert "wonderful" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_info_mode_lists_references(self, tmp_path: _pathlib.Path) -> None:
        """Info mode should list available reference files."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            references={"patterns.md": "# Patterns", "examples.md": "# Examples"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "info": True})

        assert result.success is True
        assert "patterns.md" in result.output
        assert "examples.md" in result.output

    @_pytest.mark.asyncio
    async def test_info_mode_lists_scripts(self, tmp_path: _pathlib.Path) -> None:
        """Info mode should list available scripts."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            scripts={"helper.py": "#!/usr/bin/env python\nprint('hi')"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "info": True})

        assert result.success is True
        assert "helper.py" in result.output

    @_pytest.mark.asyncio
    async def test_info_mode_shows_none_when_empty(self, tmp_path: _pathlib.Path) -> None:
        """Info mode should indicate when no resources are available."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(skill_dir, "test-skill")

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "info": True})

        assert result.success is True
        assert "none" in result.output.lower()


class TestLearnSkillReferenceMode:
    """Tests for reference file retrieval (Level 3)."""

    @_pytest.mark.asyncio
    async def test_get_reference_returns_content(self, tmp_path: _pathlib.Path) -> None:
        """Getting a reference should return its content."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            references={"patterns.md": "# Design Patterns\n\nThis is the content."},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "reference": "patterns.md"})

        assert result.success is True
        assert "Design Patterns" in result.output
        assert "content" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_get_nonexistent_reference(self, tmp_path: _pathlib.Path) -> None:
        """Getting nonexistent reference should list available ones."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            references={"existing.md": "# Existing"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "reference": "missing.md"})

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "existing.md" in result.error


class TestLearnSkillScriptMode:
    """Tests for script path retrieval (Level 3)."""

    @_pytest.mark.asyncio
    async def test_get_script_returns_path(self, tmp_path: _pathlib.Path) -> None:
        """Getting a script should return its absolute path."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            scripts={"helper.py": "#!/usr/bin/env python\nprint('hi')"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "script": "helper.py"})

        assert result.success is True
        assert "helper.py" in result.output
        # Should be an absolute path
        assert result.output.startswith("/")

    @_pytest.mark.asyncio
    async def test_get_nonexistent_script(self, tmp_path: _pathlib.Path) -> None:
        """Getting nonexistent script should list available ones."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            scripts={"existing.py": "#!/usr/bin/env python"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "script": "missing.py"})

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "existing.py" in result.error

    @_pytest.mark.asyncio
    async def test_script_path_is_executable(self, tmp_path: _pathlib.Path) -> None:
        """Returned script path should point to an executable file."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        _create_skill(
            skill_dir,
            "test-skill",
            scripts={"helper.py": "#!/usr/bin/env python\nprint('hi')"},
        )

        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        result = await tool.execute({"skill": "test-skill", "script": "helper.py"})

        assert result.success is True
        import pathlib

        script_path = pathlib.Path(result.output)
        assert script_path.is_file()


class TestLearnSkillAPIFormats:
    """Tests for API format conversion."""

    def test_to_api_format(self, tmp_path: _pathlib.Path) -> None:
        """Tool should convert to Anthropic API format."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        api_format = tool.to_api_format()

        assert api_format["name"] == "LearnSkill"
        assert "description" in api_format
        assert "input_schema" in api_format

    def test_to_openai_format(self, tmp_path: _pathlib.Path) -> None:
        """Tool should convert to OpenAI API format."""
        registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=registry)

        openai_format = tool.to_openai_format()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "LearnSkill"
        assert "description" in openai_format["function"]
        assert "parameters" in openai_format["function"]
