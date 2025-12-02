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


@_dataclasses.dataclass
class ToolMetrics:
    """
    Metrics for a single tool's usage.

    Tracks call counts, durations, and success rates for observability.
    These metrics are accumulated during a session and can be logged
    or stored in session data.
    """

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    last_used: str | None = None  # ISO timestamp

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0.0 to 100.0)."""
        if self.call_count == 0:
            return 0.0
        return (self.success_count / self.call_count) * 100.0

    @property
    def average_duration_ms(self) -> float:
        """Average duration per call in milliseconds."""
        if self.call_count == 0:
            return 0.0
        return self.total_duration_ms / self.call_count

    def record_call(
        self,
        success: bool,
        duration_ms: float,
        timestamp: str | None = None,
    ) -> None:
        """
        Record a tool call.

        Args:
            success: Whether the call succeeded
            duration_ms: How long the call took in milliseconds
            timestamp: ISO timestamp of the call (default: now)
        """
        import datetime as _dt

        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.total_duration_ms += duration_ms
        self.last_used = timestamp or _dt.datetime.now(_dt.UTC).isoformat()

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to JSON-serializable dict."""
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_duration_ms": self.total_duration_ms,
            "average_duration_ms": self.average_duration_ms,
            "success_rate": self.success_rate,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, _typing.Any]) -> ToolMetrics:
        """Create from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            call_count=data.get("call_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            last_used=data.get("last_used"),
        )


class MetricsCollector:
    """
    Collects tool metrics across a session.

    This collector is always on - metrics are recorded for every tool call.
    Metrics can be retrieved for logging, session storage, or CLI display.
    """

    def __init__(self) -> None:
        """Initialize an empty metrics collector."""
        self._metrics: dict[str, ToolMetrics] = {}

    def record(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
        timestamp: str | None = None,
    ) -> None:
        """
        Record a tool call.

        Args:
            tool_name: Name of the tool
            success: Whether the call succeeded
            duration_ms: How long the call took in milliseconds
            timestamp: ISO timestamp of the call (default: now)
        """
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetrics(tool_name=tool_name)
        self._metrics[tool_name].record_call(success, duration_ms, timestamp)

    def get(self, tool_name: str) -> ToolMetrics | None:
        """Get metrics for a specific tool."""
        return self._metrics.get(tool_name)

    def all(self) -> list[ToolMetrics]:
        """Get all tool metrics, sorted by call count (descending)."""
        return sorted(
            self._metrics.values(),
            key=lambda m: m.call_count,
            reverse=True,
        )

    def to_dict(self) -> dict[str, dict[str, _typing.Any]]:
        """Convert all metrics to JSON-serializable dict."""
        return {name: m.to_dict() for name, m in self._metrics.items()}

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, _typing.Any]]) -> MetricsCollector:
        """Create from dictionary."""
        collector = cls()
        for name, metrics_data in data.items():
            collector._metrics[name] = ToolMetrics.from_dict(metrics_data)
        return collector

    def summary(self) -> dict[str, _typing.Any]:
        """Get a summary of all metrics."""
        total_calls = sum(m.call_count for m in self._metrics.values())
        total_success = sum(m.success_count for m in self._metrics.values())
        total_duration = sum(m.total_duration_ms for m in self._metrics.values())

        return {
            "total_calls": total_calls,
            "total_success": total_success,
            "total_failures": total_calls - total_success,
            "success_rate": (total_success / total_calls * 100.0) if total_calls else 0.0,
            "total_duration_ms": total_duration,
            "tools_used": len(self._metrics),
        }


class Tool(_abc.ABC):
    """
    Abstract base class for all tools.

    Subclasses must implement:
    - name (property): The tool's identifier (used in API calls)
    - description (property): Human-readable description for the LLM
    - input_schema (property): JSON schema for input validation
    - execute(): The actual tool implementation

    Optional metadata (override for richer tool information):
    - version (property): Tool version string (default: "0.0.0")
    - categories (property): List of category tags (default: [])
    - examples (property): Usage examples for the LLM (default: [])
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

    # Optional metadata properties with null-ish defaults

    @property
    def version(self) -> str:
        """
        Tool version string.

        Override to track tool versioning. Default is "0.0.0" indicating
        version is not tracked for this tool.

        Returns:
            Semantic version string (e.g., "1.2.3")
        """
        return "0.0.0"

    @property
    def categories(self) -> list[str]:
        """
        Category tags for tool organization.

        Override to categorize tools. Useful for filtering and grouping.
        Common categories: "filesystem", "search", "shell", "network", etc.

        Returns:
            List of category strings
        """
        return []

    @property
    def examples(self) -> list[dict[str, _typing.Any]]:
        """
        Usage examples for the LLM.

        Override to provide examples that help the LLM understand how
        to use the tool effectively. Each example is a dict with:
        - "description": What the example demonstrates
        - "input": Example input dict matching input_schema

        Returns:
            List of example dictionaries
        """
        return []

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

