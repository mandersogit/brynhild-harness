"""
Base classes for UI rendering.

Implements a layered rendering system:
- Layer 1: PlainTextRenderer - Just strings, fully testable
- Layer 2: JSONRenderer - Structured output, machine-readable
- Layer 3: RichConsoleRenderer - Colors and formatting
- Layer 4: TextualTUI - Full interactive app (optional, build last)

All renderers implement the same interface, allowing injection for testing.
"""

import abc as _abc
import typing as _typing

# Import display types from core (they are DTOs, not UI-specific)
# Re-exported here for backwards compatibility
import brynhild.core.types as core_types

ToolCallDisplay = core_types.ToolCallDisplay
ToolResultDisplay = core_types.ToolResultDisplay


class Renderer(_abc.ABC):
    """
    Abstract base class for all UI renderers.

    Renderers handle all output operations. By using different renderer
    implementations, we can:
    - Test conversation logic without real output
    - Switch between plain text, JSON, and rich formatting
    - Build interactive TUI on top of the same core logic
    """

    @_abc.abstractmethod
    def show_user_message(self, content: str) -> None:
        """Display a user message."""
        ...

    @_abc.abstractmethod
    def show_assistant_text(self, text: str, *, streaming: bool = False) -> None:
        """
        Display assistant text response.

        Args:
            text: The text content to display.
            streaming: If True, this is a partial chunk during streaming.
                      If False, this is the complete message.
        """
        ...

    @_abc.abstractmethod
    def show_tool_call(self, tool_call: ToolCallDisplay) -> None:
        """Display that a tool is being called."""
        ...

    @_abc.abstractmethod
    def show_tool_result(self, result: ToolResultDisplay) -> None:
        """Display the result of a tool call."""
        ...

    @_abc.abstractmethod
    def show_error(self, error: str) -> None:
        """Display an error message."""
        ...

    @_abc.abstractmethod
    def show_info(self, message: str) -> None:
        """Display an informational message."""
        ...

    @_abc.abstractmethod
    def start_streaming(self) -> None:
        """Called when streaming response starts."""
        ...

    @_abc.abstractmethod
    def end_streaming(self) -> None:
        """Called when streaming response ends."""
        ...

    def prompt_permission(
        self,
        _tool_call: ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        """
        Ask user for permission to execute a tool.

        Args:
            _tool_call: The tool call requesting permission (unused in base).
            auto_approve: If True, automatically approve without prompting.

        Returns:
            True if permission granted, False otherwise.
        """
        # Default implementation: auto-approve if requested, deny otherwise
        return auto_approve

    def finalize(self, _result: dict[str, _typing.Any] | None = None) -> None:  # noqa: B027
        """
        Called at the end of a conversation turn.

        For JSON renderer, this outputs the accumulated result.
        For other renderers, this may do cleanup.

        Note: Not abstract because most renderers don't need this.
        """

    def show_session_banner(  # noqa: B027
        self,
        *,
        model: str,  # noqa: ARG002
        provider: str,  # noqa: ARG002
        profile: str | None = None,  # noqa: ARG002
        session: str | None = None,  # noqa: ARG002
    ) -> None:
        """
        Display session info banner at the start of a conversation.

        Optional - renderers may override to show model/profile/session info.

        Args:
            model: Model name/identifier.
            provider: Provider name (openrouter, ollama, etc).
            profile: Profile name if using one, or None for default.
            session: Session name if resuming, or None/new for new session.
        """

    def show_finish(  # noqa: B027
        self,
        status: str,  # noqa: ARG002
        summary: str,  # noqa: ARG002
        next_steps: str | None = None,  # noqa: ARG002
    ) -> None:
        """
        Display finish status when agent calls the Finish tool.

        Optional - renderers may override to show completion status.

        Args:
            status: Completion status (success, partial, failed, blocked).
            summary: Summary of what was accomplished.
            next_steps: Optional suggestions for next actions.
        """

    def show_prompt_source(  # noqa: B027
        self,
        file_paths: list[str],  # noqa: ARG002
        content: str,  # noqa: ARG002
    ) -> None:
        """
        Display the source of a prompt read from file(s).

        Optional - renderers may override to show prompt source info.
        Called after session banner when prompt is read from file(s).

        Args:
            file_paths: List of paths to the prompt file(s).
            content: The combined prompt content (may be truncated for display).
        """


class ConversationResult(_typing.TypedDict, total=False):
    """Result of a conversation turn for JSON output."""

    response: str
    provider: str
    model: str
    usage: dict[str, int]
    stop_reason: str | None
    tool_calls: list[dict[str, _typing.Any]]
    tool_results: list[dict[str, _typing.Any]]
    error: str | None

