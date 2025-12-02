"""
Base classes for the tool system.

Tools are the primary way the LLM interacts with the outside world.
Each tool has a name, description, input schema, and execute method.
"""

from __future__ import annotations

import abc as _abc
import dataclasses as _dataclasses
import pathlib as _pathlib
import typing as _typing

if _typing.TYPE_CHECKING:
    import brynhild.tools.sandbox as _sandbox


@_dataclasses.dataclass
class ToolResult:
    """
    Result of executing a tool.

    All tools return this standardized result format.
    """

    success: bool
    output: str
    error: str | None = None

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


class Tool(_abc.ABC):
    """
    Abstract base class for all tools.

    Subclasses must implement:
    - name (property): The tool's identifier (used in API calls)
    - description (property): Human-readable description for the LLM
    - input_schema (property): JSON schema for input validation
    - execute(): The actual tool implementation
    """

    @property
    @_abc.abstractmethod
    def name(self) -> str:
        """Tool name (e.g., 'Bash', 'Read', 'Grep')."""
        ...

    @property
    @_abc.abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM."""
        ...

    @property
    @_abc.abstractmethod
    def input_schema(self) -> dict[str, _typing.Any]:
        """
        JSON schema for tool input.

        This schema is sent to the LLM to describe what parameters
        the tool accepts.
        """
        ...

    @_abc.abstractmethod
    async def execute(self, input: dict[str, _typing.Any]) -> ToolResult:
        """
        Execute the tool with the given input.

        Args:
            input: Dictionary matching the input schema

        Returns:
            ToolResult with success status, output, and optional error
        """
        ...

    @property
    def requires_permission(self) -> bool:
        """
        Whether this tool requires user permission before execution.

        Read-only inspection tools can return False to skip the permission
        dialog. Tools that modify the filesystem, execute commands, or
        access the network should return True (the default).

        Returns:
            True if user permission is required, False for safe read-only tools
        """
        return True

    def to_api_format(self) -> dict[str, _typing.Any]:
        """
        Convert to Anthropic API tool format.

        This format is used when sending tool definitions to the LLM.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_format(self) -> dict[str, _typing.Any]:
        """
        Convert to OpenAI/OpenRouter API format.

        OpenAI uses a slightly different schema structure.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def __repr__(self) -> str:
        return f"<Tool {self.name}>"

    def _require_input(
        self,
        input: dict[str, _typing.Any],
        key: str,
        *,
        label: str | None = None,
    ) -> str | ToolResult:
        """
        Get a required input value, returning an error ToolResult if missing.

        This is a convenience method to reduce boilerplate for required field
        validation at the start of execute() methods.

        Args:
            input: The input dictionary from execute()
            key: The key to look up
            label: Human-readable name for error messages (defaults to key)

        Returns:
            The input value if present and non-empty, or a ToolResult error
        """
        value: str = input.get(key, "")
        if not value:
            return ToolResult(
                success=False,
                output="",
                error=f"No {label or key} provided",
            )
        return value


class SandboxMixin:
    """
    Mixin providing common sandbox configuration handling for tools.

    Tools that need sandbox path validation should inherit from this mixin
    and call super().__init__() to set up the base_dir and sandbox_config.

    Attributes:
        _base_dir: Base directory for relative path resolution
        _sandbox_config: Sandbox configuration (or None for lazy initialization)
    """

    _base_dir: _pathlib.Path
    _sandbox_config: _sandbox.SandboxConfig | None

    def _get_sandbox_config(self) -> _sandbox.SandboxConfig:
        """
        Get or create sandbox configuration.

        Returns the configured SandboxConfig, or creates a default one
        using the base directory as the project root.
        """
        import brynhild.tools.sandbox as sandbox

        if self._sandbox_config is None:
            self._sandbox_config = sandbox.SandboxConfig(project_root=self._base_dir)
        return self._sandbox_config

    def _resolve_and_validate(
        self,
        path: str,
        operation: _typing.Literal["read", "write"],
    ) -> _pathlib.Path:
        """
        Resolve a path and validate it against sandbox rules.

        Args:
            path: Path string (may be relative, may contain ~)
            operation: The type of operation (read or write)

        Returns:
            Resolved absolute path

        Raises:
            PathValidationError: If the path is not allowed
        """
        import brynhild.tools.sandbox as sandbox

        config = self._get_sandbox_config()
        return sandbox.resolve_and_validate(path, self._base_dir, config, operation)

    def _resolve_path_or_error(
        self,
        path: str,
        operation: _typing.Literal["read", "write"],
    ) -> _pathlib.Path | ToolResult:
        """
        Resolve a path, returning a ToolResult error if validation fails.

        This is a convenience method that wraps _resolve_and_validate
        and returns a ToolResult on error instead of raising.

        Args:
            path: Path string (may be relative, may contain ~)
            operation: The type of operation (read or write)

        Returns:
            Resolved absolute path, or ToolResult with error
        """
        import brynhild.tools.sandbox as sandbox

        try:
            return self._resolve_and_validate(path, operation)
        except sandbox.PathValidationError as e:
            return ToolResult(success=False, output="", error=str(e))

