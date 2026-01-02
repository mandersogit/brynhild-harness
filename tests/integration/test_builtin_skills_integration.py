"""
Integration tests for builtin skills.

Verifies the full path from:
1. Builtin skills discovery
2. Skill registry loading
3. Skill metadata injection into system prompt
4. Skill triggering and content injection
"""

import pathlib as _pathlib

import brynhild.core.context as context
import brynhild.skills.discovery as discovery
import brynhild.skills.registry as registry


class TestBuiltinSkillsDiscovery:
    """Tests that builtin skills are properly discovered."""

    def test_builtin_path_exists(self) -> None:
        """The builtin skills path should exist in the package."""
        builtin_path = discovery.get_builtin_skills_path()
        assert builtin_path.exists()
        assert builtin_path.is_dir()

    def test_builtin_skills_discovered(self) -> None:
        """Builtin skills should be discovered without project root."""
        d = discovery.SkillDiscovery()  # No project root
        skills = d.discover()

        # Should have our two builtin skills
        assert "commit-helper" in skills
        assert "skill-creator" in skills

    def test_builtin_skills_have_correct_source(self) -> None:
        """Builtin skills should have source='builtin'."""
        d = discovery.SkillDiscovery()
        skills = d.discover()

        assert skills["commit-helper"].source == "builtin"
        assert skills["skill-creator"].source == "builtin"

    def test_builtin_skills_have_valid_skill_md(self) -> None:
        """Builtin skills should have valid SKILL.md files."""
        d = discovery.SkillDiscovery()
        skills = d.discover()

        for name, skill in skills.items():
            # SKILL.md exists
            assert skill.skill_file.exists(), f"{name} missing SKILL.md"
            # Has body content
            assert len(skill.body) > 0, f"{name} has empty body"
            # Has description
            assert len(skill.description) > 0, f"{name} has empty description"

    def test_project_skills_override_builtin(self, tmp_path: _pathlib.Path) -> None:
        """Project-local skills should override builtin skills of same name."""
        # Create a project-local skill with same name as builtin
        project_skills = tmp_path / ".brynhild" / "skills" / "commit-helper"
        project_skills.mkdir(parents=True)
        (project_skills / "SKILL.md").write_text("""---
name: commit-helper
description: OVERRIDDEN commit helper
---

# Overridden Content

This is the project-local override.
""")

        d = discovery.SkillDiscovery(project_root=tmp_path)
        skills = d.discover()

        # Should be overridden
        assert skills["commit-helper"].source == "project"
        assert "OVERRIDDEN" in skills["commit-helper"].description


class TestSkillRegistryIntegration:
    """Tests that skills work through the registry."""

    def test_registry_loads_builtin_skills(self) -> None:
        """Registry should load builtin skills."""
        reg = registry.SkillRegistry()
        skills = reg.list_skills()

        skill_names = [s.name for s in skills]
        assert "commit-helper" in skill_names
        assert "skill-creator" in skill_names

    def test_registry_trigger_returns_content(self) -> None:
        """Triggering a skill should return its content."""
        reg = registry.SkillRegistry()
        content = reg.trigger_skill("commit-helper")

        assert content is not None
        assert len(content) > 0
        assert "<skill" in content  # Should be wrapped in tags
        assert "commit-helper" in content

    def test_registry_trigger_includes_body(self) -> None:
        """Triggered skill should include the SKILL.md body."""
        reg = registry.SkillRegistry()
        content = reg.trigger_skill("skill-creator")

        # Check for content that should be in the body
        assert "Context Window is a Public Good" in content
        assert "SKILL.md" in content

    def test_registry_metadata_includes_all_skills(self) -> None:
        """Metadata for prompt should include all skills."""
        reg = registry.SkillRegistry()
        metadata = reg.get_metadata_for_prompt()

        assert "commit-helper" in metadata
        assert "skill-creator" in metadata
        assert "Available Skills" in metadata


