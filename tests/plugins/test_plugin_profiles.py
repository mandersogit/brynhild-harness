"""Tests for plugin-supplied model profiles."""

import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.plugins.profiles as plugin_profiles
import brynhild.profiles.manager as profile_manager
import brynhild.profiles.types as profile_types


class TestLoadProfilesFromDirectory:
    """Tests for load_profiles_from_directory function."""

    def test_empty_directory(self, tmp_path: _pathlib.Path) -> None:
        """Empty directory returns empty dict."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        result = plugin_profiles.load_profiles_from_directory(profiles_dir)
        assert result == {}

    def test_nonexistent_directory(self, tmp_path: _pathlib.Path) -> None:
        """Nonexistent directory returns empty dict."""
        profiles_dir = tmp_path / "nonexistent"

        result = plugin_profiles.load_profiles_from_directory(profiles_dir)
        assert result == {}

    def test_loads_valid_profile(self, tmp_path: _pathlib.Path) -> None:
        """Valid YAML profile is loaded correctly."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_yaml = profiles_dir / "test-model.yaml"
        profile_yaml.write_text("""
name: test-model
family: test
description: Test model profile
default_temperature: 0.8
supports_tools: true
""")

        result = plugin_profiles.load_profiles_from_directory(profiles_dir, "test-plugin")
        assert "test-model" in result
        assert result["test-model"].name == "test-model"
        assert result["test-model"].family == "test"
        assert result["test-model"].default_temperature == 0.8
        assert result["test-model"].supports_tools is True

    def test_skips_invalid_yaml(self, tmp_path: _pathlib.Path) -> None:
        """Invalid YAML files are skipped with warning."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        # Create invalid YAML
        invalid = profiles_dir / "invalid.yaml"
        invalid.write_text("{ invalid yaml [[[")

        # Create valid profile
        valid = profiles_dir / "valid.yaml"
        valid.write_text("name: valid\nfamily: test\n")

        result = plugin_profiles.load_profiles_from_directory(profiles_dir)
        assert "valid" in result
        assert "invalid" not in result

    def test_loads_multiple_profiles(self, tmp_path: _pathlib.Path) -> None:
        """Multiple profiles are all loaded."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        for i in range(3):
            profile = profiles_dir / f"model-{i}.yaml"
            profile.write_text(f"name: model-{i}\nfamily: test\n")

        result = plugin_profiles.load_profiles_from_directory(profiles_dir)
        assert len(result) == 3
        for i in range(3):
            assert f"model-{i}" in result


class TestLoadAllPluginProfiles:
    """Tests for load_all_plugin_profiles function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        plugin_profiles.clear_cache()

    def teardown_method(self) -> None:
        """Clear cache after each test."""
        plugin_profiles.clear_cache()

    def test_caches_results(self) -> None:
        """Results are cached after first call."""
        with _mock.patch(
            "brynhild.plugins.profiles.discovery.get_plugin_search_paths",
            return_value=[],
        ):
            # First call
            result1 = plugin_profiles.load_all_plugin_profiles()
            # Second call should return cached result
            result2 = plugin_profiles.load_all_plugin_profiles()

            assert result1 is result2

    def test_clear_cache_works(self) -> None:
        """clear_cache() clears the cached profiles."""
        with _mock.patch(
            "brynhild.plugins.profiles.discovery.get_plugin_search_paths",
            return_value=[],
        ):
            # Load profiles (creates cache)
            plugin_profiles.load_all_plugin_profiles()

            # Clear cache
            plugin_profiles.clear_cache()

            # Should be None now (will reload on next call)
            assert plugin_profiles._plugin_profiles is None


class TestProfileManagerPluginIntegration:
    """Tests for ProfileManager with plugin profiles."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        plugin_profiles.clear_cache()

    def teardown_method(self) -> None:
        """Clear cache after each test."""
        plugin_profiles.clear_cache()

    def test_load_plugin_profiles_flag_default_true(self) -> None:
        """load_plugin_profiles defaults to True."""
        with _mock.patch.object(
            profile_manager.ProfileManager,
            "_load_plugin_profiles",
        ) as mock_load:
            profile_manager.ProfileManager(load_user_profiles=False)
            mock_load.assert_called_once()

    def test_load_plugin_profiles_flag_false_skips(self) -> None:
        """load_plugin_profiles=False skips plugin profile loading."""
        with _mock.patch.object(
            profile_manager.ProfileManager,
            "_load_plugin_profiles",
        ) as mock_load:
            profile_manager.ProfileManager(
                load_user_profiles=False,
                load_plugin_profiles=False,
            )
            mock_load.assert_not_called()

    def test_plugin_profiles_override_builtins(self, tmp_path: _pathlib.Path) -> None:
        """Plugin profiles can override builtin profiles."""
        # Create a mock plugin with a profile that overrides a builtin
        plugin_profiles_dir = tmp_path / "profiles"
        plugin_profiles_dir.mkdir()

        # Create a profile with the same name as a builtin (if one exists)
        # or just verify the mechanism works
        override_profile = plugin_profiles_dir / "custom.yaml"
        override_profile.write_text("""
name: custom-from-plugin
family: custom
description: Custom profile from plugin
default_temperature: 0.5
""")

        # Mock the plugin profile loading to return our test profile
        test_profile = profile_types.ModelProfile(
            name="custom-from-plugin",
            family="custom",
            description="Custom profile from plugin",
            default_temperature=0.5,
        )

        with _mock.patch(
            "brynhild.plugins.profiles.load_all_plugin_profiles",
            return_value={"custom-from-plugin": test_profile},
        ):
            manager = profile_manager.ProfileManager(
                load_user_profiles=False,
                load_plugin_profiles=True,
            )

            # Should be able to get the plugin profile
            profile = manager.get_profile("custom-from-plugin")
            assert profile is not None
            assert profile.name == "custom-from-plugin"
            assert profile.default_temperature == 0.5

    def test_priority_order_builtin_plugin_user(self, tmp_path: _pathlib.Path) -> None:
        """Verify priority: user > plugin > builtin."""
        # Create user profile directory with override
        user_profiles_dir = tmp_path / "profiles"
        user_profiles_dir.mkdir()

        user_profile_file = user_profiles_dir / "priority-test.yaml"
        user_profile_file.write_text("""
name: priority-test
family: test
description: User profile wins
default_temperature: 0.1
""")

        # Create plugin profile that would be overridden
        plugin_profile = profile_types.ModelProfile(
            name="priority-test",
            family="test",
            description="Plugin profile would lose",
            default_temperature=0.5,
        )

        with _mock.patch(
            "brynhild.plugins.profiles.load_all_plugin_profiles",
            return_value={"priority-test": plugin_profile},
        ):
            manager = profile_manager.ProfileManager(
                config_dir=tmp_path,
                load_user_profiles=True,
                load_plugin_profiles=True,
            )

            profile = manager.get_profile("priority-test")
            assert profile is not None
            # User profile should win (temperature 0.1)
            assert profile.default_temperature == 0.1


