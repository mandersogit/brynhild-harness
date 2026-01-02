"""
Integration tests for plugin lifecycle hooks (PLUGIN_INIT, PLUGIN_SHUTDOWN).

Tests that plugins can define hooks that fire when:
- PLUGIN_INIT: Plugin is loaded and components registered
- PLUGIN_SHUTDOWN: Brynhild is shutting down
"""

import pathlib as _pathlib

import pytest as _pytest

# Path to fixtures
FIXTURES_DIR = _pathlib.Path(__file__).parent.parent / "fixtures"
PLUGINS_DIR = FIXTURES_DIR / "plugins"
TEST_COMPLETE_PLUGIN = PLUGINS_DIR / "test-complete"


class TestPluginLifecycleEvents:
    """Test plugin lifecycle hook event definitions."""

    def test_plugin_init_event_exists(self) -> None:
        """PLUGIN_INIT event is defined in HookEvent enum."""
        import brynhild.hooks.events as events

        assert hasattr(events.HookEvent, "PLUGIN_INIT")
        assert events.HookEvent.PLUGIN_INIT.value == "plugin_init"

    def test_plugin_shutdown_event_exists(self) -> None:
        """PLUGIN_SHUTDOWN event is defined in HookEvent enum."""
        import brynhild.hooks.events as events

        assert hasattr(events.HookEvent, "PLUGIN_SHUTDOWN")
        assert events.HookEvent.PLUGIN_SHUTDOWN.value == "plugin_shutdown"

    def test_plugin_events_cannot_block(self) -> None:
        """Plugin lifecycle events cannot block."""
        import brynhild.hooks.events as events

        assert not events.HookEvent.PLUGIN_INIT.can_block
        assert not events.HookEvent.PLUGIN_SHUTDOWN.can_block

    def test_plugin_events_cannot_modify(self) -> None:
        """Plugin lifecycle events cannot modify data."""
        import brynhild.hooks.events as events

        assert not events.HookEvent.PLUGIN_INIT.can_modify
        assert not events.HookEvent.PLUGIN_SHUTDOWN.can_modify


class TestHookContextPluginFields:
    """Test HookContext plugin-related fields."""

    def test_context_has_plugin_name(self) -> None:
        """HookContext has plugin_name field."""
        import brynhild.hooks.events as events

        context = events.HookContext(
            event=events.HookEvent.PLUGIN_INIT,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            plugin_name="test-plugin",
            plugin_path=_pathlib.Path("/path/to/plugin"),
        )

        assert context.plugin_name == "test-plugin"
        assert context.plugin_path == _pathlib.Path("/path/to/plugin")

    def test_context_to_dict_includes_plugin_fields(self) -> None:
        """HookContext.to_dict() includes plugin fields."""
        import brynhild.hooks.events as events

        context = events.HookContext(
            event=events.HookEvent.PLUGIN_INIT,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            plugin_name="test-plugin",
            plugin_path=_pathlib.Path("/path/to/plugin"),
        )

        d = context.to_dict()
        assert d["plugin_name"] == "test-plugin"
        assert d["plugin_path"] == "/path/to/plugin"

    def test_context_to_env_vars_includes_plugin_fields(self) -> None:
        """HookContext.to_env_vars() includes plugin fields."""
        import brynhild.hooks.events as events

        context = events.HookContext(
            event=events.HookEvent.PLUGIN_INIT,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            plugin_name="test-plugin",
            plugin_path=_pathlib.Path("/path/to/plugin"),
        )

        env = context.to_env_vars()
        assert env["BRYNHILD_PLUGIN_NAME"] == "test-plugin"
        assert env["BRYNHILD_PLUGIN_PATH"] == "/path/to/plugin"


