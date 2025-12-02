"""
Grep tool using ripgrep for fast file searching.

Provides powerful regex-based search across files with sandbox path validation.
"""

from __future__ import annotations

import asyncio as _asyncio
import pathlib as _pathlib
import shutil as _shutil
import typing as _typing

import brynhild.tools.base as base
import brynhild.tools.sandbox as sandbox


class GrepTool(base.Tool, base.SandboxMixin):
    """
    Search files using ripgrep.

    Features:
    - Regex pattern matching
    - Context lines (before/after)
    - File type filtering
    - Glob patterns
    - Multiple output modes
    - Sandbox path validation (restricted to project directory)
    """

    def __init__(
        self,
        base_dir: _pathlib.Path | None = None,
        ripgrep_path: str | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
    ) -> None:
        """
        Initialize the grep tool.

        Args:
            base_dir: Base directory for searches (default: cwd)
            ripgrep_path: Path to ripgrep binary (default: find in PATH)
            sandbox_config: Sandbox configuration for path validation
        """
        self._base_dir = base_dir or _pathlib.Path.cwd()
        self._ripgrep_path = ripgrep_path or _shutil.which("rg")
        self._sandbox_config = sandbox_config

    @property
    def name(self) -> str:
        return "Grep"

    @property
    def description(self) -> str:
        return (
            "Search for a pattern in files using ripgrep. "
            "Supports regex, context lines, file type filtering, and glob patterns. "
            "Searches are restricted to the project directory."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def categories(self) -> list[str]:
        return ["search", "filesystem"]

    @property
    def requires_permission(self) -> bool:
        return False  # Read-only search tool

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: current directory)",
                },
                "-i": {
                    "type": "boolean",
                    "description": "Case insensitive search",
                },
                "-A": {
                    "type": "integer",
                    "description": "Lines of context after match",
                },
                "-B": {
                    "type": "integer",
                    "description": "Lines of context before match",
                },
                "-C": {
                    "type": "integer",
                    "description": "Lines of context before and after match",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')",
                },
                "type": {
                    "type": "string",
                    "description": "File type to search (e.g., 'py', 'js', 'rust')",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output mode: content (default), files_with_matches, or count",
                },
                "head_limit": {
                    "type": "integer",
                    "description": "Limit output to first N lines/entries",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Execute a ripgrep search."""
        pattern = input.get("pattern", "")
        if not pattern:
            return base.ToolResult(
                success=False,
                output="",
                error="No pattern provided",
            )

        if not self._ripgrep_path:
            return base.ToolResult(
                success=False,
                output="",
                error="ripgrep (rg) not found in PATH",
            )

        # Validate search path (uses SandboxMixin)
        search_path_input = input.get("path", ".")
        try:
            validated_path = self._resolve_and_validate(search_path_input, "read")
        except sandbox.PathValidationError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        # Build command
        args = [self._ripgrep_path]

        # Output mode
        output_mode = input.get("output_mode", "content")
        if output_mode == "files_with_matches":
            args.append("-l")
        elif output_mode == "count":
            args.append("-c")

        # Options
        if input.get("-i"):
            args.append("-i")
        if input.get("-A"):
            args.extend(["-A", str(input["-A"])])
        if input.get("-B"):
            args.extend(["-B", str(input["-B"])])
        if input.get("-C"):
            args.extend(["-C", str(input["-C"])])
        if input.get("glob"):
            args.extend(["--glob", input["glob"]])
        if input.get("type"):
            args.extend(["--type", input["type"]])

        # Add line numbers for content mode
        if output_mode == "content":
            args.append("-n")

        # Pattern and validated path
        args.append(pattern)
        args.append(str(validated_path))

        try:
            proc = await _asyncio.create_subprocess_exec(
                *args,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
                cwd=str(self._base_dir),
            )

            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")

            # Apply head limit
            head_limit = input.get("head_limit")
            if head_limit and output:
                lines = output.splitlines()
                if len(lines) > head_limit:
                    lines = lines[:head_limit]
                    lines.append(f"... (truncated, showing first {head_limit} lines)")
                output = "\n".join(lines)

            # ripgrep returns 1 for no matches (not an error)
            if proc.returncode == 1 and not error:
                return base.ToolResult(
                    success=True,
                    output="No matches found",
                    error=None,
                )

            if proc.returncode != 0 and proc.returncode != 1:
                return base.ToolResult(
                    success=False,
                    output="",
                    error=error or f"ripgrep exited with code {proc.returncode}",
                )

            return base.ToolResult(
                success=True,
                output=output.rstrip(),
                error=None,
            )

        except FileNotFoundError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"ripgrep not found at: {self._ripgrep_path}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to execute ripgrep: {e}",
            )