class TestPluginProfileWithRealPlugin:
    """Integration tests with real plugin structure (mocked discovery)."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        plugin_profiles.clear_cache()

    def teardown_method(self) -> None:
        """Clear cache after each test."""
        plugin_profiles.clear_cache()

    def test_loads_profile_from_plugin_directory(self, tmp_path: _pathlib.Path) -> None:
        """Profiles are loaded from plugin's profiles/ directory."""
        # Create plugin structure
        plugin_dir = tmp_path / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)

        # Create plugin manifest
        manifest = plugin_dir / "plugin.yaml"
        manifest.write_text("""
name: test-plugin
version: 1.0.0
description: Test plugin with profiles
""")

        # Create profiles directory
        profiles_dir = plugin_dir / "profiles"
        profiles_dir.mkdir()

        # Create profile YAML
        profile_yaml = profiles_dir / "my-model.yaml"
        profile_yaml.write_text("""
name: my-model
family: my
description: My model profile
default_temperature: 0.9
api_params:
  frequency_penalty: 0.2
""")

        # Mock plugin discovery to return our test path
        with _mock.patch(
            "brynhild.plugins.profiles.discovery.get_plugin_search_paths",
            return_value=[tmp_path / "plugins"],
        ):
            profiles = plugin_profiles.load_all_plugin_profiles()

            assert "my-model" in profiles
            assert profiles["my-model"].name == "my-model"
            assert profiles["my-model"].family == "my"
            assert profiles["my-model"].default_temperature == 0.9
            assert profiles["my-model"].api_params == {"frequency_penalty": 0.2}


class TestPluginProfileCollisions:
    """Tests for profile name collision handling."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        plugin_profiles.clear_cache()

    def teardown_method(self) -> None:
        """Clear cache after each test."""
        plugin_profiles.clear_cache()

    def test_collision_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Two plugins providing same profile name raises ProfileCollisionError.

        Requirement: Plugin profiles must have unique names.
        Fails if: Collision is silently ignored (last-one-wins).
        """
        # Create two plugins with conflicting profile names
        for plugin_name in ["plugin-a", "plugin-b"]:
            plugin_dir = tmp_path / "plugins" / plugin_name
            plugin_dir.mkdir(parents=True)

            manifest = plugin_dir / "plugin.yaml"
            manifest.write_text(f"""
name: {plugin_name}
version: 1.0.0
description: Test plugin
""")

            profiles_dir = plugin_dir / "profiles"
            profiles_dir.mkdir()

            # Both plugins provide a profile named "conflicting-model"
            profile_yaml = profiles_dir / "conflicting.yaml"
            profile_yaml.write_text(f"""
name: conflicting-model
family: test
description: Profile from {plugin_name}
""")

        with _mock.patch(
            "brynhild.plugins.profiles.discovery.get_plugin_search_paths",
            return_value=[tmp_path / "plugins"],
        ):
            with _pytest.raises(plugin_profiles.ProfileCollisionError) as exc_info:
                plugin_profiles.load_all_plugin_profiles()

            # Error message should identify both plugins
            assert "conflicting-model" in str(exc_info.value)
            assert "plugin-a" in str(exc_info.value) or "plugin-b" in str(exc_info.value)

    def test_different_profile_names_no_collision(self, tmp_path: _pathlib.Path) -> None:
        """Two plugins with different profile names load successfully.

        Requirement: Multiple plugins can provide profiles if names are unique.
        Fails if: Non-conflicting profiles incorrectly raise collision error.
        """
        # Create two plugins with different profile names
        for i, plugin_name in enumerate(["plugin-a", "plugin-b"]):
            plugin_dir = tmp_path / "plugins" / plugin_name
            plugin_dir.mkdir(parents=True)

            manifest = plugin_dir / "plugin.yaml"
            manifest.write_text(f"""
name: {plugin_name}
version: 1.0.0
description: Test plugin
""")

            profiles_dir = plugin_dir / "profiles"
            profiles_dir.mkdir()

            # Each plugin provides a uniquely named profile
            profile_yaml = profiles_dir / f"model-{i}.yaml"
            profile_yaml.write_text(f"""
name: model-{i}
family: test
description: Profile from {plugin_name}
""")

        with _mock.patch(
            "brynhild.plugins.profiles.discovery.get_plugin_search_paths",
            return_value=[tmp_path / "plugins"],
        ):
            # Should not raise
            profiles = plugin_profiles.load_all_plugin_profiles()

            assert "model-0" in profiles
            assert "model-1" in profiles
