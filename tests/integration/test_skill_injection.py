"""Integration tests for skill injection into conversations.

These tests verify that:
1. /skill <name> command triggers skill body injection
2. LearnSkill tool provides model access to skills
3. Skill injections are logged correctly
4. Errors are handled gracefully

Note: Auto-triggering based on keywords was removed by design.
Models should use the LearnSkill tool for explicit skill access.
"""

import pathlib as _pathlib
import tempfile as _tempfile

import pytest as _pytest

import brynhild.config as config
import brynhild.core.context as context
import brynhild.logging as logging
import brynhild.skills as skills
import brynhild.tools as tools
import brynhild.tools.skill as skill_tool


class TestSkillPreprocessor:
    """Tests for the skill preprocessor module."""

    @_pytest.fixture
    def skill_registry(self, tmp_path: _pathlib.Path) -> skills.SkillRegistry:
        """Create a skill registry with test skills."""
        # Create a test skill directory
        skill_dir = tmp_path / ".brynhild" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)

        # Write a test SKILL.md
        (skill_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill for commit planning and git organization
---

# Test Skill

This is the full body of the test skill.

## Instructions

Follow these guidelines when working on commits.
"""
        )

        # Create another skill
        skill_dir2 = tmp_path / ".brynhild" / "skills" / "debug-helper"
        skill_dir2.mkdir(parents=True)
        (skill_dir2 / "SKILL.md").write_text(
            """---
name: debug-helper
description: Debug and troubleshoot code issues
---

# Debug Helper

This skill helps with debugging.
"""
        )

        return skills.SkillRegistry(project_root=tmp_path)

    def test_explicit_skill_command_triggers_injection(
        self, skill_registry: skills.SkillRegistry
    ) -> None:
        """Explicit /skill <name> command should trigger skill injection."""
        result = skills.preprocess_for_skills(
            "/skill test-skill",
            skill_registry,
        )

        assert result.skill_injection is not None
        assert result.skill_name == "test-skill"
        assert result.trigger_type == "explicit"
        assert result.error is None
        assert "Test Skill" in result.skill_injection
        assert "full body of the test skill" in result.skill_injection.lower()

    def test_explicit_skill_with_message(self, skill_registry: skills.SkillRegistry) -> None:
        """/skill <name> followed by message should inject skill and pass message."""
        result = skills.preprocess_for_skills(
            "/skill test-skill help me with commits",
            skill_registry,
        )

        assert result.skill_injection is not None
        assert result.skill_name == "test-skill"
        assert result.user_message == "help me with commits"

    def test_unknown_skill_returns_error(self, skill_registry: skills.SkillRegistry) -> None:
        """Unknown skill name should return error with available skills."""
        result = skills.preprocess_for_skills(
            "/skill nonexistent",
            skill_registry,
        )

        assert result.skill_injection is None
        assert result.error is not None
        assert "nonexistent" in result.error
        assert "test-skill" in result.error  # Should list available skills

    def test_no_registry_returns_unchanged(self) -> None:
        """When no registry is provided, message should pass through unchanged."""
        result = skills.preprocess_for_skills(
            "/skill test-skill",
            None,
        )

        assert result.skill_injection is None
        assert result.user_message == "/skill test-skill"

    def test_format_skill_injection_message(self) -> None:
        """Skill injection should be properly formatted."""
        content = "<skill>Test content</skill>"
        formatted = skills.format_skill_injection_message(content, "test-skill")

        assert "test-skill" in formatted
        assert "Test content" in formatted
        assert "activated" in formatted.lower()

    def test_normal_message_not_processed(self, skill_registry: skills.SkillRegistry) -> None:
        """Normal messages should pass through unchanged."""
        result = skills.preprocess_for_skills(
            "I need help with my commit planning",
            skill_registry,
        )

        assert result.skill_injection is None
        assert result.skill_name is None
        assert result.user_message == "I need help with my commit planning"


class TestSkillInjectionLogging:
    """Tests for skill injection logging."""

    def test_skill_triggered_logged(self, tmp_path: _pathlib.Path) -> None:
        """Skill triggers should be logged with proper event type."""
        log_file = tmp_path / "test.jsonl"

        logger = logging.ConversationLogger(
            log_dir=tmp_path,
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
            private_mode=False,
        )

        # Log a skill trigger
        logger.log_skill_triggered(
            skill_name="test-skill",
            skill_content="<skill>Test body</skill>",
            trigger_type="explicit",
            trigger_match="/skill test-skill",
        )

        logger.close()

        # Read and verify log
        import json as _json

        events = [_json.loads(line) for line in log_file.read_text().strip().split("\n")]

        # Find the skill trigger event
        skill_events = [e for e in events if e.get("source") == "skill_trigger"]
        assert len(skill_events) == 1

        event = skill_events[0]
        assert event["event_type"] == "context_injection"
        assert event["source"] == "skill_trigger"
        assert event["origin"] == "test-skill"
        assert event["trigger_type"] == "explicit"
        assert event["trigger_match"] == "/skill test-skill"
        assert "Test body" in event["content"]


class TestConversationContextWithSkills:
    """Tests for ConversationContext including skill registry."""

    def test_context_includes_skill_registry(self, tmp_path: _pathlib.Path) -> None:
        """ConversationContext should include skill registry for runtime triggering."""
        # Create a skill
        skill_dir = tmp_path / ".brynhild" / "skills" / "ctx-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: ctx-skill
description: Context test skill
---
# Context Skill
Body here.
"""
        )

        ctx = context.build_context(
            "Base prompt",
            project_root=tmp_path,
            include_skills=True,
        )

        assert ctx.skill_registry is not None
        # Should have project skill plus builtins (commit-helper, skill-creator)
        skill_names = [s.name for s in ctx.skill_registry.list_skills()]
        assert "ctx-skill" in skill_names
        assert ctx.skill_registry.get_skill("ctx-skill") is not None

    def test_context_skill_registry_can_trigger(self, tmp_path: _pathlib.Path) -> None:
        """Skill registry from context should support triggering."""
        # Create a skill
        skill_dir = tmp_path / ".brynhild" / "skills" / "trigger-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: trigger-skill
