"""
Integration tests for complete plugin functionality.

Tests the test-complete plugin fixture which exercises ALL plugin capabilities:
- Commands (greet, echo with aliases)
- Tools (marker tool)
- Providers (test-marker provider)
- Hooks (pre/post tool, pre_message, on_error)
- Skills (debugging, testing with scripts)

Also tests standalone fixtures:
- Standalone skills (my-skill)
- Rules (AGENTS.md, .cursorrules)
- Model profiles (test-model.yaml)
"""

import pathlib as _pathlib

import pytest as _pytest

# Path to fixtures
FIXTURES_DIR = _pathlib.Path(__file__).parent.parent / "fixtures"
PLUGINS_DIR = FIXTURES_DIR / "plugins"
TEST_COMPLETE_PLUGIN = PLUGINS_DIR / "test-complete"


class TestCompletePluginCommands:
    """Test commands from test-complete plugin."""

    def test_greet_command_loads(self) -> None:
        """Greet command loads with all fields."""
        import brynhild.plugins.commands as commands

        loader = commands.CommandLoader()
        cmds = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        assert "greet" in cmds
        cmd = cmds["greet"]
        assert cmd.name == "greet"
        assert cmd.description == "A test greeting command"
        assert cmd.plugin_name == "test-complete"

    def test_greet_command_aliases(self) -> None:
        """Greet command has aliases registered."""
        import brynhild.plugins.commands as commands

        loader = commands.CommandLoader()
        cmds = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        # Aliases should be separate entries pointing to same command
        assert "hi" in cmds
        assert "hello" in cmds
        assert cmds["hi"] is cmds["greet"]
        assert cmds["hello"] is cmds["greet"]

    def test_greet_command_renders_args(self) -> None:
        """Greet command substitutes {{args}}."""
        import brynhild.plugins.commands as commands

        loader = commands.CommandLoader()
        cmds = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        rendered = cmds["greet"].render(args="World")
        assert "World" in rendered

    def test_echo_command_loads(self) -> None:
        """Echo command loads correctly."""
        import brynhild.plugins.commands as commands

        loader = commands.CommandLoader()
        cmds = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        assert "echo" in cmds
        assert cmds["echo"].description == "Echo back the provided arguments"


class TestCompletePluginTools:
    """Test tools from test-complete plugin."""

    def test_marker_tool_loads(self) -> None:
        """Marker tool loads from plugin."""
        import brynhild.plugins.tools as tools

        loader = tools.ToolLoader()
        loaded = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        assert "marker" in loaded
        tool_cls = loaded["marker"]
        # Instantiate to access properties
        tool_instance = tool_cls()
        assert tool_instance.name == "marker"
        assert "marker" in tool_instance.description.lower()

    @_pytest.mark.asyncio
    async def test_marker_tool_executes(self) -> None:
        """Marker tool returns expected output."""
        import brynhild.plugins.tools as tools

        loader = tools.ToolLoader()
        loaded = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        tool = loaded["marker"]()
        result = await tool.execute({"message": "test"})

        assert result.success is True
        assert "[PLUGIN-TOOL-MARKER]" in result.output
        assert "test" in result.output


class TestCompletePluginProviders:
    """Test providers from test-complete plugin."""

    def test_provider_discovered(self) -> None:
        """test-marker provider is discovered from plugin."""
        import brynhild.plugins.providers as providers

        loader = providers.ProviderLoader()
        loaded = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        assert "test-marker" in loaded

    def test_provider_instantiates(self) -> None:
        """test-marker provider can be instantiated."""
        import brynhild.plugins.providers as providers

        loader = providers.ProviderLoader()
        loaded = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        provider_cls = loaded["test-marker"]
        provider = provider_cls(model="custom-model")

        assert provider.name == "test-marker"
        assert provider.model == "custom-model"

    @_pytest.mark.asyncio
    async def test_provider_complete(self) -> None:
        """test-marker provider returns canned response."""
        import brynhild.plugins.providers as providers

        loader = providers.ProviderLoader()
        loaded = loader.load_from_plugin(TEST_COMPLETE_PLUGIN, "test-complete")

        provider = loaded["test-marker"]()
        response = await provider.complete([{"role": "user", "content": "hello"}])

        assert "[TEST-MARKER-PROVIDER]" in response.content


class TestCompletePluginHooks:
    """Test hooks from test-complete plugin."""

    def test_hooks_load(self) -> None:
        """Hooks load from plugin."""
        import brynhild.plugins.hooks as plugin_hooks
        import brynhild.plugins.manifest as manifest

        m = manifest.load_manifest(TEST_COMPLETE_PLUGIN / "plugin.yaml")
        plugin = manifest.Plugin(manifest=m, path=TEST_COMPLETE_PLUGIN)

        config = plugin_hooks.load_plugin_hooks(plugin)

        assert config is not None
        assert "pre_tool_use" in config.hooks
        assert "post_tool_use" in config.hooks
        assert "pre_message" in config.hooks
        assert "on_error" in config.hooks

    def test_hooks_have_correct_names(self) -> None:
        """Hook definitions have expected names."""
        import brynhild.plugins.hooks as plugin_hooks
        import brynhild.plugins.manifest as manifest

        m = manifest.load_manifest(TEST_COMPLETE_PLUGIN / "plugin.yaml")
        plugin = manifest.Plugin(manifest=m, path=TEST_COMPLETE_PLUGIN)

        config = plugin_hooks.load_plugin_hooks(plugin)
        assert config is not None

        pre_tool_hooks = config.hooks["pre_tool_use"]
        assert any(h.name == "log_tool_start" for h in pre_tool_hooks)


