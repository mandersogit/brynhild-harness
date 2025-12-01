"""
Slash command parsing from markdown files.

Commands are defined in plugin commands/ directories as markdown files
with YAML frontmatter. The frontmatter defines metadata, and the body
is the command template injected as a system message.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import os as _os
import pathlib as _pathlib
import re as _re
import typing as _typing

import pydantic as _pydantic
import yaml as _yaml

# Regex to extract YAML frontmatter from markdown
_FRONTMATTER_RE = _re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?(.*)$",
    _re.DOTALL,
)


class CommandFrontmatter(_pydantic.BaseModel):
    """
    Frontmatter parsed from a command markdown file.

    Required fields:
    - name: Command name (what user types after /)

    Optional fields control command behavior.
    """

    model_config = _pydantic.ConfigDict(extra="forbid")

    name: str = _pydantic.Field(
        ...,
        min_length=1,
        max_length=64,
        description="Command name (user types /name)",
    )

    description: str = _pydantic.Field(
        default="",
        max_length=512,
        description="Short description shown in help",
    )

    aliases: list[str] = _pydantic.Field(
        default_factory=list,
        description="Alternative names for the command",
    )

    args: str = _pydantic.Field(
        default="",
        description="Argument specification (e.g., '<target>')",
    )


@_dataclasses.dataclass
class Command:
    """
    A parsed slash command ready for execution.

    The command body is a template that can include variables
    like {{args}}, {{cwd}}, {{file}}, etc.
    """

    frontmatter: CommandFrontmatter
    """Parsed frontmatter metadata."""

    body: str
    """Command template (markdown body after frontmatter)."""

    path: _pathlib.Path
    """Path to the source .md file."""

    plugin_name: str = ""
    """Name of the plugin that provides this command (if any)."""

    @property
    def name(self) -> str:
        """Command name from frontmatter."""
        return self.frontmatter.name

    @property
    def description(self) -> str:
        """Command description from frontmatter."""
        return self.frontmatter.description

    @property
    def aliases(self) -> list[str]:
        """Command aliases from frontmatter."""
        return self.frontmatter.aliases

    def render(
        self,
        args: str = "",
        **context: _typing.Any,
    ) -> str:
        """
        Render the command template with variable substitution.

        Args:
            args: Arguments passed to the command.
            **context: Additional context variables.

        Returns:
            Rendered command body with variables substituted.
        """
        # Build context with defaults
        render_context = {
            "args": args,
            "cwd": str(_pathlib.Path.cwd()),
            **context,
        }

        # Add environment variable access
        # Handle {{env.VAR}} patterns
        result = self.body
        for match in _re.finditer(r"\{\{env\.([^}]+)\}\}", result):
            var_name = match.group(1)
            var_value = _os.environ.get(var_name, "")
            result = result.replace(match.group(0), var_value)

        # Substitute simple {{var}} patterns
        for key, value in render_context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))

        return result

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "aliases": self.aliases,
            "args": self.frontmatter.args,
            "path": str(self.path),
            "plugin_name": self.plugin_name,
        }


def parse_command_markdown(content: str) -> tuple[CommandFrontmatter, str]:
    """
    Parse a command markdown file into frontmatter and body.

    Args:
        content: Raw markdown content.

    Returns:
        Tuple of (frontmatter, body).

    Raises:
        ValueError: If frontmatter is missing or invalid.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError("Command file must have YAML frontmatter (---)")

    frontmatter_yaml = match.group(1)
    body = match.group(2).strip()

    try:
        data = _yaml.safe_load(frontmatter_yaml) or {}
        frontmatter = CommandFrontmatter.model_validate(data)
    except _yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}") from e
    except _pydantic.ValidationError as e:
        raise ValueError(f"Invalid command frontmatter: {e}") from e

    return frontmatter, body


def load_command(path: _pathlib.Path, plugin_name: str = "") -> Command:
    """
    Load a command from a markdown file.

    Args:
        path: Path to the .md file.
        plugin_name: Name of the providing plugin (if any).

    Returns:
        Parsed Command instance.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Command file not found: {path}")

    content = path.read_text(encoding="utf-8")
    frontmatter, body = parse_command_markdown(content)

    return Command(
        frontmatter=frontmatter,
        body=body,
        path=path,
        plugin_name=plugin_name,
    )


class CommandLoader:
    """
    Loads commands from plugin command directories.

    Scans the commands/ directory of a plugin and loads all .md files
    as commands.
    """

    def load_from_directory(
        self,
        commands_dir: _pathlib.Path,
        plugin_name: str = "",
    ) -> dict[str, Command]:
        """
        Load all commands from a directory.

        Args:
            commands_dir: Path to commands/ directory.
            plugin_name: Name of the providing plugin.

        Returns:
            Dict mapping command name to Command instance.
            Includes aliases as separate entries pointing to same command.
        """
        commands: dict[str, Command] = {}

        if not commands_dir.is_dir():
            return commands

        for md_file in sorted(commands_dir.glob("*.md")):
            try:
                command = load_command(md_file, plugin_name)
                # Primary name
                commands[command.name] = command
                # Aliases
                for alias in command.aliases:
                    commands[alias] = command
            except (FileNotFoundError, ValueError):
                # Skip invalid command files
                continue

        return commands

    def load_from_plugin(
        self,
        plugin_path: _pathlib.Path,
        plugin_name: str,
    ) -> dict[str, Command]:
        """
        Load commands from a plugin directory.

        Args:
            plugin_path: Root path of the plugin.
            plugin_name: Plugin name.

        Returns:
            Dict mapping command name to Command.
        """
        commands_dir = plugin_path / "commands"
        return self.load_from_directory(commands_dir, plugin_name)