class TestPluginHooksConfig:
    """Test plugin hooks configuration loading."""

    def test_test_complete_has_plugin_init_hook(self) -> None:
        """test-complete plugin has plugin_init hook defined."""
        import brynhild.plugins.hooks as plugin_hooks
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        config = plugin_hooks.load_plugin_hooks(plugin)
        assert config is not None

        # Check plugin_init hooks exist
        import brynhild.hooks.events as events

        init_hooks = config.get_hooks_for_event(events.HookEvent.PLUGIN_INIT)
        assert len(init_hooks) > 0
        assert any(h.name == "on_plugin_init" for h in init_hooks)

    def test_test_complete_has_plugin_shutdown_hook(self) -> None:
        """test-complete plugin has plugin_shutdown hook defined."""
        import brynhild.plugins.hooks as plugin_hooks
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        config = plugin_hooks.load_plugin_hooks(plugin)
        assert config is not None

        # Check plugin_shutdown hooks exist
        import brynhild.hooks.events as events

        shutdown_hooks = config.get_hooks_for_event(events.HookEvent.PLUGIN_SHUTDOWN)
        assert len(shutdown_hooks) > 0
        assert any(h.name == "on_plugin_shutdown" for h in shutdown_hooks)


class TestPluginLifecycleFunctions:
    """Test plugin lifecycle functions."""

    def test_fire_plugin_init_exports(self) -> None:
        """fire_plugin_init functions are exported from plugins module."""
        import brynhild.plugins as plugins

        assert hasattr(plugins, "fire_plugin_init")
        assert hasattr(plugins, "fire_plugin_init_sync")
        assert hasattr(plugins, "fire_plugin_init_for_all")
        assert hasattr(plugins, "fire_plugin_init_for_all_sync")

    @_pytest.mark.asyncio
    async def test_fire_plugin_init_runs_without_error(self) -> None:
        """fire_plugin_init completes without raising for valid plugin."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Should not raise
        await lifecycle.fire_plugin_init(plugin, project_root=FIXTURES_DIR)

    @_pytest.mark.asyncio
    async def test_fire_plugin_init_for_all_runs_without_error(self) -> None:
        """fire_plugin_init_for_all completes for multiple plugins."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Should not raise
        await lifecycle.fire_plugin_init_for_all([plugin], project_root=FIXTURES_DIR)

    def test_fire_plugin_init_sync_runs_without_error(self) -> None:
        """fire_plugin_init_sync completes without raising."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Should not raise
        lifecycle.fire_plugin_init_sync(plugin, project_root=FIXTURES_DIR)


class TestPluginLifecycleIntegration:
    """Integration tests for plugin lifecycle hooks."""

    def test_plugin_with_no_hooks_does_not_error(self, tmp_path: _pathlib.Path) -> None:
        """Plugin without hooks.yaml doesn't cause errors."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        # Create minimal plugin without hooks
        plugin_dir = tmp_path / "no-hooks-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text("""
name: no-hooks
version: 1.0.0
description: Plugin without hooks
""")

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(plugin_dir)

        # Should not raise
        lifecycle.fire_plugin_init_sync(plugin, project_root=tmp_path)

    def test_plugin_with_empty_hooks_does_not_error(self, tmp_path: _pathlib.Path) -> None:
        """Plugin with empty hooks.yaml doesn't cause errors."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        # Create plugin with empty hooks
        plugin_dir = tmp_path / "empty-hooks-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text("""
name: empty-hooks
version: 1.0.0
description: Plugin with empty hooks
hooks: true
""")
        (plugin_dir / "hooks.yaml").write_text("""
version: 1
hooks: {}
""")

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(plugin_dir)

        # Should not raise
        lifecycle.fire_plugin_init_sync(plugin, project_root=tmp_path)

    def test_disabled_plugin_not_initialized(self) -> None:
        """Disabled plugins don't get init hooks fired."""
        import brynhild.plugins.lifecycle as lifecycle
        import brynhild.plugins.loader as loader

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)
        plugin.enabled = False

        # Clear any previously tracked plugins
        lifecycle._initialized_plugins.clear()

        # fire_plugin_init_for_all_sync skips disabled plugins
        lifecycle.fire_plugin_init_for_all_sync([plugin], project_root=FIXTURES_DIR)

        # Plugin should not be tracked for shutdown
        assert not any(name == "test-complete" for name, _ in lifecycle._initialized_plugins)
