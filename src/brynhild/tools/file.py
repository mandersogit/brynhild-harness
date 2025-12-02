"""
File operation tools: Read, Write, Edit.

These tools provide safe file system access with proper error handling
and sandbox path validation to prevent writes outside the project directory.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import brynhild.tools.base as base
import brynhild.tools.sandbox as sandbox


class FileReadTool(base.Tool, base.SandboxMixin):
    """
    Read file contents.

    Supports:
    - Full file reading
    - Line number prefixing
    - Offset and limit for partial reads
    - Blocks reads from sensitive paths
    """

    def __init__(
        self,
        base_dir: _pathlib.Path | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
    ) -> None:
        """
        Initialize the file read tool.

        Args:
            base_dir: Base directory for relative paths (default: cwd)
            sandbox_config: Sandbox configuration for path validation
        """
        self._base_dir = base_dir or _pathlib.Path.cwd()
        self._sandbox_config = sandbox_config

    @property
    def name(self) -> str:
        return "Read"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Returns the file content with line numbers. "
            "Use offset and limit for partial reads of large files."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read (relative or absolute)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Read a file and return its contents with line numbers."""
        file_path = input.get("file_path", "")
        if not file_path:
            return base.ToolResult(
                success=False,
                output="",
                error="No file_path provided",
            )

        offset = input.get("offset", 0)
        limit = input.get("limit")

        # Resolve and validate path (uses SandboxMixin)
        try:
            path = self._resolve_and_validate(file_path, "read")
        except sandbox.PathValidationError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        try:
            if not path.exists():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {file_path}",
                )

            if not path.is_file():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Not a file: {file_path}",
                )

            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)

            # Apply offset and limit
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]

            # Add line numbers (1-indexed, accounting for offset)
            numbered_lines = []
            for i, line in enumerate(lines):
                line_num = i + offset + 1
                # Right-align line numbers in 6-character field
                numbered_lines.append(f"{line_num:6}|{line}")

            output = "".join(numbered_lines)
            if not output:
                output = "(empty file)"

            return base.ToolResult(
                success=True,
                output=output.rstrip(),
                error=None,
            )

        except PermissionError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {file_path}",
            )
        except UnicodeDecodeError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"File is not valid UTF-8: {file_path}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to read file: {e}",
            )


class FileWriteTool(base.Tool, base.SandboxMixin):
    """
    Write or create files.

    Creates parent directories as needed.
    Overwrites existing files.
    Validates paths against sandbox rules.
    """

    def __init__(
        self,
        base_dir: _pathlib.Path | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the file write tool.

        Args:
            base_dir: Base directory for relative paths (default: cwd)
            sandbox_config: Sandbox configuration for path validation
            dry_run: If True, don't actually write files
        """
        self._base_dir = base_dir or _pathlib.Path.cwd()
        self._sandbox_config = sandbox_config
        self._dry_run = dry_run

    @property
    def name(self) -> str:
        return "Write"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Creates the file if it doesn't exist. "
            "Creates parent directories as needed. Overwrites existing content."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write (relative or absolute)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Write content to a file."""
        file_path = input.get("file_path", "")
        content = input.get("content", "")

        if not file_path:
            return base.ToolResult(
                success=False,
                output="",
                error="No file_path provided",
            )

        # Resolve and validate path (uses SandboxMixin)
        try:
            path = self._resolve_and_validate(file_path, "write")
        except sandbox.PathValidationError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        # Handle dry-run mode
        if self._dry_run:
            return base.ToolResult(
                success=True,
                output=f"[DRY RUN] Would write {len(content)} bytes to {file_path}",
                error=None,
            )

        try:
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            path.write_text(content, encoding="utf-8")

            return base.ToolResult(
                success=True,
                output=f"Wrote {len(content)} bytes to {file_path}",
                error=None,
            )

        except PermissionError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {file_path}",
            )
        except IsADirectoryError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Path is a directory: {file_path}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to write file: {e}",
            )


class FileEditTool(base.Tool, base.SandboxMixin):
    """
    Edit files using search and replace.

    Supports:
    - Single occurrence replacement (default, requires unique match)
    - Replace all occurrences
    - Validates paths against sandbox rules
    """

    def __init__(
        self,
        base_dir: _pathlib.Path | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the file edit tool.

        Args:
            base_dir: Base directory for relative paths (default: cwd)
            sandbox_config: Sandbox configuration for path validation
            dry_run: If True, don't actually edit files
        """
        self._base_dir = base_dir or _pathlib.Path.cwd()
        self._sandbox_config = sandbox_config
        self._dry_run = dry_run

    @property
    def name(self) -> str:
        return "Edit"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing text. By default, the old_string must "
            "appear exactly once in the file. Use replace_all to replace all occurrences."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "Text to search for and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "Text to replace with",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Edit a file by replacing text."""
        file_path = input.get("file_path", "")
        old_string = input.get("old_string", "")
        new_string = input.get("new_string", "")
        replace_all = input.get("replace_all", False)

        if not file_path:
            return base.ToolResult(
                success=False,
                output="",
                error="No file_path provided",
            )

        if not old_string:
            return base.ToolResult(
                success=False,
                output="",
                error="No old_string provided",
            )

        # Resolve and validate path (uses SandboxMixin)
        try:
            path = self._resolve_and_validate(file_path, "write")
        except sandbox.PathValidationError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        try:
            if not path.exists():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {file_path}",
                )

            if not path.is_file():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Not a file: {file_path}",
                )

            content = path.read_text(encoding="utf-8")

            # Check if old_string exists
            if old_string not in content:
                return base.ToolResult(
                    success=False,
                    output="",
                    error="old_string not found in file",
                )

            # Check uniqueness for single replacement
            count = content.count(old_string)
            if not replace_all and count > 1:
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"old_string found {count} times, must be unique (or use replace_all)",
                )

            # Handle dry-run mode
            if self._dry_run:
                return base.ToolResult(
                    success=True,
                    output=f"[DRY RUN] Would replace {count} occurrence(s) in {file_path}",
                    error=None,
                )

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            # Write back
            path.write_text(new_content, encoding="utf-8")

            return base.ToolResult(
                success=True,
                output=f"Replaced {count} occurrence(s) in {file_path}",
                error=None,
            )

        except PermissionError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {file_path}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to edit file: {e}",
            )
