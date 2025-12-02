"""
Glob tool for file pattern matching.

Finds files matching glob patterns with sandbox path validation.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import brynhild.tools.base as base
import brynhild.tools.sandbox as sandbox


class GlobTool(base.Tool, base.SandboxMixin):
    """
    Find files matching glob patterns.

    Returns matching file paths sorted by modification time.
    Searches are restricted to the project directory.
    """

    def __init__(
        self,
        base_dir: _pathlib.Path | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
    ) -> None:
        """
        Initialize the glob tool.

        Args:
            base_dir: Base directory for searches (default: cwd)
            sandbox_config: Sandbox configuration for path validation
        """
        self._base_dir = base_dir or _pathlib.Path.cwd()
        self._sandbox_config = sandbox_config

    @property
    def name(self) -> str:
        return "Glob"

    @property
    def description(self) -> str:
        return (
            "Find files matching a glob pattern. "
            "Returns file paths sorted by modification time (newest first). "
            "Searches are restricted to the project directory."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.js')",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current directory)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Find files matching a glob pattern."""
        pattern = input.get("pattern", "")
        if not pattern:
            return base.ToolResult(
                success=False,
                output="",
                error="No pattern provided",
            )

        search_path_input = input.get("path", ".")
        limit = input.get("limit")

        # Validate search path (uses SandboxMixin)
        try:
            base_path = self._resolve_and_validate(search_path_input, "read")
        except sandbox.PathValidationError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        try:
            if not base_path.exists():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {search_path_input}",
                )

            if not base_path.is_dir():
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Not a directory: {search_path_input}",
                )

            # Auto-prepend **/ if pattern doesn't start with it
            # This makes patterns like "*.py" work recursively
            if not pattern.startswith("**/") and not pattern.startswith("/"):
                pattern = "**/" + pattern

            # Find matching files
            matches = list(base_path.glob(pattern))

            # Filter to files only (exclude directories)
            files = [m for m in matches if m.is_file()]

            # Sort by modification time (newest first)
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Apply limit
            if limit:
                files = files[:limit]

            if not files:
                return base.ToolResult(
                    success=True,
                    output="No files found matching pattern",
                    error=None,
                )

            # Format output as relative paths
            output_lines = []
            for f in files:
                try:
                    rel_path = f.relative_to(self._base_dir)
                except ValueError:
                    rel_path = f
                output_lines.append(str(rel_path))

            return base.ToolResult(
                success=True,
                output="\n".join(output_lines),
                error=None,
            )

        except PermissionError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to search files: {e}",
            )
