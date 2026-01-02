"""
Tests for plugin manifest parsing.

Tests verify that:
- Valid manifests parse correctly with all fields
- Required fields are enforced
- Field validation works (name pattern, lengths)
- Invalid YAML and schema errors are caught
"""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.plugins.manifest as manifest


class TestPluginManifest:
    """Tests for PluginManifest pydantic model."""

    def test_minimal_manifest_has_required_fields(self) -> None:
        """Minimal valid manifest requires only name and version."""
        m = manifest.PluginManifest(name="test", version="1.0.0")
        assert m.name == "test"
        assert m.version == "1.0.0"
        assert m.description == ""
        assert m.commands == []
        assert m.tools == []
        assert m.hooks is False
        assert m.skills == []

    def test_full_manifest_preserves_all_fields(self) -> None:
        """All optional fields are preserved when provided."""
        m = manifest.PluginManifest(
            name="my-plugin",
            version="2.1.0",
            description="A test plugin",
            author="Test Author",
            license="MIT",
            commands=["build", "deploy"],
            tools=["my_tool"],
            hooks=True,
            skills=["my-skill"],
            brynhild_version=">=1.0.0",
        )
        assert m.name == "my-plugin"
        assert m.version == "2.1.0"
        assert m.description == "A test plugin"
        assert m.author == "Test Author"
        assert m.license == "MIT"
        assert m.commands == ["build", "deploy"]
        assert m.tools == ["my_tool"]
        assert m.hooks is True
        assert m.skills == ["my-skill"]
        assert m.brynhild_version == ">=1.0.0"

    def test_name_requires_lowercase_alphanumeric(self) -> None:
        """Plugin name must be lowercase with optional hyphens."""
        # Valid names
        manifest.PluginManifest(name="a", version="1.0.0")
        manifest.PluginManifest(name="my-plugin", version="1.0.0")
        manifest.PluginManifest(name="plugin123", version="1.0.0")

        # Invalid: uppercase
        with _pytest.raises(ValueError, match="String should match pattern"):
            manifest.PluginManifest(name="MyPlugin", version="1.0.0")

        # Invalid: starts with hyphen
        with _pytest.raises(ValueError, match="String should match pattern"):
            manifest.PluginManifest(name="-plugin", version="1.0.0")

        # Invalid: ends with hyphen (except single char)
        with _pytest.raises(ValueError, match="String should match pattern"):
            manifest.PluginManifest(name="plugin-", version="1.0.0")

    def test_name_length_limits(self) -> None:
        """Plugin name must be 1-64 characters."""
        # Empty name not allowed
        with _pytest.raises(ValueError, match="at least 1"):
            manifest.PluginManifest(name="", version="1.0.0")

        # Max length allowed
        manifest.PluginManifest(name="a" * 64, version="1.0.0")

        # Over max length
        with _pytest.raises(ValueError, match="at most 64"):
            manifest.PluginManifest(name="a" * 65, version="1.0.0")

    def test_description_length_limit(self) -> None:
        """Description must be at most 1024 characters."""
        # Max length allowed
        manifest.PluginManifest(name="test", version="1.0.0", description="a" * 1024)

        # Over max length
        with _pytest.raises(ValueError, match="at most 1024"):
            manifest.PluginManifest(name="test", version="1.0.0", description="a" * 1025)

    def test_missing_required_field_raises_error(self) -> None:
        """Missing name or version raises ValidationError."""
        with _pytest.raises(ValueError, match="name"):
            manifest.PluginManifest(version="1.0.0")  # type: ignore[call-arg]

        with _pytest.raises(ValueError, match="version"):
            manifest.PluginManifest(name="test")  # type: ignore[call-arg]

    def test_extra_fields_rejected(self) -> None:
        """Unknown fields in manifest are rejected."""
        with _pytest.raises(ValueError, match="Extra inputs"):
            manifest.PluginManifest(name="test", version="1.0.0", unknown_field="value")


