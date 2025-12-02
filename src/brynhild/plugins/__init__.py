"""
Plugin system for Brynhild.

Plugins are packages that extend Brynhild with:
- Slash commands (commands/*.md)
- Custom tools (tools/*.py)
- Hooks (hooks.yaml)
- Skills (skills/**/SKILL.md)
- LLM providers (providers/*.py)

Plugin discovery locations (in priority order):
1. ~/.config/brynhild/plugins/ - User plugins
2. $BRYNHILD_PLUGIN_PATH - Custom paths (colon-separated)
3. Project .brynhild/plugins/ - Project-local plugins
"""

from brynhild.plugins.commands import Command, CommandFrontmatter, CommandLoader
from brynhild.plugins.discovery import (
    PluginDiscovery,
    get_global_plugins_path,
    get_plugin_search_paths,
    get_project_plugins_path,
)
from brynhild.plugins.hooks import (
    load_merged_config_with_plugins,
    load_plugin_hooks,
    merge_plugin_hooks,
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
    get_global_rules_path,
    load_global_rules,
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
    "load_merged_config_with_plugins",
    "load_plugin_hooks",
    "merge_plugin_hooks",
    # Rules
    "RULE_FILES",
    "RulesManager",
    "discover_rule_files",
    "get_global_rules_path",
    "load_global_rules",
    "load_rule_file",
    # Path helpers
    "get_global_plugins_path",
    "get_plugin_search_paths",
    "get_project_plugins_path",
]

