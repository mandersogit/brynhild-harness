"""
Plugin profile loading.

This module discovers and loads ModelProfile definitions from plugin
directories. Plugins can provide profiles in a `profiles/` subdirectory
containing YAML files.

Profile priority (later overrides earlier):
1. Builtin profiles (from brynhild.profiles.builtin)
2. Plugin profiles (from this module)
3. User profiles (from ~/.config/brynhild/profiles/)

Plugin profiles must have unique names. If two plugins provide a profile
with the same name, a ProfileCollisionError is raised. Use user profiles
(~/.config/brynhild/profiles/) if you need to override a plugin's profile.
"""

from __future__ import annotations

import logging as _logging
import pathlib as _pathlib

import yaml as _yaml

import brynhild.plugins.discovery as discovery
import brynhild.plugins.loader as plugin_loader
import brynhild.profiles.types as profile_types

_logger = _logging.getLogger(__name__)


class ProfileCollisionError(Exception):
    """Raised when two plugins provide profiles with the same name."""

    pass


# Global registry of plugin profiles (cached after first load)
_plugin_profiles: dict[str, profile_types.ModelProfile] | None = None

# Track which plugin provided each profile (for error messages)
_profile_sources: dict[str, str] = {}


def load_profiles_from_directory(
    profiles_dir: _pathlib.Path,
    plugin_name: str = "",
) -> dict[str, profile_types.ModelProfile]:
    """
    Load all profiles from a directory.

    Args:
        profiles_dir: Path to profiles/ directory.
        plugin_name: Name of the plugin (for logging/context).

    Returns:
        Dict mapping profile name to ModelProfile instance.
    """
    loaded_profiles: dict[str, profile_types.ModelProfile] = {}

    if not profiles_dir.is_dir():
        return loaded_profiles

    for yaml_file in sorted(profiles_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = _yaml.safe_load(f)
            if data and isinstance(data, dict):
                profile = profile_types.ModelProfile.from_dict(data)
                loaded_profiles[profile.name] = profile
                _logger.debug(
                    "Loaded plugin profile '%s' from %s (plugin: %s)",
                    profile.name,
                    yaml_file,
                    plugin_name,
                )
        except Exception as e:
            _logger.warning(
                "Failed to load profile from %s (plugin: %s): %s",
                yaml_file,
                plugin_name,
                e,
            )

    return loaded_profiles


def load_all_plugin_profiles() -> dict[str, profile_types.ModelProfile]:
    """
    Discover and load all profiles from plugin directories.

    Searches plugin paths for `profiles/` subdirectories and loads
    any YAML files found within them.

    Returns:
        Dict mapping profile name to ModelProfile instance.

    Raises:
        ProfileCollisionError: If two plugins provide profiles with the same name.
    """
    global _plugin_profiles
    global _profile_sources

    # Return cached profiles if already loaded
    if _plugin_profiles is not None:
        return _plugin_profiles

    _plugin_profiles = {}
    _profile_sources = {}
    loader = plugin_loader.PluginLoader()

    # Get all plugin search paths
    paths = discovery.get_plugin_search_paths()

    for search_path in paths:
        if not search_path.exists():
            continue

        for plugin_dir in sorted(search_path.iterdir()):
            if not plugin_dir.is_dir():
                continue

            # Check for plugin.yaml to confirm it's a valid plugin
            manifest_path = plugin_dir / "plugin.yaml"
            if not manifest_path.exists():
                continue

            try:
                plugin = loader.load(plugin_dir)
                profiles_dir = plugin.path / "profiles"
                if profiles_dir.is_dir():
                    loaded_from_plugin = load_profiles_from_directory(
                        profiles_dir, plugin.name
                    )

                    # Check for collisions before adding
                    for profile_name in loaded_from_plugin:
                        if profile_name in _plugin_profiles:
                            existing_plugin = _profile_sources.get(
                                profile_name, "unknown"
                            )
                            raise ProfileCollisionError(
                                f"Profile '{profile_name}' provided by plugin "
                                f"'{plugin.name}' conflicts with profile from "
                                f"plugin '{existing_plugin}'. Plugin profiles must "
                                f"have unique names. Use user profiles "
                                f"(~/.config/brynhild/profiles/) to override."
                            )
                        _plugin_profiles[profile_name] = loaded_from_plugin[
                            profile_name
                        ]
                        _profile_sources[profile_name] = plugin.name

                    if loaded_from_plugin:
                        _logger.debug(
                            "Loaded %d profiles from plugin '%s'",
                            len(loaded_from_plugin),
                            plugin.name,
                        )
            except ProfileCollisionError:
                # Re-raise collision errors (don't swallow them)
                raise
            except Exception as e:
                _logger.warning(
                    "Failed to process plugin %s for profiles: %s", plugin_dir, e
                )

    return _plugin_profiles


def clear_cache() -> None:
    """
    Clear the cached plugin profiles.

    Useful for testing or when plugins are reloaded.
    """
    global _plugin_profiles
    global _profile_sources
    _plugin_profiles = None
    _profile_sources = {}

