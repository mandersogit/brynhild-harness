"""
Plugin hooks integration.

Loads hooks from plugin hooks.yaml files, entry points, and merges them with
the existing hook configuration. Plugin hooks run after standalone hooks.

Entry point plugins can register hooks via:
    [project.entry-points."brynhild.hooks"]
    my-hooks = "my_package:get_hooks"

The function should return either:
    - A HooksConfig instance
    - A dict matching the HooksConfig schema
"""

from __future__ import annotations

import importlib.metadata as _meta
import logging as _logging
import pathlib as _pathlib

import brynhild.hooks.config as hooks_config
import brynhild.plugins.manifest as manifest

_logger = _logging.getLogger(__name__)


def _entry_points_disabled() -> bool:
    """Check if entry point plugin discovery is disabled."""
    import os as _os
    return _os.environ.get("BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS", "").lower() in (
        "1", "true", "yes"
    )


def discover_hooks_from_entry_points() -> dict[str, hooks_config.HooksConfig]:
    """
    Discover hooks registered via the 'brynhild.hooks' entry point group.

    Entry point format in pyproject.toml:
        [project.entry-points."brynhild.hooks"]
        my-hooks = "my_package:get_hooks"

    The function should return:
        - A HooksConfig instance, OR
        - A dict that validates as HooksConfig

    Can be disabled by setting BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS=1.

    Returns:
        Dict mapping entry point name to HooksConfig.
    """
    if _entry_points_disabled():
        _logger.debug("Entry point hooks discovery disabled by environment variable")
        return {}

    hooks: dict[str, hooks_config.HooksConfig] = {}

    eps = _meta.entry_points(group="brynhild.hooks")

    for ep in eps:
        try:
            hook_provider = ep.load()

            # Call if callable, otherwise use as-is
            result = hook_provider() if callable(hook_provider) else hook_provider

            if isinstance(result, hooks_config.HooksConfig):
                hooks[ep.name] = result
            elif isinstance(result, dict):
                # Validate dict as HooksConfig
                hooks[ep.name] = hooks_config.HooksConfig.model_validate(result)
            else:
                _logger.warning(
                    "Entry point '%s' returned unexpected type: %s "
                    "(expected HooksConfig or dict)",
                    ep.name,
                    type(result).__name__,
                )
                continue

            _logger.debug(
                "Discovered hooks from entry point '%s' (package: %s)",
                ep.name,
                getattr(ep.dist, "name", "unknown") if ep.dist else "unknown",
            )
        except Exception as e:
            _logger.warning(
                "Failed to load hooks from entry point '%s': %s",
                ep.name,
                e,
            )

    return hooks


def load_plugin_hooks(
    plugin: manifest.Plugin,
) -> hooks_config.HooksConfig | None:
    """
    Load hooks from a plugin's hooks.yaml file.

    Note: Entry-point plugins should use the 'brynhild.hooks' entry point
    group instead, as they don't have a filesystem path.

    Args:
        plugin: Plugin to load hooks from.

    Returns:
        Parsed HooksConfig, or None if plugin has no hooks.
    """
    if not plugin.has_hooks():
        return None

    # Entry-point plugins don't have filesystem paths
    if plugin.is_packaged:
        return None

    hooks_path = plugin.hooks_path
    if not hooks_path.exists():
        return None

    try:
        return hooks_config.load_hooks_yaml(hooks_path)
    except (FileNotFoundError, ValueError):
        return None


def _merge_hooks_config(
    merged_hooks: dict[str, list[hooks_config.HookDefinition]],
    config: hooks_config.HooksConfig,
) -> None:
    """
    Merge a HooksConfig into the merged_hooks dict (in-place).

    Args:
        merged_hooks: Dict to merge into (modified in place).
        config: Config to merge from.
    """
    for event_name, hooks_list in config.hooks.items():
        if event_name not in merged_hooks:
            merged_hooks[event_name] = []

        # Get existing hook names for this event
        existing_names = {h.name for h in merged_hooks[event_name]}

        for hook in hooks_list:
            if hook.name in existing_names:
                # Later hooks override earlier ones with same name
                merged_hooks[event_name] = [
                    h if h.name != hook.name else hook
                    for h in merged_hooks[event_name]
                ]
            else:
                # Append new hook
                merged_hooks[event_name].append(hook)


def merge_plugin_hooks(
    base_config: hooks_config.HooksConfig,
    plugins: list[manifest.Plugin],
) -> hooks_config.HooksConfig:
    """
    Merge plugin hooks into the base hooks configuration.

    Plugin hooks are added after standalone hooks. Sources in order:
    1. Directory-based plugin hooks (from hooks.yaml)
    2. Entry-point hooks (from brynhild.hooks entry points)

    Hooks from later sources override earlier ones with the same name.

    Args:
        base_config: Base hooks configuration (standalone hooks).
        plugins: List of plugins to load hooks from.

    Returns:
        Merged HooksConfig with plugin hooks appended.
    """
    # Start with a copy of base config hooks
    merged_hooks: dict[str, list[hooks_config.HookDefinition]] = {}
    for event_name, hooks_list in base_config.hooks.items():
        merged_hooks[event_name] = list(hooks_list)

    # Add hooks from directory-based plugins
    for plugin in plugins:
        plugin_config = load_plugin_hooks(plugin)
        if plugin_config is not None:
            _merge_hooks_config(merged_hooks, plugin_config)

    # Add hooks from entry points (highest priority among plugins)
    entry_point_hooks = discover_hooks_from_entry_points()
    for _ep_name, ep_config in entry_point_hooks.items():
        _merge_hooks_config(merged_hooks, ep_config)

    return hooks_config.HooksConfig(hooks=merged_hooks)


def load_merged_config_with_plugins(
    project_root: _pathlib.Path | None = None,
    plugins: list[manifest.Plugin] | None = None,
) -> hooks_config.HooksConfig:
    """
    Load and merge hooks from all sources.

    Sources in order (earlier sources have lower priority):
    1. Global hooks (~/.config/brynhild/hooks.yaml)
    2. Project hooks (.brynhild/hooks.yaml)
    3. Directory-based plugin hooks (from enabled plugins)
    4. Entry-point hooks (brynhild.hooks entry points) - always included

    Args:
        project_root: Project root directory.
        plugins: List of enabled plugins. If None, no directory plugins loaded.

    Returns:
        Merged HooksConfig.
    """
    # Load standalone hooks (global + project)
    base_config = hooks_config.load_merged_config(project_root)

    # Always merge plugin hooks (includes both directory-based and entry-point)
    # Pass empty list if no directory plugins to still get entry-point hooks
    return merge_plugin_hooks(base_config, plugins or [])

