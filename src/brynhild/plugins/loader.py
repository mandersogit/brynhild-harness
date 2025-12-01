"""
Plugin loading from directories.

PluginLoader reads a plugin directory and creates a Plugin instance
with the parsed manifest.
"""

from __future__ import annotations

import pathlib as _pathlib

import brynhild.plugins.manifest as manifest


class PluginLoader:
    """
    Loads plugins from directories.

    A valid plugin directory must contain:
    - plugin.yaml (required) - Plugin manifest

    May optionally contain:
    - commands/ - Slash command definitions (*.md)
    - tools/ - Custom tool implementations (*.py)
    - hooks.yaml - Hook definitions
    - skills/ - Skill definitions (*/SKILL.md)
    """

    def load(self, plugin_dir: _pathlib.Path) -> manifest.Plugin:
        """
        Load a plugin from a directory.

        Args:
            plugin_dir: Path to plugin directory.

        Returns:
            Loaded Plugin instance.

        Raises:
            FileNotFoundError: If plugin.yaml doesn't exist.
            ValueError: If manifest is invalid.
        """
        plugin_dir = plugin_dir.resolve()

        if not plugin_dir.is_dir():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        manifest_path = plugin_dir / "plugin.yaml"
        plugin_manifest = manifest.load_manifest(manifest_path)

        return manifest.Plugin(
            manifest=plugin_manifest,
            path=plugin_dir,
            enabled=True,
        )

    def validate(self, plugin_dir: _pathlib.Path) -> list[str]:
        """
        Validate a plugin directory and return any warnings.

        Checks that:
        - plugin.yaml exists and is valid
        - Declared components exist on disk

        Args:
            plugin_dir: Path to plugin directory.

        Returns:
            List of warning messages (empty if fully valid).

        Raises:
            FileNotFoundError: If plugin.yaml doesn't exist.
            ValueError: If manifest is invalid.
        """
        plugin = self.load(plugin_dir)
        warnings: list[str] = []

        # Check declared commands exist
        if plugin.has_commands():
            commands_dir = plugin.commands_path
            if not commands_dir.is_dir():
                warnings.append(
                    "Plugin declares commands but commands/ directory missing"
                )
            else:
                for cmd_name in plugin.manifest.commands:
                    cmd_file = commands_dir / f"{cmd_name}.md"
                    if not cmd_file.exists():
                        warnings.append(f"Declared command not found: {cmd_name}.md")

        # Check declared tools exist
        if plugin.has_tools():
            tools_dir = plugin.tools_path
            if not tools_dir.is_dir():
                warnings.append("Plugin declares tools but tools/ directory missing")
            else:
                for tool_name in plugin.manifest.tools:
                    tool_file = tools_dir / f"{tool_name}.py"
                    if not tool_file.exists():
                        warnings.append(f"Declared tool not found: {tool_name}.py")

        # Check hooks file exists if declared
        if plugin.has_hooks() and not plugin.hooks_path.exists():
            warnings.append("Plugin declares hooks but hooks.yaml missing")

        # Check declared skills exist
        if plugin.has_skills():
            skills_dir = plugin.skills_path
            if not skills_dir.is_dir():
                warnings.append("Plugin declares skills but skills/ directory missing")
            else:
                for skill_name in plugin.manifest.skills:
                    skill_dir = skills_dir / skill_name
                    skill_file = skill_dir / "SKILL.md"
                    if not skill_file.exists():
                        warnings.append(
                            f"Declared skill not found: {skill_name}/SKILL.md"
                        )

        return warnings

