"""
Tests for plugin loading.

Tests verify that:
- Valid plugins load correctly
- Missing manifest raises FileNotFoundError
- Invalid manifest raises ValueError
- Validation detects missing declared components
"""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.plugins.loader as loader


class TestPluginLoader:
    """Tests for PluginLoader.load method."""

    def test_loads_valid_plugin_directory(self, tmp_path: _pathlib.Path) -> None:
        """Valid plugin directory with manifest loads successfully."""
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: my-plugin
version: 1.0.0
description: Test plugin
"""
        )

        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(plugin_dir)

        assert plugin.name == "my-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Test plugin"
        assert plugin.path == plugin_dir.resolve()
        assert plugin.enabled is True

    def test_missing_directory_raises_file_not_found(self, tmp_path: _pathlib.Path) -> None:
        """Non-existent directory raises FileNotFoundError."""
        plugin_loader = loader.PluginLoader()

        with _pytest.raises(FileNotFoundError, match="not found"):
            plugin_loader.load(tmp_path / "nonexistent")

    def test_missing_manifest_raises_file_not_found(self, tmp_path: _pathlib.Path) -> None:
        """Directory without plugin.yaml raises FileNotFoundError."""
        plugin_dir = tmp_path / "no-manifest"
        plugin_dir.mkdir()

        plugin_loader = loader.PluginLoader()
        with _pytest.raises(FileNotFoundError, match="not found"):
            plugin_loader.load(plugin_dir)

    def test_invalid_manifest_raises_value_error(self, tmp_path: _pathlib.Path) -> None:
        """Invalid manifest content raises ValueError."""
        plugin_dir = tmp_path / "bad-manifest"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text("not: valid: yaml: {{")

        plugin_loader = loader.PluginLoader()
        with _pytest.raises(ValueError, match="Invalid YAML"):
            plugin_loader.load(plugin_dir)


class TestPluginLoaderValidate:
    """Tests for PluginLoader.validate method."""

    def test_valid_plugin_with_all_components_has_no_warnings(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Plugin with all declared components present has no warnings."""
        plugin_dir = tmp_path / "complete-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: complete-plugin
version: 1.0.0
commands:
  - build
tools:
  - my-tool
hooks: true
skills:
  - my-skill
"""
        )

        # Create all declared components
        (plugin_dir / "commands").mkdir()
        (plugin_dir / "commands" / "build.md").write_text("# Build command")

        (plugin_dir / "tools").mkdir()
        (plugin_dir / "tools" / "my-tool.py").write_text("# Tool impl")

        (plugin_dir / "hooks.yaml").write_text("version: 1\nhooks: {}")

        (plugin_dir / "skills").mkdir()
        (plugin_dir / "skills" / "my-skill").mkdir()
        (plugin_dir / "skills" / "my-skill" / "SKILL.md").write_text("---\nname: my-skill\n---")

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert warnings == []

    def test_missing_commands_directory_generates_warning(self, tmp_path: _pathlib.Path) -> None:
        """Plugin declaring commands but missing commands/ generates warning."""
        plugin_dir = tmp_path / "missing-commands"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: missing-commands
version: 1.0.0
commands:
  - build
"""
        )

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 1
        assert "commands/ directory missing" in warnings[0]

    def test_missing_command_file_generates_warning(self, tmp_path: _pathlib.Path) -> None:
        """Plugin declaring command but missing file generates warning."""
        plugin_dir = tmp_path / "missing-cmd-file"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: missing-cmd-file
version: 1.0.0
commands:
  - build
  - deploy
"""
        )
        (plugin_dir / "commands").mkdir()
        (plugin_dir / "commands" / "build.md").write_text("# Build")
        # deploy.md is missing

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 1
        assert "deploy.md" in warnings[0]

    def test_missing_tools_directory_generates_warning(self, tmp_path: _pathlib.Path) -> None:
        """Plugin declaring tools but missing tools/ generates warning."""
        plugin_dir = tmp_path / "missing-tools"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: missing-tools
version: 1.0.0
tools:
  - my-tool
"""
        )

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 1
        assert "tools/ directory missing" in warnings[0]

    def test_missing_hooks_file_generates_warning(self, tmp_path: _pathlib.Path) -> None:
        """Plugin declaring hooks but missing hooks.yaml generates warning."""
        plugin_dir = tmp_path / "missing-hooks"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: missing-hooks
version: 1.0.0
hooks: true
"""
        )

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 1
        assert "hooks.yaml missing" in warnings[0]

    def test_missing_skill_generates_warning(self, tmp_path: _pathlib.Path) -> None:
        """Plugin declaring skill but missing SKILL.md generates warning."""
        plugin_dir = tmp_path / "missing-skill"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: missing-skill
version: 1.0.0
skills:
  - my-skill
"""
        )
        (plugin_dir / "skills").mkdir()
        # my-skill/SKILL.md is missing

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 1
        assert "my-skill/SKILL.md" in warnings[0]

    def test_multiple_missing_components_generate_multiple_warnings(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Plugin missing multiple components generates warning for each."""
        plugin_dir = tmp_path / "many-missing"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
name: many-missing
version: 1.0.0
commands:
  - build
tools:
  - my-tool
hooks: true
"""
        )

        plugin_loader = loader.PluginLoader()
        warnings = plugin_loader.validate(plugin_dir)

        assert len(warnings) == 3
        # Verify each type of warning is present
        warning_text = "\n".join(warnings)
        assert "commands/" in warning_text
        assert "tools/" in warning_text
        assert "hooks.yaml" in warning_text
