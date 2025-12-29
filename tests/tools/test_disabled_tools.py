"""Tests for tool disabling functionality."""

import os as _os
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.config.types as types
import brynhild.tools as tools


class TestDisabledToolsSettings:
    """Tests for disabled_tools and disable_builtin_tools settings."""

    def test_disable_builtin_tools_default_is_false(self) -> None:
        """Default should be False (builtins enabled)."""
        settings = config.Settings()
        assert settings.disable_builtin_tools is False

    def test_disabled_tools_default_is_empty(self) -> None:
        """Default should be empty string."""
        settings = config.Settings()
        assert settings.disabled_tools == ""

    def test_get_disabled_tools_returns_empty_set_by_default(self) -> None:
        """get_disabled_tools() should return empty set by default."""
        settings = config.Settings()
        assert settings.get_disabled_tools() == set()

    def test_get_disabled_tools_from_nested_config(self) -> None:
        """Should get disabled tools from nested tools.disabled dict."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": True, "Edit": True})
        )
        assert settings.get_disabled_tools() == {"Bash", "Write", "Edit"}

    def test_get_disabled_tools_excludes_false_values(self) -> None:
        """Should exclude tools marked as not disabled (False)."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": False, "Edit": True})
        )
        assert settings.get_disabled_tools() == {"Bash", "Edit"}

    def test_is_tool_disabled_returns_false_for_enabled_tool(self) -> None:
        """Should return False for tools not in disabled list."""
        settings = config.Settings()
        assert settings.is_tool_disabled("Bash") is False

    def test_is_tool_disabled_returns_true_for_disabled_tool(self) -> None:
        """Should return True for tools in disabled list."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": True})
        )
        assert settings.is_tool_disabled("Bash") is True
        assert settings.is_tool_disabled("Write") is True
        assert settings.is_tool_disabled("Read") is False

    def test_is_tool_disabled_returns_true_when_all_builtins_disabled(self) -> None:
        """Should return True for any tool when __builtin__ marker is set."""
        # The __builtin__ marker in disabled dict disables all builtin tools
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"__builtin__": True})
        )
        assert settings.is_tool_disabled("Bash") is True
        assert settings.is_tool_disabled("Read") is True
        assert settings.is_tool_disabled("Write") is True
        assert settings.is_tool_disabled("AnyTool") is True


class TestBuildRegistryWithDisabledTools:
    """Tests for build_registry_from_settings with disabled tools."""

    def test_registry_contains_all_tools_by_default(self) -> None:
        """All builtin tools should be registered by default."""
        settings = config.Settings()
        registry = tools.build_registry_from_settings(settings)

        # Check all builtin tools are present
        for tool_name in tools.BUILTIN_TOOL_NAMES:
            assert tool_name in registry, f"Tool {tool_name} should be in registry"

    def test_registry_excludes_disabled_tools(self) -> None:
        """Disabled tools should not be in registry."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": True})
        )
        registry = tools.build_registry_from_settings(settings)

        assert "Bash" not in registry
        assert "Write" not in registry
        assert "Read" in registry
        assert "Edit" in registry

    def test_registry_is_empty_when_all_builtins_disabled(self) -> None:
        """Registry should be empty when __builtin__ marker is set."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"__builtin__": True})
        )
        registry = tools.build_registry_from_settings(settings)

        assert len(registry) == 0

    def test_disable_single_tool(self) -> None:
        """Disabling a single tool should only remove that tool."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True})
        )
        registry = tools.build_registry_from_settings(settings)

        assert "Bash" not in registry
        # All other tools should be present
        assert "Read" in registry
        assert "Write" in registry
        assert "Edit" in registry
        assert "Grep" in registry
        assert "Glob" in registry

    def test_disabled_tools_in_to_dict(self) -> None:
        """Settings.to_dict() should include disabled_tools info."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": True})
        )
        d = settings.to_dict()

        assert "disable_builtin_tools" in d
        assert d["disable_builtin_tools"] is False
        assert "disabled_tools" in d
        assert set(d["disabled_tools"]) == {"Bash", "Write"}


class TestSystemPromptWithDisabledTools:
    """Test that system prompt reflects disabled tools."""

    def test_system_prompt_includes_all_tools_by_default(self) -> None:
        """System prompt includes all tools when none are disabled."""
        import brynhild.core.prompts as prompts
        import brynhild.tools as tools_module

        settings = config.Settings()
        registry = tools_module.build_registry_from_settings(settings)

        prompt = prompts.get_system_prompt("test-model", tool_registry=registry)

        # Check tool names are present (not just substrings)
        assert "- Bash:" in prompt
        assert "- Read:" in prompt
        assert "- Grep:" in prompt

    def test_system_prompt_excludes_disabled_tools(self) -> None:
        """System prompt excludes disabled tools."""
        import brynhild.core.prompts as prompts
        import brynhild.tools as tools_module

        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Grep": True})
        )
        registry = tools_module.build_registry_from_settings(settings)

        prompt = prompts.get_system_prompt("test-model", tool_registry=registry)

        # Check tool entries are absent (the "- ToolName:" format)
        assert "- Bash:" not in prompt
        assert "- Grep:" not in prompt
        assert "- Read:" in prompt
        assert "- Write:" in prompt

    def test_system_prompt_empty_tools_when_all_disabled(self) -> None:
        """System prompt says no tools when all are disabled."""
        import brynhild.core.prompts as prompts
        import brynhild.tools as tools_module

        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"__builtin__": True})
        )
        registry = tools_module.build_registry_from_settings(settings)

        prompt = prompts.get_system_prompt("test-model", tool_registry=registry)

        assert "no tools available" in prompt.lower()


class TestBuiltinToolNames:
    """Tests for BUILTIN_TOOL_NAMES constant."""

    def test_builtin_tool_names_is_frozen_set(self) -> None:
        """BUILTIN_TOOL_NAMES should be a frozenset."""
        assert isinstance(tools.BUILTIN_TOOL_NAMES, frozenset)

    def test_builtin_tool_names_contains_expected_tools(self) -> None:
        """Should contain all expected builtin tool names."""
        expected = {"Bash", "Read", "Write", "Edit", "Grep", "Glob", "Inspect", "LearnSkill", "Finish"}
        assert expected == tools.BUILTIN_TOOL_NAMES

