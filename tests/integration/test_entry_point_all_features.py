"""
Comprehensive integration tests for ALL entry point plugin features.

These tests verify end-to-end functionality with the test-complete plugin
which exercises every entry point group:
- brynhild.plugins (plugin manifest)
- brynhild.tools (tool classes)
- brynhild.providers (LLM providers)
- brynhild.hooks (hook configurations)
- brynhild.skills (skill definitions)
- brynhild.commands (slash commands)
- brynhild.rules (project rules)

The test plugin is "installed" via the `installed_test_plugin` fixture.
"""

import pathlib as _pathlib

import brynhild.config as config
import brynhild.plugins.commands as commands
import brynhild.plugins.discovery as discovery
import brynhild.plugins.hooks as hooks
import brynhild.plugins.providers as providers_module
import brynhild.plugins.rules as rules
import brynhild.skills.discovery as skills_discovery
import brynhild.tools.registry as registry


class TestEntryPointPluginManifest:
    """Tests for plugin manifest via brynhild.plugins entry point."""

    def test_discovers_complete_plugin_via_entry_point(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The comprehensive test plugin is discovered via entry points."""
        plugins = discovery.discover_from_entry_points()

        assert "test-complete" in plugins
        plugin = plugins["test-complete"]
        assert plugin.source == "entry_point"
        assert plugin.package_name == "brynhild-test-complete"
        assert plugin.package_version == "0.0.1"
        assert plugin.manifest.name == "test-complete"

    def test_plugin_declares_all_features(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The plugin manifest declares all features it provides."""
        plugins = discovery.discover_from_entry_points()
        plugin = plugins["test-complete"]

        # Check declared tools
        assert "TestEcho" in plugin.manifest.tools
        assert "TestCounter" in plugin.manifest.tools

        # Check declared hooks
        assert plugin.manifest.hooks is True

        # Check declared skills
        assert "test-skill" in plugin.manifest.skills

        # Check declared providers
        assert "test-mock" in plugin.manifest.providers

        # Check declared commands
        assert "test-cmd" in plugin.manifest.commands

        # Check declared rules
        assert "test-rules" in plugin.manifest.rules


class TestEntryPointTools:
    """Tests for tool loading via brynhild.tools entry point."""

    def test_echo_tool_loads(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestEcho tool loads via entry points."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        assert "TestEcho" in tool_registry

        tool = tool_registry.get("TestEcho")
        assert tool is not None
        assert tool.name == "TestEcho"
        assert "echo" in tool.description.lower()

    def test_counter_tool_loads(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestCounter tool loads via entry points."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        assert "TestCounter" in tool_registry

        tool = tool_registry.get("TestCounter")
        assert tool is not None
        assert tool.name == "TestCounter"
        assert "counter" in tool.description.lower()

    async def test_echo_tool_executes(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestEcho tool executes correctly."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        tool = tool_registry.get("TestEcho")
        assert tool is not None

        result = await tool.execute({"message": "Hello, World!"})

        assert result.success is True
        assert "Hello, World!" in result.output

    async def test_counter_tool_executes(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestCounter tool executes correctly."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        tool = tool_registry.get("TestCounter")
        assert tool is not None

        # Reset first
        result = await tool.execute({"operation": "reset"})
        assert result.success is True
        assert "0" in result.output

        # Increment
        result = await tool.execute({"operation": "increment", "amount": 5})
        assert result.success is True
        assert "5" in result.output

        # Decrement
        result = await tool.execute({"operation": "decrement", "amount": 2})
        assert result.success is True
        assert "3" in result.output

    async def test_tool_error_handling(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools handle errors correctly."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        tool = tool_registry.get("TestEcho")
        assert tool is not None

        # Missing required argument
        result = await tool.execute({})
        assert result.success is False
        assert result.error is not None


class TestEntryPointProviders:
    """Tests for provider loading via brynhild.providers entry point."""

    def test_mock_provider_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The MockProvider is discovered via entry points."""
        provider_classes = providers_module.discover_providers_from_entry_points()

        assert "test-mock" in provider_classes
        provider_class = provider_classes["test-mock"]
        assert provider_class.PROVIDER_NAME == "test-mock"

    def test_mock_provider_instantiation(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The MockProvider can be instantiated."""
        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]

        provider = provider_class(model="test-model", api_key="fake-key")

        assert provider.name == "test-mock"
        assert provider.model == "test-model"
        assert provider.supports_tools is True
        assert provider.supports_streaming is True

    async def test_mock_provider_complete(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The MockProvider.complete() returns mock responses."""
        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]

        provider = provider_class(model="test-model")
        response = await provider.complete([{"role": "user", "content": "Hello"}])

        assert "Mock response" in response.content
        assert response.usage is not None
        assert response.usage.input_tokens == 100

    async def test_mock_provider_stream(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The MockProvider.stream() returns mock stream events."""
        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]

        provider = provider_class(model="test-model")
        events = []
        async for event in provider.stream([{"role": "user", "content": "Hello"}]):
            events.append(event)

        assert len(events) == 2  # text_delta + message_stop
        assert events[0].type == "text_delta"
        assert "Mock streaming response" in events[0].text
        assert events[1].type == "message_stop"


class TestEntryPointHooks:
    """Tests for hooks loading via brynhild.hooks entry point."""

    def test_hooks_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Hooks are discovered via entry points."""
        hooks_configs = hooks.discover_hooks_from_entry_points()

        assert "test-hooks" in hooks_configs
        hooks_config = hooks_configs["test-hooks"]
        assert "pre_tool_use" in hooks_config.hooks
        assert "post_tool_use" in hooks_config.hooks

    def test_pre_tool_hook_loaded(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Pre-tool hooks are loaded correctly."""
        hooks_configs = hooks.discover_hooks_from_entry_points()
        hooks_config = hooks_configs["test-hooks"]

        pre_hooks = hooks_config.hooks.get("pre_tool_use", [])
        assert len(pre_hooks) >= 1

        pre_hook = pre_hooks[0]
        assert pre_hook.name == "test-pre-hook"
        assert pre_hook.enabled is True
        assert "echo" in pre_hook.command

    def test_post_tool_hook_loaded(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Post-tool hooks are loaded correctly."""
        hooks_configs = hooks.discover_hooks_from_entry_points()
        hooks_config = hooks_configs["test-hooks"]

        post_hooks = hooks_config.hooks.get("post_tool_use", [])
        assert len(post_hooks) >= 1

        post_hook = post_hooks[0]
        assert post_hook.name == "test-post-hook"
        assert post_hook.enabled is True


class TestEntryPointSkills:
    """Tests for skills loading via brynhild.skills entry point."""

    def test_skill_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skills are discovered via entry points."""
        skills = skills_discovery.discover_skills_from_entry_points()

        assert "test-skill" in skills
        skill = skills["test-skill"]
        assert skill.name == "test-skill"
        assert skill.source == "entry_point"

    def test_skill_has_description(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skills have descriptions."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        assert len(skill.description) > 0
        assert "test" in skill.description.lower()

    def test_skill_has_body(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skills have body content."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        assert len(skill.body) > 0
        assert "entry point" in skill.body.lower()

    def test_skill_to_dict(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skills can be serialized to dict."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        skill_dict = skill.to_dict()
        assert skill_dict["name"] == "test-skill"
        assert skill_dict["source"] == "entry_point"


class TestEntryPointCommands:
    """Tests for commands loading via brynhild.commands entry point."""

    def test_command_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands are discovered via entry points."""
        cmds = commands.discover_commands_from_entry_points()

        assert "test-cmd" in cmds
        cmd = cmds["test-cmd"]
        assert cmd.name == "test-cmd"

    def test_command_aliases_registered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Command aliases are also registered."""
        cmds = commands.discover_commands_from_entry_points()

        # Check aliases
        assert "tc" in cmds
        assert "testcmd" in cmds

        # Aliases should point to the same command
        assert cmds["tc"].name == "test-cmd"
        assert cmds["testcmd"].name == "test-cmd"

    def test_command_has_description(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands have descriptions."""
        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        assert len(cmd.description) > 0
        assert "test" in cmd.description.lower()

    def test_command_has_body(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands have body templates."""
        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        assert len(cmd.body) > 0
        assert "{{args}}" in cmd.body

    def test_command_render(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands can render their templates."""
        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        rendered = cmd.render(args="Hello, World!")
        assert "Hello, World!" in rendered

    def test_command_to_dict(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands can be serialized to dict."""
        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        cmd_dict = cmd.to_dict()
        assert cmd_dict["name"] == "test-cmd"
        assert "tc" in cmd_dict["aliases"]


class TestEntryPointRules:
    """Tests for rules loading via brynhild.rules entry point."""

    def test_rules_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Rules are discovered via entry points."""
        rule_list = rules.discover_rules_from_entry_points()

        assert len(rule_list) > 0
        names = [name for name, _ in rule_list]
        assert "test-rules" in names

    def test_rules_have_content(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Rules have content."""
        rule_list = rules.discover_rules_from_entry_points()

        for name, content in rule_list:
            if name == "test-rules":
                assert len(content) > 0
                assert "entry point" in content.lower()
                break
        else:
            raise AssertionError("test-rules not found")

    def test_rules_contain_markers(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Rules contain expected test markers."""
        rule_list = rules.discover_rules_from_entry_points()

        for name, content in rule_list:
            if name == "test-rules":
                assert "ENTRY_POINT_RULES_LOADED" in content
                assert "test-complete" in content
                break


class TestAllFeaturesIntegration:
    """Integration tests that verify all features work together."""

    def test_all_entry_point_groups_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """All entry point groups are discovered for the complete plugin."""
        # Plugin manifest
        plugins = discovery.discover_from_entry_points()
        assert "test-complete" in plugins

        # Tools
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)
        assert "TestEcho" in tool_registry
        assert "TestCounter" in tool_registry

        # Providers
        provider_classes = providers_module.discover_providers_from_entry_points()
        assert "test-mock" in provider_classes

        # Hooks
        hooks_configs = hooks.discover_hooks_from_entry_points()
        assert "test-hooks" in hooks_configs

        # Skills
        skills = skills_discovery.discover_skills_from_entry_points()
        assert "test-skill" in skills

        # Commands
        cmds = commands.discover_commands_from_entry_points()
        assert "test-cmd" in cmds

        # Rules
        rule_list = rules.discover_rules_from_entry_points()
        assert any(name == "test-rules" for name, _ in rule_list)

    def test_plugin_discovery_returns_both_plugins(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Plugin discovery returns both the original and complete test plugins."""
        plugins = discovery.discover_from_entry_points()

        # Original test plugin
        assert "test-plugin" in plugins

        # New comprehensive plugin
        assert "test-complete" in plugins

    def test_declared_tools_match_loaded_tools(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools declared in manifest are actually loaded."""
        plugins = discovery.discover_from_entry_points()
        plugin = plugins["test-complete"]

        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        for declared_tool in plugin.manifest.tools:
            assert declared_tool in tool_registry, (
                f"Tool '{declared_tool}' declared in manifest but not loaded"
            )