description: Trigger test skill
---
# Trigger Skill
This is the body that should be injected.
"""
        )

        ctx = context.build_context(
            "Base prompt",
            project_root=tmp_path,
            include_skills=True,
        )

        # Trigger the skill
        content = ctx.skill_registry.trigger_skill("trigger-skill")

        assert content is not None
        assert "Trigger Skill" in content
        assert "body that should be injected" in content


class TestSkillCommandParsing:
    """Tests for /skill command parsing edge cases."""

    @_pytest.fixture
    def skill_registry(self, tmp_path: _pathlib.Path) -> skills.SkillRegistry:
        """Create a minimal skill registry."""
        skill_dir = tmp_path / ".brynhild" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: my-skill
description: Test
---
Body
"""
        )
        return skills.SkillRegistry(project_root=tmp_path)

    def test_case_insensitive_command(self, skill_registry: skills.SkillRegistry) -> None:
        """/Skill and /SKILL should work."""
        result = skills.preprocess_for_skills(
            "/SKILL my-skill",
            skill_registry,
        )
        assert result.skill_injection is not None

    def test_extra_whitespace_handled(self, skill_registry: skills.SkillRegistry) -> None:
        """Extra whitespace should be handled."""
        result = skills.preprocess_for_skills(
            "/skill   my-skill   rest of message",
            skill_registry,
        )
        assert result.skill_injection is not None
        assert result.user_message.strip() == "rest of message"

    def test_multiline_message_after_command(self, skill_registry: skills.SkillRegistry) -> None:
        """Multiline message after /skill should be preserved."""
        result = skills.preprocess_for_skills(
            "/skill my-skill\nLine 1\nLine 2",
            skill_registry,
        )
        assert result.skill_injection is not None
        assert "Line 1" in result.user_message
        assert "Line 2" in result.user_message

    def test_slash_not_at_start_not_command(self, skill_registry: skills.SkillRegistry) -> None:
        """Slash command not at start should not trigger."""
        result = skills.preprocess_for_skills(
            "Please use /skill my-skill",
            skill_registry,
        )
        # This should NOT trigger because /skill is not at the start
        assert result.trigger_type != "explicit" or result.skill_injection is None


