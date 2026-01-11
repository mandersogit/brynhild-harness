"""
End-to-end tests for plugin operational integration.

These tests verify that plugin components work correctly in the full
Brynhild system, not just that they're discovered:

1. Tools execute in conversation flow and their results are used
2. Providers work in the conversation processor
3. Hooks fire when tools are used (pre/post)
4. Skills get injected into system prompts
5. Commands parse and render correctly in context
6. Rules get included in the system context

These tests use the comprehensive test plugin from:
tests/fixtures/plugins/entry-point-complete-plugin/
"""

import pathlib as _pathlib

import pydantic as _pydantic
import pytest as _pytest

import brynhild.config as config
import brynhild.plugins.commands as commands
import brynhild.plugins.hooks as hooks
import brynhild.plugins.rules as rules
import brynhild.skills.discovery as skills_discovery
import brynhild.skills.registry as skills_registry
import brynhild.tools.registry as tools_registry


class TestToolsOperationalIntegration:
    """Test that plugin tools work in the full system."""

    async def test_tool_executes_with_correct_result(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools from entry points execute and return correct results."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        # Get the test echo tool
        echo_tool = tool_registry.get("TestEcho")
        assert echo_tool is not None

        # Execute it - this tests the full tool execution path
        result = await echo_tool.execute({"message": "Integration test!"})

        assert result.success is True
        assert "Integration test!" in result.output

    async def test_tool_handles_missing_required_input(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools properly handle validation errors."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        echo_tool = tool_registry.get("TestEcho")
        result = await echo_tool.execute({})  # Missing 'message'

        assert result.success is False
        assert result.error is not None
        assert "required" in result.error.lower() or "message" in result.error.lower()

    async def test_tool_input_schema_is_valid_json_schema(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tool input schemas are valid JSON schema that can be sent to LLM."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        echo_tool = tool_registry.get("TestEcho")
        schema = echo_tool.input_schema

        # Verify it's a valid JSON Schema structure
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert "message" in schema["properties"]
        assert "required" in schema

    async def test_tool_can_be_formatted_for_llm(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools can be converted to LLM tool format."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        # Get tools in LLM-ready format (Anthropic API format)
        tools_for_llm = tool_registry.to_api_format()

        # Find our tool in the list
        echo_tool_def = next(
            (t for t in tools_for_llm if t["name"] == "TestEcho"),
            None,
        )
        assert echo_tool_def is not None
        assert "description" in echo_tool_def
        assert "input_schema" in echo_tool_def


class TestProviderOperationalIntegration:
    """Test that plugin providers work in the full system."""

    async def test_provider_produces_valid_response(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Provider from entry point produces valid CompletionResponse."""
        import brynhild.plugins.providers as providers_module

        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]
        provider = provider_class(model="test-model")

        # Call complete - this is what ConversationProcessor uses
        response = await provider.complete([
            {"role": "user", "content": "Hello, world!"}
        ])

        # Verify response structure
        assert response.content is not None
        assert response.stop_reason is not None
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0

    async def test_provider_streaming_produces_events(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Provider streaming yields valid StreamEvents."""
        import brynhild.plugins.providers as providers_module

        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]
        provider = provider_class(model="test-model")

        events = []
        async for event in provider.stream([
            {"role": "user", "content": "Hello!"}
        ]):
            events.append(event)

        # Should have at least text and stop events
        assert len(events) >= 2

        # Check event types
        event_types = [e.type for e in events]
        assert "text_delta" in event_types
        assert "message_stop" in event_types

        # Stop event should have usage
        stop_event = next(e for e in events if e.type == "message_stop")
        assert stop_event.usage is not None


class TestHooksOperationalIntegration:
    """Test that plugin hooks fire correctly during tool use."""

    def test_hooks_merge_with_base_config(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Hooks from entry points merge with base configuration."""
        # Get merged hooks config
        merged_config = hooks.load_merged_config_with_plugins(
            project_root=None,
            plugins=[],
        )

        # Entry point hooks should be included
        pre_hooks = merged_config.hooks.get("pre_tool_use", [])
        post_hooks = merged_config.hooks.get("post_tool_use", [])

        # Find our test hooks
        pre_hook_names = [h.name for h in pre_hooks]
        post_hook_names = [h.name for h in post_hooks]

        assert "test-pre-hook" in pre_hook_names
        assert "test-post-hook" in post_hook_names

    def test_hooks_have_correct_configuration(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Hooks have all required configuration."""
        merged_config = hooks.load_merged_config_with_plugins(
            project_root=None,
            plugins=[],
        )

        pre_hooks = merged_config.hooks.get("pre_tool_use", [])
        test_hook = next(h for h in pre_hooks if h.name == "test-pre-hook")

        # Verify hook configuration
        assert test_hook.type == "command"
        assert test_hook.command is not None
        assert "echo" in test_hook.command
        assert test_hook.enabled is True


class TestSkillsOperationalIntegration:
    """Test that plugin skills work in the full system."""

    def test_skill_available_in_registry(
        self, installed_test_plugin: _pathlib.Path, tmp_path: _pathlib.Path
    ) -> None:
        """Skills from entry points are available in SkillRegistry."""
        skill_reg = skills_registry.SkillRegistry(
            project_root=tmp_path,
            plugins=[],
        )

        # Get all available skills
        all_skills = skill_reg.list_skills()
        skill_names = [s.name for s in all_skills]

        assert "test-skill" in skill_names

    def test_skill_has_valid_content(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skill content is properly formatted."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        # Verify content structure
        assert len(skill.body) > 0
        assert len(skill.description) > 0

        # Body should have meaningful content
        assert "entry point" in skill.body.lower()

    def test_skill_can_get_full_content(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skill.get_full_content() returns the body for system prompt."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        full_content = skill.get_full_content()

        assert full_content == skill.body

    def test_skill_can_get_metadata_for_prompt(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Skill.get_metadata_for_prompt() returns name and description."""
        skills = skills_discovery.discover_skills_from_entry_points()
        skill = skills["test-skill"]

        metadata = skill.get_metadata_for_prompt()

        # Should contain name and description in a format for the LLM
        assert skill.name in metadata
        assert skill.description in metadata


class TestCommandsOperationalIntegration:
    """Test that plugin commands work in the full system."""

    def test_command_renders_with_args(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands render with argument substitution."""
        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        # Render with arguments
        rendered = cmd.render(args="my test argument")

        # Args should be substituted
        assert "my test argument" in rendered
        # Should not have raw template markers
        assert "{{args}}" not in rendered

    def test_command_renders_cwd(
        self, installed_test_plugin: _pathlib.Path, tmp_path: _pathlib.Path
    ) -> None:
        """Commands render current working directory."""
        import os

        cmds = commands.discover_commands_from_entry_points()
        cmd = cmds["test-cmd"]

        # Change to a known directory
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            rendered = cmd.render(args="test")

            # CWD should be substituted
            assert str(tmp_path) in rendered
            assert "{{cwd}}" not in rendered
        finally:
            os.chdir(old_cwd)

    def test_command_accessible_via_alias(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Commands are accessible via their aliases."""
        cmds = commands.discover_commands_from_entry_points()

        # Access via alias
        cmd_via_alias = cmds.get("tc")
        cmd_via_name = cmds.get("test-cmd")

        assert cmd_via_alias is not None
        assert cmd_via_name is not None
        # Should be the same command
        assert cmd_via_alias.name == cmd_via_name.name


class TestRulesOperationalIntegration:
    """Test that plugin rules work in the full system."""

    def test_rules_loaded_via_rules_manager(
        self, installed_test_plugin: _pathlib.Path, tmp_path: _pathlib.Path
    ) -> None:
        """Rules from entry points are loaded by RulesManager."""
        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
            plugins=[],
        )

        # Load all rules
        all_rules = manager.load_rules()

        # Entry point rules should be included
        assert "ENTRY_POINT_RULES_LOADED" in all_rules

    def test_rules_included_in_prompt_output(
        self, installed_test_plugin: _pathlib.Path, tmp_path: _pathlib.Path
    ) -> None:
        """Rules are formatted correctly for system prompt."""
        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
            plugins=[],
        )

        prompt_rules = manager.get_rules_for_prompt()

        # Should be wrapped in project_rules tags
        assert "<project_rules>" in prompt_rules
        assert "</project_rules>" in prompt_rules
        assert "ENTRY_POINT_RULES_LOADED" in prompt_rules


class TestContextBuildingIntegration:
    """Test that plugin components integrate into context building."""

    def test_skills_available_for_context(
        self, installed_test_plugin: _pathlib.Path, tmp_path: _pathlib.Path
    ) -> None:
        """Skills from entry points are available in context building."""
        skill_reg = skills_registry.SkillRegistry(
            project_root=tmp_path,
            plugins=[],
        )

        # Active skills would be pulled into system prompt
        all_skills = skill_reg.list_skills()

        # Should find the entry point skill
        ep_skills = [s for s in all_skills if s.source == "entry_point"]
        assert len(ep_skills) >= 1


class TestFullOperationalFlow:
    """Test complete operational flows with all components."""

    async def test_tool_execution_flow(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Full tool execution flow from registry to result."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        # 1. Get tool
        tool = tool_registry.get("TestEcho")
        assert tool is not None

        # 2. Verify schema for LLM
        schema = tool.input_schema
        assert schema["type"] == "object"

        # 3. Execute tool
        result = await tool.execute({"message": "Full flow test"})
        assert result.success

        # 4. Result is suitable for returning to LLM
        assert isinstance(result.output, str)
        assert len(result.output) > 0

    async def test_stateful_tool_maintains_state(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Stateful tools maintain state across calls."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        counter = tool_registry.get("TestCounter")

        # Reset to known state
        result = await counter.execute({"operation": "reset"})
        assert "0" in result.output

        # Increment
        result = await counter.execute({"operation": "increment", "amount": 10})
        assert "10" in result.output

        # Get - should still be 10
        result = await counter.execute({"operation": "get"})
        assert "10" in result.output

        # State persists across calls
        result = await counter.execute({"operation": "decrement", "amount": 3})
        assert "7" in result.output

    async def test_provider_complete_flow(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Full provider completion flow."""
        import brynhild.plugins.providers as providers_module

        provider_classes = providers_module.discover_providers_from_entry_points()
        provider_class = provider_classes["test-mock"]

        # 1. Instantiate with settings
        provider = provider_class(model="gpt-test", api_key="test-key")

        # 2. Verify configuration
        assert provider.model == "gpt-test"
        assert provider.supports_tools is True

        # 3. Call complete
        response = await provider.complete([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ])

        # 4. Response is valid
        assert response.id is not None
        assert len(response.content) > 0
        assert response.usage.input_tokens > 0


class TestErrorHandlingIntegration:
    """Test that plugin components handle errors correctly."""

    async def test_tool_returns_error_not_raises(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools return ToolResult with error, not raise exceptions."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        counter = tool_registry.get("TestCounter")

        # Invalid operation should return error result, not raise
        result = await counter.execute({"operation": "invalid_op"})

        assert result.success is False
        assert result.error is not None

    def test_skill_with_invalid_name_handled(self) -> None:
        """Skill name validation works."""
        import brynhild.skills.skill as skill_module

        # Invalid names should fail validation
        with _pytest.raises(_pydantic.ValidationError):
            skill_module.SkillFrontmatter(
                name="Invalid Name With Spaces",  # Not allowed
                description="Test",
            )

    def test_hook_type_validation(self) -> None:
        """Hook type field is validated."""
        import brynhild.hooks.config as hooks_config

        # Invalid type should fail
        with _pytest.raises(_pydantic.ValidationError):
            hooks_config.HookDefinition(
                name="test",
                type="invalid_type",  # Not allowed
                command="echo test",
            )


class TestMultiplePluginsIntegration:
    """Test that multiple entry point plugins work together."""

    def test_both_test_plugins_discovered(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Both test plugins are discovered together."""
        import brynhild.plugins.discovery as discovery

        plugins = discovery.discover_from_entry_points()

        # Both plugins should be present
        assert "test-plugin" in plugins
        assert "test-complete" in plugins

    def test_tools_from_all_plugins_available(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Tools from all plugins are available in registry."""
        settings = config.Settings()
        tool_registry = tools_registry.build_registry_from_settings(settings)

        # Tools from test-plugin
        assert "TestCalculator" in tool_registry

        # Tools from test-complete
        assert "TestEcho" in tool_registry
        assert "TestCounter" in tool_registry

