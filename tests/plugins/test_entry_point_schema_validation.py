"""
Schema validation tests for entry-point plugin return types.

These tests verify that:
1. Entry-point return types are validated before use
2. Invalid return types produce helpful error messages
3. All supported return type formats are handled correctly

This helps plugin authors catch schema issues early during development.
"""

import unittest.mock as _mock

import pydantic as _pydantic
import pytest as _pytest

import brynhild.hooks.config as hooks_config
import brynhild.plugins.commands as commands
import brynhild.plugins.hooks as hooks
import brynhild.plugins.manifest as manifest
import brynhild.plugins.providers as providers
import brynhild.plugins.rules as rules
import brynhild.plugins.tools as tools
import brynhild.skills.discovery as skills_discovery
import brynhild.skills.skill as skill_module

# Apply enable_entry_point_plugins fixture to all tests in this module
pytestmark = _pytest.mark.usefixtures("enable_entry_point_plugins")


class TestHookDefinitionValidation:
    """Test that HookDefinition provides helpful validation errors."""

    def test_missing_type_gives_helpful_error(self) -> None:
        """Missing 'type' field gives helpful error with valid options."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            hooks_config.HookDefinition(
                name="test-hook",
                command="echo test",
                # Missing required 'type' field
            )

        error_msg = str(exc_info.value)
        # Should mention valid options
        assert "command" in error_msg
        assert "script" in error_msg
        assert "prompt" in error_msg

    def test_invalid_type_gives_helpful_error(self) -> None:
        """Invalid 'type' value gives helpful error with valid options."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            hooks_config.HookDefinition(
                name="test-hook",
                type="invalid_type",
                command="echo test",
            )

        error_msg = str(exc_info.value)
        assert "invalid_type" in error_msg.lower() or "Invalid" in error_msg
        # Should mention valid options
        assert "command" in error_msg
        assert "script" in error_msg
        assert "prompt" in error_msg

    def test_command_type_without_command_field(self) -> None:
        """type='command' without command field gives helpful error."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            hooks_config.HookDefinition(
                name="test-hook",
                type="command",
                # Missing 'command' field
            )

        error_msg = str(exc_info.value)
        assert "command" in error_msg.lower()

    def test_script_type_without_script_field(self) -> None:
        """type='script' without script field gives helpful error."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            hooks_config.HookDefinition(
                name="test-hook",
                type="script",
                # Missing 'script' field
            )

        error_msg = str(exc_info.value)
        assert "script" in error_msg.lower()

    def test_prompt_type_without_prompt_field(self) -> None:
        """type='prompt' without prompt field gives helpful error."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            hooks_config.HookDefinition(
                name="test-hook",
                type="prompt",
                # Missing 'prompt' field
            )

        error_msg = str(exc_info.value)
        assert "prompt" in error_msg.lower()

    def test_valid_command_hook(self) -> None:
        """Valid command hook passes validation."""
        hook = hooks_config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo 'Hello'",
        )
        assert hook.type == "command"
        assert hook.command == "echo 'Hello'"

    def test_valid_script_hook(self) -> None:
        """Valid script hook passes validation."""
        hook = hooks_config.HookDefinition(
            name="test-hook",
            type="script",
            script="./scripts/test.py",
        )
        assert hook.type == "script"
        assert hook.script == "./scripts/test.py"

    def test_valid_prompt_hook(self) -> None:
        """Valid prompt hook passes validation."""
        hook = hooks_config.HookDefinition(
            name="test-hook",
            type="prompt",
            prompt="Analyze: {{context}}",
        )
        assert hook.type == "prompt"
        assert hook.prompt == "Analyze: {{context}}"


class TestSkillFrontmatterValidation:
    """Test that SkillFrontmatter provides helpful validation errors."""

    def test_invalid_name_pattern_gives_error(self) -> None:
        """Invalid skill name gives validation error."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            skill_module.SkillFrontmatter(
                name="Invalid Name With Spaces",
                description="Test skill",
            )

        # Error should indicate the name is invalid
        error_msg = str(exc_info.value)
        assert "name" in error_msg.lower()

    def test_name_with_uppercase_fails(self) -> None:
        """Uppercase in skill name fails validation."""
        with _pytest.raises(_pydantic.ValidationError):
            skill_module.SkillFrontmatter(
                name="MySkill",  # Should be lowercase
                description="Test skill",
            )

    def test_name_with_underscores_fails(self) -> None:
        """Underscores in skill name fails validation."""
        with _pytest.raises(_pydantic.ValidationError):
            skill_module.SkillFrontmatter(
                name="my_skill",  # Should use hyphens
                description="Test skill",
            )

    def test_valid_skill_name_passes(self) -> None:
        """Valid skill name passes validation."""
        frontmatter = skill_module.SkillFrontmatter(
            name="my-skill",
            description="Test skill",
        )
        assert frontmatter.name == "my-skill"

    def test_single_char_name_passes(self) -> None:
        """Single character skill name passes validation."""
        frontmatter = skill_module.SkillFrontmatter(
            name="x",
            description="Test skill",
        )
        assert frontmatter.name == "x"