class TestBuiltinSkillsIntegration:
    """Tests that builtin skills can be triggered."""

    def test_builtin_commit_helper_can_trigger(self) -> None:
        """The builtin commit-helper skill should be triggerable."""
        # Use a temp directory so only builtins are found
        with _tempfile.TemporaryDirectory() as tmp:
            tmp_path = _pathlib.Path(tmp)

            registry = skills.SkillRegistry(project_root=tmp_path)
            skill_list = registry.list_skills()

            # Should find builtin skills
            skill_names = [s.name for s in skill_list]
            assert "commit-helper" in skill_names

            # Should be able to trigger it
            content = registry.trigger_skill("commit-helper")
            assert content is not None
            assert "commit" in content.lower()

    def test_explicit_skill_command_with_builtin(self) -> None:
        """Explicit /skill command should work with builtin skills."""
        with _tempfile.TemporaryDirectory() as tmp:
            tmp_path = _pathlib.Path(tmp)
            registry = skills.SkillRegistry(project_root=tmp_path)

            result = skills.preprocess_for_skills(
                "/skill commit-helper",
                registry,
            )

            assert result.skill_injection is not None
            assert result.skill_name == "commit-helper"
            assert result.trigger_type == "explicit"


class TestLearnSkillToolIntegration:
    """Tests for LearnSkill tool registration and functionality."""

    def test_learnskill_tool_registered(self, tmp_path: _pathlib.Path) -> None:
        """LearnSkill tool should be registered in the default registry."""
        # Create settings pointing to tmp_path
        settings = config.Settings.construct_without_dotenv(
            project_root=str(tmp_path),
        )
        registry = tools.build_registry_from_settings(settings)

        assert "LearnSkill" in registry
        tool = registry.get("LearnSkill")
        assert tool is not None
        assert tool.name == "LearnSkill"

    def test_learnskill_in_api_format(self, tmp_path: _pathlib.Path) -> None:
        """LearnSkill tool should appear in API format for LLM."""
        settings = config.Settings.construct_without_dotenv(
            project_root=str(tmp_path),
        )
        registry = tools.build_registry_from_settings(settings)

        api_tools = registry.to_api_format()
        tool_names = [t["name"] for t in api_tools]
        assert "LearnSkill" in tool_names

    @_pytest.mark.asyncio
    async def test_learnskill_lists_builtin_skills(self, tmp_path: _pathlib.Path) -> None:
        """LearnSkill() should list builtin skills."""
        skill_registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=skill_registry)

        result = await tool.execute({})

        assert result.success is True
        assert "commit-helper" in result.output

    @_pytest.mark.asyncio
    async def test_learnskill_loads_builtin_skill(self, tmp_path: _pathlib.Path) -> None:
        """LearnSkill(skill="commit-helper") should load the skill."""
        skill_registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=skill_registry)

        result = await tool.execute({"skill": "commit-helper"})

        assert result.success is True
        assert '<skill name="commit-helper">' in result.output
        assert "commit" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_learnskill_info_mode(self, tmp_path: _pathlib.Path) -> None:
        """LearnSkill(skill="commit-helper", info=True) should show resources."""
        skill_registry = skills.SkillRegistry(project_root=tmp_path)
        tool = skill_tool.LearnSkillTool(skill_registry=skill_registry)

        result = await tool.execute({"skill": "commit-helper", "info": True})

        assert result.success is True
        assert "commit-helper" in result.output
        # Should show script info
        assert "script" in result.output.lower() or "none" in result.output.lower()