class TestLoadManifest:
    """Tests for load_manifest function."""

    def test_loads_valid_yaml_manifest(self, tmp_path: _pathlib.Path) -> None:
        """Valid YAML manifest is parsed correctly."""
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text(
            """
name: my-plugin
version: 1.0.0
description: A test plugin
commands:
  - build
  - deploy
"""
        )

        m = manifest.load_manifest(manifest_file)
        assert m.name == "my-plugin"
        assert m.version == "1.0.0"
        assert m.description == "A test plugin"
        assert m.commands == ["build", "deploy"]

    def test_missing_file_raises_file_not_found(self, tmp_path: _pathlib.Path) -> None:
        """FileNotFoundError raised for missing manifest."""
        missing = tmp_path / "nonexistent.yaml"
        with _pytest.raises(FileNotFoundError, match="not found"):
            manifest.load_manifest(missing)

    def test_invalid_yaml_raises_value_error(self, tmp_path: _pathlib.Path) -> None:
        """Invalid YAML syntax raises ValueError."""
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text("{ invalid yaml: [")

        with _pytest.raises(ValueError, match="Invalid YAML"):
            manifest.load_manifest(manifest_file)

    def test_empty_file_raises_value_error(self, tmp_path: _pathlib.Path) -> None:
        """Empty manifest file raises ValueError."""
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text("")

        with _pytest.raises(ValueError, match="Empty manifest"):
            manifest.load_manifest(manifest_file)

    def test_missing_required_field_raises_value_error(self, tmp_path: _pathlib.Path) -> None:
        """Missing required fields raise ValueError with details."""
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text("description: Missing name and version")

        with _pytest.raises(ValueError, match="Invalid plugin manifest"):
            manifest.load_manifest(manifest_file)


class TestPlugin:
    """Tests for Plugin dataclass."""

    def test_plugin_exposes_manifest_properties(self, tmp_path: _pathlib.Path) -> None:
        """Plugin provides convenient access to manifest fields."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.2.3",
            description="Test description",
        )
        plugin = manifest.Plugin(manifest=m, path=tmp_path)

        assert plugin.name == "test-plugin"
        assert plugin.version == "1.2.3"
        assert plugin.description == "Test description"

    def test_plugin_path_properties_are_correct(self, tmp_path: _pathlib.Path) -> None:
        """Plugin computes correct paths for components."""
        m = manifest.PluginManifest(name="test", version="1.0.0")
        plugin = manifest.Plugin(manifest=m, path=tmp_path)

        assert plugin.commands_path == tmp_path / "commands"
        assert plugin.tools_path == tmp_path / "tools"
        assert plugin.hooks_path == tmp_path / "hooks.yaml"
        assert plugin.skills_path == tmp_path / "skills"

    def test_has_methods_reflect_manifest(self, tmp_path: _pathlib.Path) -> None:
        """has_* methods correctly reflect manifest declarations."""
        m = manifest.PluginManifest(
            name="test",
            version="1.0.0",
            commands=["build"],
            tools=[],
            hooks=True,
            skills=["my-skill"],
        )
        plugin = manifest.Plugin(manifest=m, path=tmp_path)

        assert plugin.has_commands() is True
        assert plugin.has_tools() is False
        assert plugin.has_hooks() is True
        assert plugin.has_skills() is True

    def test_to_dict_serializes_all_fields(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes all relevant fields for JSON output."""
        m = manifest.PluginManifest(
            name="test",
            version="1.0.0",
            description="Test",
            commands=["cmd"],
            tools=["tool"],
            hooks=True,
            skills=["skill"],
        )
        plugin = manifest.Plugin(manifest=m, path=tmp_path, enabled=False)
        d = plugin.to_dict()

        assert d["name"] == "test"
        assert d["version"] == "1.0.0"
        assert d["description"] == "Test"
        assert d["path"] == str(tmp_path)
        assert d["enabled"] is False
        assert d["commands"] == ["cmd"]
        assert d["tools"] == ["tool"]
        assert d["hooks"] is True
        assert d["skills"] == ["skill"]
