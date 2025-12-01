"""
Plugin hooks integration.

Loads hooks from plugin hooks.yaml files and merges them with
the existing hook configuration. Plugin hooks run after standalone hooks.
"""

from __future__ import annotations

import pathlib as _pathlib

import brynhild.hooks.config as hooks_config
import brynhild.plugins.manifest as manifest


def load_plugin_hooks(
    plugin: manifest.Plugin,
) -> hooks_config.HooksConfig | None:
    """
    Load hooks from a plugin's hooks.yaml file.

    Args:
        plugin: Plugin to load hooks from.

    Returns:
        Parsed HooksConfig, or None if plugin has no hooks.
    """
    if not plugin.has_hooks():
        return None

    hooks_path = plugin.hooks_path
    if not hooks_path.exists():
        return None

    try:
        return hooks_config.load_hooks_yaml(hooks_path)
    except (FileNotFoundError, ValueError):
        return None


def merge_plugin_hooks(
    base_config: hooks_config.HooksConfig,
    plugins: list[manifest.Plugin],
) -> hooks_config.HooksConfig:
    """
    Merge plugin hooks into the base hooks configuration.

    Plugin hooks are added after standalone hooks. Hooks from later
    plugins override earlier plugins with the same name.

    Args:
        base_config: Base hooks configuration (standalone hooks).
        plugins: List of plugins to load hooks from.

    Returns:
        Merged HooksConfig with plugin hooks appended.
    """
    # Start with a copy of base config hooks
    merged_hooks: dict[str, list[hooks_config.HookDefinition]] = {}
    for event_name, hooks in base_config.hooks.items():
        merged_hooks[event_name] = list(hooks)

    # Add hooks from each plugin
    for plugin in plugins:
        plugin_config = load_plugin_hooks(plugin)
        if plugin_config is None:
            continue

        for event_name, plugin_hooks in plugin_config.hooks.items():
            if event_name not in merged_hooks:
                merged_hooks[event_name] = []

            # Get existing hook names for this event
            existing_names = {h.name for h in merged_hooks[event_name]}

            for hook in plugin_hooks:
                if hook.name in existing_names:
                    # Later plugin hooks override earlier ones with same name
                    merged_hooks[event_name] = [
                        h if h.name != hook.name else hook
                        for h in merged_hooks[event_name]
                    ]
                else:
                    # Append new hook
                    merged_hooks[event_name].append(hook)

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
    3. Plugin hooks (from enabled plugins)

    Args:
        project_root: Project root directory.
        plugins: List of enabled plugins. If None, no plugin hooks loaded.

    Returns:
        Merged HooksConfig.
    """
    # Load standalone hooks (global + project)
    base_config = hooks_config.load_merged_config(project_root)

    # Merge plugin hooks if provided
    if plugins:
        return merge_plugin_hooks(base_config, plugins)

    return base_config