class TestCommandFrontmatterValidation:
    """Test that CommandFrontmatter provides validation."""

    def test_missing_name_fails(self) -> None:
        """Missing name field fails validation."""
        with _pytest.raises(_pydantic.ValidationError):
            commands.CommandFrontmatter()  # type: ignore[call-arg]

    def test_valid_command_passes(self) -> None:
        """Valid command frontmatter passes validation."""
        frontmatter = commands.CommandFrontmatter(
            name="test-cmd",
            description="Test command",
            aliases=["t", "tc"],
        )
        assert frontmatter.name == "test-cmd"
        assert frontmatter.aliases == ["t", "tc"]


class TestPluginManifestValidation:
    """Test that PluginManifest provides validation."""

    def test_missing_name_fails(self) -> None:
        """Missing name field fails validation."""
        with _pytest.raises(_pydantic.ValidationError):
            manifest.PluginManifest()  # type: ignore[call-arg]

    def test_valid_manifest_passes(self) -> None:
        """Valid manifest passes validation."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            tools=["MyTool"],
        )
        assert m.name == "test-plugin"
        assert m.tools == ["MyTool"]


class TestEntryPointReturnTypeValidation:
    """Test that entry point discovery validates return types."""

    def test_hooks_entry_point_validates_return_type(self) -> None:
        """Hooks entry point validates that return is HooksConfig or dict."""
        # Mock an entry point that returns invalid type
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-hooks"
        mock_ep.load.return_value = lambda: "not a hooks config"
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = hooks.discover_hooks_from_entry_points()

        # Should skip invalid return type
        assert "bad-hooks" not in result

    def test_hooks_entry_point_accepts_dict(self) -> None:
        """Hooks entry point accepts dict that matches schema."""
        mock_ep = _mock.Mock()
        mock_ep.name = "dict-hooks"
        mock_ep.load.return_value = lambda: {
            "hooks": {
                "pre_tool_use": [
                    {"name": "test", "type": "command", "command": "echo test"}
                ]
            }
        }
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = hooks.discover_hooks_from_entry_points()

        assert "dict-hooks" in result
        assert isinstance(result["dict-hooks"], hooks_config.HooksConfig)

    def test_skills_entry_point_validates_return_type(self) -> None:
        """Skills entry point validates return type."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-skill"
        mock_ep.load.return_value = lambda: 12345  # Invalid type
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = skills_discovery.discover_skills_from_entry_points()

        # Should skip invalid return type
        assert "bad-skill" not in result

    def test_skills_entry_point_accepts_dict(self) -> None:
        """Skills entry point accepts dict with required fields."""
        mock_ep = _mock.Mock()
        mock_ep.name = "dict-skill"
        mock_ep.load.return_value = lambda: {
            "name": "dict-skill",
            "description": "A skill from dict",
            "body": "Skill body content",
        }
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = skills_discovery.discover_skills_from_entry_points()

        assert "dict-skill" in result
        assert result["dict-skill"].name == "dict-skill"

    def test_commands_entry_point_validates_return_type(self) -> None:
        """Commands entry point validates return type."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-command"
        mock_ep.load.return_value = lambda: ["not", "a", "command"]
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = commands.discover_commands_from_entry_points()

        # Should skip invalid return type
        assert "bad-command" not in result

    def test_commands_entry_point_accepts_dict(self) -> None:
        """Commands entry point accepts dict with required fields."""
        mock_ep = _mock.Mock()
        mock_ep.name = "dict-cmd"
        mock_ep.load.return_value = lambda: {
            "name": "dict-cmd",
            "body": "Command body",
        }
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = commands.discover_commands_from_entry_points()

        assert "dict-cmd" in result
        assert result["dict-cmd"].name == "dict-cmd"

    def test_rules_entry_point_validates_return_type(self) -> None:
        """Rules entry point validates return type."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-rules"
        mock_ep.load.return_value = lambda: object()  # Invalid
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = rules.discover_rules_from_entry_points()

        # Should skip invalid return type (no entry for bad-rules)
        assert not any(name == "bad-rules" for name, _ in result)

    def test_rules_entry_point_accepts_string(self) -> None:
        """Rules entry point accepts string."""
        mock_ep = _mock.Mock()
        mock_ep.name = "string-rules"
        mock_ep.load.return_value = lambda: "# My Rules\n\nFollow these."
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = rules.discover_rules_from_entry_points()

        assert any(name == "string-rules" for name, _ in result)

    def test_rules_entry_point_accepts_list(self) -> None:
        """Rules entry point accepts list of strings."""
        mock_ep = _mock.Mock()
        mock_ep.name = "list-rules"
        mock_ep.load.return_value = lambda: ["Rule 1", "Rule 2"]
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = rules.discover_rules_from_entry_points()

        # Should have two entries
        list_rules = [(n, c) for n, c in result if n.startswith("list-rules")]
        assert len(list_rules) == 2

    def test_tools_entry_point_validates_tool_class(self) -> None:
        """Tools entry point validates that return is a Tool class."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-tool"
        mock_ep.load.return_value = "not a tool class"
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = tools.discover_tools_from_entry_points()

        # Should skip invalid return type
        assert "bad-tool" not in result

    def test_providers_entry_point_validates_provider_class(self) -> None:
        """Providers entry point validates that return is a Provider class."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-provider"
        mock_ep.load.return_value = {"not": "a provider"}
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = providers.discover_providers_from_entry_points()

        # Should skip invalid return type
        assert "bad-provider" not in result


class TestHooksConfigSchemaValidation:
    """Test HooksConfig schema validation."""

    def test_hooks_config_validates_hook_definitions(self) -> None:
        """HooksConfig validates that hooks are valid HookDefinitions."""
        # Valid config
        config = hooks_config.HooksConfig(
            hooks={
                "pre_tool_use": [
                    hooks_config.HookDefinition(
                        name="test",
                        type="command",
                        command="echo test",
                    )
                ]
            }
        )
        assert len(config.hooks["pre_tool_use"]) == 1

    def test_hooks_config_from_dict_validates(self) -> None:
        """HooksConfig.model_validate validates dict input."""
        config = hooks_config.HooksConfig.model_validate({
            "hooks": {
                "pre_tool_use": [
                    {"name": "test", "type": "command", "command": "echo test"}
                ]
            }
        })
        assert config.hooks["pre_tool_use"][0].name == "test"

    def test_hooks_config_from_invalid_dict_fails(self) -> None:
        """HooksConfig.model_validate fails on invalid dict."""
        with _pytest.raises(_pydantic.ValidationError):
            hooks_config.HooksConfig.model_validate({
                "hooks": {
                    "pre_tool_use": [
                        {"name": "test"}  # Missing required 'type'
                    ]
                }
            })

