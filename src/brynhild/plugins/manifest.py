"""
Plugin manifest parsing.

Plugins are defined by a plugin.yaml manifest file that specifies
metadata and what components the plugin provides.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import pathlib as _pathlib
import typing as _typing

import pydantic as _pydantic
import yaml as _yaml


class PluginManifest(_pydantic.BaseModel):
    """
    Plugin manifest parsed from plugin.yaml.

    Required fields:
    - name: Unique plugin identifier
    - version: Semantic version string

    Optional fields specify what the plugin provides.
    """

    model_config = _pydantic.ConfigDict(extra="forbid")

    # Required metadata
    name: str = _pydantic.Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        description="Plugin name (lowercase, hyphens allowed)",
    )

    version: str = _pydantic.Field(
        ...,
        min_length=1,
        description="Semantic version (e.g., '1.0.0')",
    )

    # Optional metadata
    description: str = _pydantic.Field(
        default="",
        max_length=1024,
        description="What the plugin does",
    )

    author: str = _pydantic.Field(
        default="",
        description="Plugin author",
    )

    license: str = _pydantic.Field(
        default="",
        description="Plugin license (e.g., 'MIT')",
    )

    # Component declarations (what the plugin provides)
    commands: list[str] = _pydantic.Field(
        default_factory=list,
        description="Slash commands provided (e.g., ['build', 'deploy'])",
    )

    tools: list[str] = _pydantic.Field(
        default_factory=list,
        description="Custom tools provided (e.g., ['my_tool'])",
    )

    hooks: bool = _pydantic.Field(
        default=False,
        description="Whether plugin provides hooks (hooks.yaml)",
    )

    skills: list[str] = _pydantic.Field(
        default_factory=list,
        description="Skills provided (e.g., ['my-skill'])",
    )

    providers: list[str] = _pydantic.Field(
        default_factory=list,
        description="LLM providers provided (e.g., ['my_provider'])",
    )

    rules: list[str] = _pydantic.Field(
        default_factory=list,
        description="Rule files provided (e.g., ['coding-standards.md'])",
    )

    # Dependencies and compatibility
    brynhild_version: str = _pydantic.Field(
        default=">=0.1.0",
        description="Required Brynhild version",
    )


@_dataclasses.dataclass
class Plugin:
    """
    A loaded plugin with manifest and path.

    This is the runtime representation of a plugin, combining
    the parsed manifest with the filesystem location.
    """

    manifest: PluginManifest
    """Parsed plugin.yaml manifest."""

    path: _pathlib.Path
    """Path to plugin directory."""

    enabled: bool = True
    """Whether the plugin is enabled."""

    @property
    def name(self) -> str:
        """Plugin name from manifest."""
        return self.manifest.name

    @property
    def version(self) -> str:
        """Plugin version from manifest."""
        return self.manifest.version

    @property
    def description(self) -> str:
        """Plugin description from manifest."""
        return self.manifest.description

    @property
    def commands_path(self) -> _pathlib.Path:
        """Path to commands/ directory."""
        return self.path / "commands"

    @property
    def tools_path(self) -> _pathlib.Path:
        """Path to tools/ directory."""
        return self.path / "tools"

    @property
    def hooks_path(self) -> _pathlib.Path:
        """Path to hooks.yaml file."""
        return self.path / "hooks.yaml"

    @property
    def skills_path(self) -> _pathlib.Path:
        """Path to skills/ directory."""
        return self.path / "skills"

    @property
    def providers_path(self) -> _pathlib.Path:
        """Path to providers/ directory."""
        return self.path / "providers"

    @property
    def rules_path(self) -> _pathlib.Path:
        """Path to rules/ directory."""
        return self.path / "rules"

    def has_commands(self) -> bool:
        """Whether plugin declares commands."""
        return bool(self.manifest.commands)

    def has_tools(self) -> bool:
        """Whether plugin declares tools."""
        return bool(self.manifest.tools)

    def has_hooks(self) -> bool:
        """Whether plugin declares hooks."""
        return self.manifest.hooks

    def has_skills(self) -> bool:
        """Whether plugin declares skills."""
        return bool(self.manifest.skills)

    def has_providers(self) -> bool:
        """Whether plugin declares providers."""
        return bool(self.manifest.providers)

    def has_rules(self) -> bool:
        """Whether plugin declares rules."""
        return bool(self.manifest.rules)

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "path": str(self.path),
            "enabled": self.enabled,
            "commands": self.manifest.commands,
            "tools": self.manifest.tools,
            "hooks": self.manifest.hooks,
            "skills": self.manifest.skills,
            "providers": self.manifest.providers,
            "rules": self.manifest.rules,
        }


def load_manifest(path: _pathlib.Path) -> PluginManifest:
    """
    Load a plugin manifest from plugin.yaml.

    Args:
        path: Path to plugin.yaml file.

    Returns:
        Parsed PluginManifest.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is invalid YAML or doesn't match schema.
    """
    if not path.exists():
        raise FileNotFoundError(f"Plugin manifest not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
        data = _yaml.safe_load(content)
        if data is None:
            raise ValueError(f"Empty manifest file: {path}")
        return PluginManifest.model_validate(data)
    except _yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e
    except _pydantic.ValidationError as e:
        raise ValueError(f"Invalid plugin manifest in {path}: {e}") from e

