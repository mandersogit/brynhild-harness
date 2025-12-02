"""
Inspect tool for safe, read-only filesystem inspection.

This tool provides filesystem inspection operations that don't require
user permission because they are read-only and constrained to allowed paths.
"""

from __future__ import annotations

import datetime as _datetime
import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.tools.base as base
import brynhild.tools.sandbox as sandbox


class InspectTool(base.Tool, base.SandboxMixin):
    """
    Inspect the filesystem (read-only, no permission required).

    Operations:
    - cwd: Get current working directory
    - ls: List directory contents with metadata
    - stat: Get file/directory metadata
    - exists: Check if a path exists and its type

    This tool is safe because:
    - All operations are read-only
    - Path validation ensures access only to allowed locations
    - No external commands are executed
    """

    def __init__(
        self,
        working_dir: _pathlib.Path | None = None,
        sandbox_config: sandbox.SandboxConfig | None = None,
    ) -> None:
        """
        Initialize the Inspect tool.

        Args:
            working_dir: Working directory for relative paths
            sandbox_config: Sandbox configuration for path validation
        """
        # SandboxMixin uses _base_dir, but we keep _working_dir for cwd operation
        self._working_dir = working_dir or _pathlib.Path.cwd()
        self._base_dir = self._working_dir
        self._sandbox_config = sandbox_config

    @property
    def name(self) -> str:
        return "Inspect"

    @property
    def description(self) -> str:
        return (
            "Inspect the filesystem (read-only, no permission required). "
            "Use this INSTEAD of Bash for filesystem queries. Operations:\n"
            "- 'cwd': Get current working directory\n"
            "- 'ls': List directory contents with size/mtime. Supports sorting "
            "(sort_by: 'name', 'mtime', 'size') and filtering (filter: 'files', 'dirs')\n"
            "- 'stat': Get detailed file/directory metadata\n"
            "- 'exists': Check if path exists and its type\n"
            "Examples: oldest file (sort_by='mtime', filter='files'), "
            "largest file (sort_by='size', reverse=true, filter='files')"
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def categories(self) -> list[str]:
        return ["filesystem", "read"]

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["cwd", "ls", "stat", "exists"],
                    "description": "The operation to perform",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Path for ls/stat/exists operations. "
                        "Relative paths are resolved from the working directory. "
                        "Default: current directory."
                    ),
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["name", "mtime", "size"],
                    "description": (
                        "For 'ls': Sort entries by 'name' (default), 'mtime' "
                        "(modification time, oldest first), or 'size' (smallest first)"
                    ),
                },
                "reverse": {
                    "type": "boolean",
                    "description": (
                        "For 'ls': Reverse sort order. "
                        "E.g., with sort_by='mtime' and reverse=true, newest first"
                    ),
                },
                "filter": {
                    "type": "string",
                    "enum": ["all", "files", "dirs"],
                    "description": (
                        "For 'ls': Filter to show only 'files', only 'dirs', "
                        "or 'all' (default)"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "For 'ls': Maximum number of entries to return",
                },
            },
            "required": ["operation"],
        }

    @property
    def requires_permission(self) -> bool:
        """Inspect is read-only and safe - no permission required."""
        return False

    @property
    def working_dir(self) -> _pathlib.Path:
        """Get the current working directory."""
        return self._working_dir

    @working_dir.setter
    def working_dir(self, path: _pathlib.Path) -> None:
        """Set the working directory."""
        self._working_dir = path
        self._sandbox_config = sandbox.SandboxConfig(project_root=path)

    def configure_sandbox(self, config: sandbox.SandboxConfig) -> None:
        """Configure the sandbox for path validation."""
        self._sandbox_config = config

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Execute the inspect operation."""
        operation = input.get("operation", "").lower()
        path_str = input.get("path", ".")

        try:
            if operation == "cwd":
                return self._do_cwd()
            elif operation == "ls":
                return self._do_ls(
                    path_str,
                    sort_by=input.get("sort_by", "name"),
                    reverse=input.get("reverse", False),
                    filter_type=input.get("filter", "all"),
                    limit=input.get("limit"),
                )
            elif operation == "stat":
                return self._do_stat(path_str)
            elif operation == "exists":
                return self._do_exists(path_str)
            else:
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown operation: {operation}. "
                    f"Valid operations: cwd, ls, stat, exists",
                )
        except sandbox.PathValidationError as e:
            return base.ToolResult(success=False, output="", error=str(e))
        except PermissionError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except FileNotFoundError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Path not found: {e}",
            )
        except OSError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"OS error: {e}",
            )

    def _resolve_path(self, path_str: str) -> _pathlib.Path:
        """Resolve a path string to an absolute path, validating access."""
        # Uses SandboxMixin's _resolve_and_validate for consistent path handling
        return self._resolve_and_validate(path_str, "read")

    def _do_cwd(self) -> base.ToolResult:
        """Get the current working directory."""
        return base.ToolResult(
            success=True,
            output=str(self._working_dir.resolve()),
        )

    def _do_ls(
        self,
        path_str: str,
        sort_by: str = "name",
        reverse: bool = False,
        filter_type: str = "all",
        limit: int | None = None,
    ) -> base.ToolResult:
        """List directory contents with metadata.

        Args:
            path_str: Directory path to list
            sort_by: Sort by 'name', 'mtime', or 'size'
            reverse: Reverse sort order
            filter_type: 'all', 'files', or 'dirs'
            limit: Maximum entries to return
        """
        path = self._resolve_path(path_str)

        if not path.exists():
            return base.ToolResult(
                success=False,
                output="",
                error=f"Path does not exist: {path}",
            )

        if not path.is_dir():
            return base.ToolResult(
                success=False,
                output="",
                error=f"Not a directory: {path}",
            )

        # Collect entries with metadata
        entries: list[dict[str, _typing.Any]] = []
        for entry in path.iterdir():
            try:
                stat = entry.stat()
                is_dir = entry.is_dir()
                is_symlink = entry.is_symlink()

                # Apply filter
                if filter_type == "files" and is_dir:
                    continue
                if filter_type == "dirs" and not is_dir:
                    continue

                entry_info = {
                    "name": entry.name,
                    "type": "symlink" if is_symlink else ("dir" if is_dir else "file"),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "modified": _datetime.datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(),
                }
                if is_symlink:
                    try:
                        entry_info["target"] = str(entry.resolve())
                    except OSError:
                        entry_info["target"] = "(broken)"
                entries.append(entry_info)
            except (PermissionError, OSError):
                # Skip entries we can't access
                if filter_type == "all":
                    entries.append({
                        "name": entry.name,
                        "type": "unknown",
                        "size": 0,
                        "mtime": 0,
                        "error": "permission denied",
                    })

        # Sort entries
        if sort_by == "mtime":
            entries.sort(key=lambda e: e["mtime"], reverse=reverse)
        elif sort_by == "size":
            entries.sort(key=lambda e: e["size"], reverse=reverse)
        else:  # name
            entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()), reverse=reverse)

        # Apply limit
        total_count = len(entries)
        if limit is not None and limit > 0:
            entries = entries[:limit]

        # Format output
        sort_desc = f"sorted by {sort_by}"
        if reverse:
            sort_desc += " (reversed)"
        if sort_by == "mtime":
            sort_desc = "oldest first" if not reverse else "newest first"
        elif sort_by == "size":
            sort_desc = "smallest first" if not reverse else "largest first"

        filter_desc = ""
        if filter_type == "files":
            filter_desc = ", files only"
        elif filter_type == "dirs":
            filter_desc = ", directories only"

        header = f"Directory: {path}"
        if limit and total_count > limit:
            header += f"\nShowing: {len(entries)} of {total_count} entries ({sort_desc}{filter_desc})"
        else:
            header += f"\nEntries: {len(entries)} ({sort_desc}{filter_desc})"

        output_lines = [header, ""]

        for e in entries:
            if e["type"] == "dir":
                prefix = "📁"
            elif e["type"] == "symlink":
                prefix = "🔗"
            elif e.get("error"):
                prefix = "⚠️"
            else:
                prefix = "📄"

            # Format timestamp nicely
            modified = e.get("modified")
            mtime_str = modified[:19].replace("T", " ") if modified else "unknown"

            if e.get("error"):
                output_lines.append(f"  {prefix} {e['name']} ({e['error']})")
            elif e["type"] == "symlink":
                output_lines.append(
                    f"  {prefix} {e['name']} -> {e.get('target', '?')} [{mtime_str}]"
                )
            elif e["type"] == "dir":
                output_lines.append(f"  {prefix} {e['name']}/ [{mtime_str}]")
            else:
                size = self._format_size(e["size"])
                output_lines.append(f"  {prefix} {e['name']} ({size}) [{mtime_str}]")

        return base.ToolResult(
            success=True,
            output="\n".join(output_lines),
        )

    def _do_stat(self, path_str: str) -> base.ToolResult:
        """Get file/directory metadata."""
        path = self._resolve_path(path_str)

        if not path.exists():
            return base.ToolResult(
                success=False,
                output="",
                error=f"Path does not exist: {path}",
            )

        stat = path.stat()

        info = {
            "path": str(path),
            "name": path.name,
            "type": "directory" if path.is_dir() else "file",
            "size": stat.st_size,
            "size_human": self._format_size(stat.st_size),
            "modified": _datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": _datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "accessed": _datetime.datetime.fromtimestamp(stat.st_atime).isoformat(),
            "mode": oct(stat.st_mode),
            "readable": _os.access(path, _os.R_OK),
            "writable": _os.access(path, _os.W_OK),
            "executable": _os.access(path, _os.X_OK),
        }

        if path.is_symlink():
            info["type"] = "symlink"
            try:
                info["target"] = str(path.resolve())
            except OSError:
                info["target"] = "(broken)"

        # Format output
        output_lines = [
            f"Path: {info['path']}",
            f"Type: {info['type']}",
            f"Size: {info['size_human']} ({info['size']} bytes)",
            f"Modified: {info['modified']}",
            f"Permissions: {'r' if info['readable'] else '-'}"
            f"{'w' if info['writable'] else '-'}"
            f"{'x' if info['executable'] else '-'}",
        ]

        if info["type"] == "symlink":
            output_lines.append(f"Target: {info.get('target', 'unknown')}")

        return base.ToolResult(
            success=True,
            output="\n".join(output_lines),
        )

    def _do_exists(self, path_str: str) -> base.ToolResult:
        """Check if a path exists and what type it is."""
        try:
            path = self._resolve_path(path_str)
        except sandbox.PathValidationError:
            # Path validation failed - it's in a blocked location
            return base.ToolResult(
                success=True,
                output=f"Path is in a restricted location and cannot be accessed: {path_str}",
            )

        exists = path.exists()
        if not exists:
            return base.ToolResult(
                success=True,
                output=f"Path does not exist: {path}",
            )

        if path.is_symlink():
            path_type = "symlink"
        elif path.is_dir():
            path_type = "directory"
        elif path.is_file():
            path_type = "file"
        else:
            path_type = "other"

        return base.ToolResult(
            success=True,
            output=f"Exists: {path}\nType: {path_type}",
        )

    def _format_size(self, size_bytes: int) -> str:
        """Format a size in bytes to human-readable form."""
        size: float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