class TestContextBuilderSkillInjection:
    """Tests that skills are properly injected into conversation context."""

    def test_context_includes_skill_metadata(self) -> None:
        """Build context should inject skill metadata into system prompt."""
        base_prompt = "You are an AI assistant."
        ctx = context.build_context(
            base_prompt,
            include_skills=True,
            include_rules=False,  # Don't load rules for this test
        )

        # Skill metadata should be in the final prompt
        assert "commit-helper" in ctx.system_prompt
        assert "skill-creator" in ctx.system_prompt
        assert "Available Skills" in ctx.system_prompt

    def test_context_without_skills(self) -> None:
        """Build context with include_skills=False should not have skills."""
        base_prompt = "You are an AI assistant."
        ctx = context.build_context(
            base_prompt,
            include_skills=False,
            include_rules=False,
        )

        # Should not have skill metadata
        assert "Available Skills" not in ctx.system_prompt

    def test_context_records_skill_injection(self) -> None:
        """Context should record skill injection metadata."""
        base_prompt = "You are an AI assistant."
        ctx = context.build_context(
            base_prompt,
            include_skills=True,
            include_rules=False,
        )

        # Should have injection record
        skill_injections = [i for i in ctx.injections if i.source == "skill_metadata"]
        assert len(skill_injections) == 1
        assert skill_injections[0].location == "system_prompt_append"

    def test_skill_registry_available_from_context(self) -> None:
        """ContextBuilder should provide access to skill registry for runtime triggering."""
        builder = context.ContextBuilder(include_skills=True, include_rules=False)
        builder.build("Base prompt")

        reg = builder.get_skill_registry()
        assert reg is not None

        # Should be able to trigger skills at runtime
        content = reg.trigger_skill("commit-helper")
        assert content is not None


class TestBuiltinSkillContent:
    """Tests that builtin skill content is correct."""

    def test_commit_helper_has_key_content(self) -> None:
        """commit-helper should have essential content."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("commit-helper")
        assert skill is not None

        body = skill.body

        # Key content that should be present
        assert "NO AUTONOMOUS COMMITS" in body
        assert "YAML" in body
        assert "git" in body.lower()

    def test_skill_creator_has_key_content(self) -> None:
        """skill-creator should have essential content."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("skill-creator")
        assert skill is not None

        body = skill.body

        # Key content that should be present
        assert "SKILL.md" in body
        assert "description" in body
        assert "frontmatter" in body.lower()

    def test_skill_creator_system_safety_section(self) -> None:
        """skill-creator should include system safety guidance."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("skill-creator")
        assert skill is not None

        body = skill.body

        # Should have the system safety section we added
        assert "System Safety" in body or "Do Not Mutate" in body
        assert "pip install" in body.lower() or "package" in body.lower()


class TestSkillResourcesAccess:
    """Tests that skill bundled resources are accessible."""

    def test_commit_helper_has_scripts(self) -> None:
        """commit-helper should have bundled scripts."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("commit-helper")
        assert skill is not None

        scripts = skill.list_scripts()
        script_names = [s.name for s in scripts]
        assert "commit-helper.py" in script_names

    def test_commit_helper_script_is_executable(self) -> None:
        """commit-helper script should be valid Python."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("commit-helper")
        assert skill is not None

        scripts = skill.list_scripts()
        script_path = next(s for s in scripts if s.name == "commit-helper.py")

        # Should be readable and have Python content
        content = script_path.read_text()
        assert "import click" in content or "import" in content
        assert "def " in content  # Has function definitions

    def test_skill_creator_has_references(self) -> None:
        """skill-creator should have reference files."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("skill-creator")
        assert skill is not None

        refs = skill.list_reference_files()
        ref_names = [r.name for r in refs]
        assert "patterns.md" in ref_names

    def test_skill_creator_reference_content(self) -> None:
        """skill-creator reference should have useful content."""
        reg = registry.SkillRegistry()
        skill = reg.get_skill("skill-creator")
        assert skill is not None

        refs = skill.list_reference_files()
        patterns_file = next(r for r in refs if r.name == "patterns.md")

        content = patterns_file.read_text()
        assert "Sequential" in content or "Workflow" in content
