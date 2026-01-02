"""
Tests for plugin hooks integration.

Tests verify that:
- Plugin hooks are loaded from hooks.yaml
- Plugin hooks are merged with standalone hooks
- Later plugins override earlier plugins
- Standalone hooks run before plugin hooks
"""

import pathlib as _pathlib

import brynhild.hooks.config as hooks_config
import brynhild.plugins.hooks as plugin_hooks
import brynhild.plugins.manifest as manifest


class TestLoadPluginHooks:
    """Tests for load_plugin_hooks function."""

    def _create_plugin_with_hooks(
        self, path: _pathlib.Path, name: str, hooks_yaml: str
    ) -> manifest.Plugin:
        """Helper to create a plugin with hooks."""
        path.mkdir(parents=True, exist_ok=True)
        (path / "plugin.yaml").write_text(f"""
name: {name}
version: 1.0.0
hooks: true
""")
        (path / "hooks.yaml").write_text(hooks_yaml)

        m = manifest.PluginManifest(name=name, version="1.0.0", hooks=True)
        return manifest.Plugin(manifest=m, path=path)

    def test_loads_hooks_from_plugin(self, tmp_path: _pathlib.Path) -> None:
        """Hooks are loaded from plugin hooks.yaml."""
        plugin = self._create_plugin_with_hooks(
            tmp_path / "my-plugin",
            "my-plugin",
            """
version: 1
hooks:
  pre_tool_use:
    - name: log_tool
      type: command
      command: echo "tool used"
""",
        )

        config = plugin_hooks.load_plugin_hooks(plugin)

        assert config is not None
        # Check the hooks dict directly
        assert "pre_tool_use" in config.hooks
        assert len(config.hooks["pre_tool_use"]) == 1
        assert config.hooks["pre_tool_use"][0].name == "log_tool"

    def test_returns_none_for_plugin_without_hooks(self, tmp_path: _pathlib.Path) -> None:
        """Returns None if plugin doesn't declare hooks."""
        m = manifest.PluginManifest(name="no-hooks", version="1.0.0", hooks=False)
        plugin = manifest.Plugin(manifest=m, path=tmp_path)

        config = plugin_hooks.load_plugin_hooks(plugin)

        assert config is None

    def test_returns_none_for_missing_hooks_file(self, tmp_path: _pathlib.Path) -> None:
        """Returns None if hooks.yaml doesn't exist."""
        m = manifest.PluginManifest(name="missing", version="1.0.0", hooks=True)
        plugin = manifest.Plugin(manifest=m, path=tmp_path)
        # Don't create hooks.yaml

        config = plugin_hooks.load_plugin_hooks(plugin)

        assert config is None


class TestMergePluginHooks:
    """Tests for merge_plugin_hooks function."""

    def _create_plugin_with_hooks(
        self, path: _pathlib.Path, name: str, hooks_yaml: str
    ) -> manifest.Plugin:
        """Helper to create a plugin with hooks."""
        path.mkdir(parents=True, exist_ok=True)
        (path / "plugin.yaml").write_text(f"""
name: {name}
version: 1.0.0
hooks: true
""")
        (path / "hooks.yaml").write_text(hooks_yaml)

        m = manifest.PluginManifest(name=name, version="1.0.0", hooks=True)
        return manifest.Plugin(manifest=m, path=path)

    def test_merges_plugin_hooks_with_base(self, tmp_path: _pathlib.Path) -> None:
        """Plugin hooks are added to base config."""
        base_config = hooks_config.HooksConfig(
            hooks={
                "pre_tool_use": [
                    hooks_config.HookDefinition(
                        name="base_hook", type="command", command="echo base"
                    )
                ]
            }
        )

        plugin = self._create_plugin_with_hooks(
            tmp_path / "plugin",
            "plugin",
            """
version: 1
hooks:
  pre_tool_use:
    - name: plugin_hook
      type: command
      command: echo plugin
""",
        )

        merged = plugin_hooks.merge_plugin_hooks(base_config, [plugin])

        # Should have both hooks
        assert len(merged.hooks["pre_tool_use"]) == 2
        names = [h.name for h in merged.hooks["pre_tool_use"]]
        assert "base_hook" in names
        assert "plugin_hook" in names

    def test_later_plugin_overrides_same_name(self, tmp_path: _pathlib.Path) -> None:
        """Later plugin hooks override earlier ones with same name."""
        plugin1 = self._create_plugin_with_hooks(
            tmp_path / "plugin1",
            "plugin1",
            """
version: 1
hooks:
  pre_tool_use:
    - name: shared_hook
      type: command
      command: echo plugin1
""",
        )

        plugin2 = self._create_plugin_with_hooks(
            tmp_path / "plugin2",
            "plugin2",
            """
version: 1
hooks:
  pre_tool_use:
    - name: shared_hook
      type: command
      command: echo plugin2
""",
        )

        base_config = hooks_config.HooksConfig()
        merged = plugin_hooks.merge_plugin_hooks(base_config, [plugin1, plugin2])

        # Should have only one hook (plugin2 overrides plugin1)
        assert len(merged.hooks["pre_tool_use"]) == 1
        assert merged.hooks["pre_tool_use"][0].command == "echo plugin2"

    def test_adds_hooks_for_new_events(self, tmp_path: _pathlib.Path) -> None:
        """Plugin can add hooks for events not in base config."""
        base_config = hooks_config.HooksConfig()  # Empty

        plugin = self._create_plugin_with_hooks(
            tmp_path / "plugin",
            "plugin",
            """
version: 1
hooks:
  post_tool_use:
    - name: new_hook
      type: command
      command: echo new
""",
        )

        merged = plugin_hooks.merge_plugin_hooks(base_config, [plugin])

        assert "post_tool_use" in merged.hooks
        assert len(merged.hooks["post_tool_use"]) == 1


class TestLoadMergedConfigWithPlugins:
    """Tests for load_merged_config_with_plugins function."""

    def _create_plugin_with_hooks(
        self, path: _pathlib.Path, name: str, hooks_yaml: str
    ) -> manifest.Plugin:
        """Helper to create a plugin with hooks."""
        path.mkdir(parents=True, exist_ok=True)
        (path / "hooks.yaml").write_text(hooks_yaml)

        m = manifest.PluginManifest(name=name, version="1.0.0", hooks=True)
        return manifest.Plugin(manifest=m, path=path)

    def test_loads_standalone_hooks_without_plugins(self, tmp_path: _pathlib.Path) -> None:
        """Without plugins, returns standalone hooks only."""
        config = plugin_hooks.load_merged_config_with_plugins(
            project_root=tmp_path,
            plugins=None,
        )
        # Should return a valid config (may be empty if no hooks configured)
        assert isinstance(config, hooks_config.HooksConfig)

    def test_merges_plugins_with_standalone(self, tmp_path: _pathlib.Path) -> None:
        """Plugins are merged with standalone hooks."""
        plugin = self._create_plugin_with_hooks(
            tmp_path / "plugin",
            "plugin",
            """
version: 1
hooks:
  pre_tool_use:
    - name: plugin_hook
      type: command
      command: echo plugin
""",
        )

        config = plugin_hooks.load_merged_config_with_plugins(
            project_root=tmp_path,
            plugins=[plugin],
        )

        assert "pre_tool_use" in config.hooks
        names = [h.name for h in config.hooks["pre_tool_use"]]
        assert "plugin_hook" in names