class TestCompletePluginSkills:
    """Test skills from test-complete plugin."""

    def test_skills_load(self) -> None:
        """Skills load from plugin."""
        import brynhild.skills as skills

        skill_dir = TEST_COMPLETE_PLUGIN / "skills"
        registry = skills.SkillRegistry(
            project_root=TEST_COMPLETE_PLUGIN.parent,
            search_paths=[skill_dir],
        )

        skill_list = registry.list_skills()
        skill_names = [s.name for s in skill_list]
        assert "debugging" in skill_names
        assert "testing" in skill_names

    def test_debugging_skill_content(self) -> None:
        """Debugging skill has expected content."""
        import brynhild.skills as skills

        skill = skills.load_skill(TEST_COMPLETE_PLUGIN / "skills" / "debugging")

        assert skill.name == "debugging"
        assert "debug" in skill.description.lower()
        assert "[TEST-PLUGIN-SKILL: debugging]" in skill.body
        assert "Reproduce the Issue" in skill.body

    def test_testing_skill_has_scripts(self) -> None:
        """Testing skill has helper scripts."""
        import brynhild.skills as skills

        skill = skills.load_skill(TEST_COMPLETE_PLUGIN / "skills" / "testing")

        scripts = skill.list_scripts()
        script_names = {s.name for s in scripts}
        assert "run_tests.sh" in script_names


class TestStandaloneSkills:
    """Test standalone skill fixtures."""

    def test_standalone_skill_loads(self) -> None:
        """my-skill loads from fixtures/skills."""
        import brynhild.skills as skills

        skill_path = FIXTURES_DIR / "skills" / "my-skill"
        skill = skills.load_skill(skill_path)

        assert skill.name == "my-skill"
        assert "[TEST-STANDALONE-SKILL]" in skill.body


class TestRulesFixtures:
    """Test rules fixtures."""

    def test_agents_md_discovered(self) -> None:
        """AGENTS.md is discovered in fixtures/rules."""
        import brynhild.plugins.rules as rules

        found = rules.discover_rule_files(
            FIXTURES_DIR / "rules",
            stop_at=FIXTURES_DIR / "rules",
        )

        names = {f.name for f in found}
        assert "AGENTS.md" in names

    def test_cursorrules_discovered(self) -> None:
        """.cursorrules is discovered in fixtures/rules."""
        import brynhild.plugins.rules as rules

        found = rules.discover_rule_files(
            FIXTURES_DIR / "rules",
            stop_at=FIXTURES_DIR / "rules",
        )

        names = {f.name for f in found}
        assert ".cursorrules" in names

    def test_rules_content_loaded(self) -> None:
        """Rules content is loaded correctly."""
        import brynhild.plugins.rules as rules

        manager = rules.RulesManager(
            project_root=FIXTURES_DIR / "rules",
            include_global=False,
        )
        content = manager.load_rules()

        assert "[TEST-RULES-FIXTURE]" in content
        assert "[TEST-CURSORRULES-FIXTURE]" in content


class TestProfileFixtures:
    """Test profile fixtures."""

    def test_profile_loads(self) -> None:
        """test-model.yaml profile loads."""
        import brynhild.profiles.types as profile_types

        profile_path = FIXTURES_DIR / "profiles" / "test-model.yaml"

        import yaml as _yaml

        with open(profile_path) as f:
            data = _yaml.safe_load(f)

        profile = profile_types.ModelProfile.from_dict(data)

        assert profile.name == "test-model"
        assert profile.family == "test"
        assert profile.system_prompt_prefix == "[TEST-PROFILE-PREFIX]"
        assert profile.system_prompt_suffix == "[TEST-PROFILE-SUFFIX]"
        assert profile.min_max_tokens == 1000


class TestPluginIntegration:
    """End-to-end integration tests combining multiple features."""

    def test_full_plugin_loads_via_loader(self) -> None:
        """Complete plugin loads via PluginLoader."""
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        assert plugin.name == "test-complete"
        assert plugin.has_commands()
        assert plugin.has_tools()
        assert plugin.has_hooks()
        assert plugin.has_skills()
        assert plugin.has_providers()

    def test_plugin_validates_without_warnings(self) -> None:
        """Complete plugin passes validation."""
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(TEST_COMPLETE_PLUGIN)

        # Should have no warnings (all declared components exist)
        assert warnings == []

    def test_plugin_to_dict_complete(self) -> None:
        """Plugin.to_dict() includes all components."""
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)
        d = plugin.to_dict()

        assert d["name"] == "test-complete"
        assert "greet" in d["commands"]
        assert "marker" in d["tools"]
        assert d["hooks"] is True
        assert "debugging" in d["skills"]
        assert "test-marker" in d["providers"]

