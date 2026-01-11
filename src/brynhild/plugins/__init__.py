"""
Plugin system for Brynhild.

Plugins are packages that extend Brynhild with:
- Slash commands (commands/*.md or brynhild.commands entry point)
- Custom tools (tools/*.py or brynhild.tools entry point)
- Hooks (hooks.yaml or brynhild.hooks entry point)
- Skills (skills/**/SKILL.md or brynhild.skills entry point)
- LLM providers (providers/*.py or brynhild.providers entry point)
- Rules (rules/*.md or brynhild.rules entry point)

Plugin discovery locations (in priority order):
1. ~/.config/brynhild/plugins/ - User plugins (directory)
2. $BRYNHILD_PLUGIN_PATH - Custom paths (directory, colon-separated)
3. Project .brynhild/plugins/ - Project-local plugins (directory)
4. Entry points (brynhild.*) - Pip-installed plugins (highest priority)
"""

from brynhild.plugins.commands import (
    Command,
    CommandFrontmatter,
    CommandLoader,
    discover_commands_from_entry_points,
)
from brynhild.plugins.discovery import (
    PluginDiscovery,
    get_global_plugins_path,
    get_plugin_search_paths,
    get_project_plugins_path,
)
from brynhild.plugins.hooks import (
    discover_hooks_from_entry_points,
    load_merged_config_with_plugins,
    load_plugin_hooks,
    merge_plugin_hooks,
)
from brynhild.plugins.lifecycle import (
    fire_plugin_init,
    fire_plugin_init_for_all,
    fire_plugin_init_for_all_sync,
    fire_plugin_init_sync,
)
from brynhild.plugins.loader import PluginLoader
from brynhild.plugins.manifest import Plugin, PluginManifest
from brynhild.plugins.providers import (
    ProviderLoader,
    ProviderLoadError,
    get_all_plugin_providers,
    get_plugin_provider,
    load_all_plugin_providers,
    register_plugin_provider,
)
from brynhild.plugins.registry import PluginRegistry
from brynhild.plugins.rules import (
    RULE_FILES,
    RulesManager,
    discover_rule_files,
    discover_rules_from_entry_points,
    get_global_rules_path,
    load_global_rules,
    load_plugin_rules,
    load_rule_file,
)
from brynhild.plugins.stubs import ToolBase, ToolResult
from brynhild.plugins.tools import ToolLoader, ToolLoadError

__all__ = [
    # Manifest and core
    "Plugin",
    "PluginDiscovery",
    "PluginLoader",
    "PluginManifest",
    "PluginRegistry",
    # Commands
    "Command",
    "CommandFrontmatter",
    "CommandLoader",
    "discover_commands_from_entry_points",
    # Tools
    "ToolBase",
    "ToolLoadError",
    "ToolLoader",
    "ToolResult",
    # Providers
    "ProviderLoadError",
    "ProviderLoader",
    "get_all_plugin_providers",
    "get_plugin_provider",
    "load_all_plugin_providers",
    "register_plugin_provider",
    # Hooks
    "discover_hooks_from_entry_points",
    "load_merged_config_with_plugins",
    "load_plugin_hooks",
    "merge_plugin_hooks",
    # Lifecycle
    "fire_plugin_init",
    "fire_plugin_init_for_all",
    "fire_plugin_init_for_all_sync",
    "fire_plugin_init_sync",
    # Rules
    "RULE_FILES",
    "RulesManager",
    "discover_rule_files",
    "discover_rules_from_entry_points",
    "get_global_rules_path",
    "load_global_rules",
    "load_plugin_rules",
    "load_rule_file",
    # Path helpers
    "get_global_plugins_path",
    "get_plugin_search_paths",
    "get_project_plugins_path",
]

