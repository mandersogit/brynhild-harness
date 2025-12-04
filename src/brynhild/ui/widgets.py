"""
Custom widgets for the Brynhild TUI.

These widgets are designed to be testable and reusable.
"""

import rich.markdown as _rich_markdown
import textual.app as _app
import textual.containers as _containers
import textual.widgets as _widgets

import brynhild.ui.base as ui_base
import brynhild.ui.icons as icons


class MessageWidget(_widgets.Static):
    """A widget displaying a single message in the conversation."""

    DEFAULT_CSS = """
    MessageWidget {
        margin: 1 0;
        padding: 1 2;
    }

    MessageWidget.user {
        background: $primary-darken-2;
        border: solid $primary;
        border-title-color: $primary-lighten-2;
    }

    MessageWidget.assistant {
        background: $success-darken-3;
        border: solid $success;
        border-title-color: $success-lighten-2;
    }

    MessageWidget.tool-call {
        background: $warning-darken-3;
        border: solid $warning;
        border-title-color: $warning-lighten-2;
    }

    MessageWidget.tool-result {
        background: $surface;
        border: solid $secondary;
        border-title-color: $secondary;
    }

    MessageWidget.tool-result.success {
        border: solid $success;
    }

    MessageWidget.tool-result.error {
        border: solid $error;
        background: $error-darken-3;
    }

    MessageWidget.error {
        background: $error-darken-3;
        border: solid $error;
        border-title-color: $error-lighten-2;
    }
    """

    def __init__(
        self,
        content: str,
        role: str,
        *,
        title: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Create a message widget.

        Args:
            content: The message content (supports markdown for assistant).
            role: One of 'user', 'assistant', 'tool-call', 'tool-result', 'error'.
            title: Optional title for the message border.
            name: Widget name.
            id: Widget ID.
            classes: Additional CSS classes.
        """
        self._content = content
        self._role = role
        self._title = title or role.title()

        # Combine role class with any additional classes
        all_classes = role
        if classes:
            all_classes = f"{role} {classes}"

        super().__init__(name=name, id=id, classes=all_classes)
        self.border_title = self._title

    def compose(self) -> _app.ComposeResult:
        """Compose the widget content."""
        # For assistant messages, render as markdown
        if self._role == "assistant":
            yield _widgets.Static(_rich_markdown.Markdown(self._content))
        else:
            yield _widgets.Static(self._content)

    @classmethod
    def construct_user_message(cls, content: str) -> "MessageWidget":
        """Create a user message widget."""
        return cls(content, "user", title="You")

    @classmethod
    def construct_assistant_message(cls, content: str) -> "MessageWidget":
        """Create an assistant message widget."""
        return cls(content, "assistant", title="Assistant")

    @classmethod
    def construct_tool_call(cls, tool_call: ui_base.ToolCallDisplay) -> "MessageWidget":
        """Create a tool call widget."""
        if tool_call.is_recovered:
            lines = [f"**Tool (recovered):** {tool_call.tool_name}"]
            title = f"{icons.icon_recovered()}{tool_call.tool_name} (recovered)"
            extra_classes = "recovered"
        else:
            lines = [f"**Tool:** {tool_call.tool_name}"]
            title = f"{icons.icon_bolt()}{tool_call.tool_name}"
            extra_classes = ""

        for key, value in tool_call.tool_input.items():
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            lines.append(f"  {key}: {value_str}")
        content = "\n".join(lines)
        widget = cls(content, "tool-call", title=title)
        if extra_classes:
            widget.add_class(extra_classes)
        return widget

    @classmethod
    def construct_tool_result(cls, result: ui_base.ToolResultDisplay) -> "MessageWidget":
        """Create a tool result widget."""
        if result.result.success:
            output = result.result.output.strip()
            if len(output) > 500:
                output = output[:497] + "..."
            content = output if output else "(no output)"
            status_class = "success"
            title = f"{icons.icon_success()}{result.tool_name}"
        else:
            content = result.result.error or "Unknown error"
            status_class = "error"
            title = f"{icons.icon_failure()}{result.tool_name}"

        return cls(content, "tool-result", title=title, classes=status_class)

    @classmethod
    def construct_error_message(cls, error: str) -> "MessageWidget":
        """Create an error message widget."""
        return cls(error, "error", title="Error")


class ThinkingWidget(_widgets.Collapsible):
    """A collapsible widget for displaying reasoning/thinking traces."""

    DEFAULT_CSS = """
    ThinkingWidget {
        margin: 0 0 1 0;
        padding: 0;
    }

    ThinkingWidget > Contents {
        padding: 0 2;
        background: $surface-darken-1;
    }

    ThinkingWidget .thinking-content {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(
        self,
        content: str = "",
        *,
        collapsed: bool = True,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Create a thinking widget."""
        super().__init__(
            title="💭 Thinking...",
            collapsed=collapsed,
            name=name,
            id=id,
        )
        self._content = content
        self._content_widget: _widgets.Static | None = None

    def compose(self) -> _app.ComposeResult:
        """Compose the widget content."""
        self._content_widget = _widgets.Static(
            self._content,
            classes="thinking-content",
        )
        yield self._content_widget

    def append_text(self, text: str) -> None:
        """Append text to the thinking content."""
        self._content += text
        if self._content_widget:
            self._content_widget.update(self._content)

    def finalize(self) -> None:
        """Finalize the thinking display (collapse and update title)."""
        word_count = len(self._content.split())
        self.title = f"💭 Thinking ({word_count} words) - click to expand"
        self.collapsed = True

    def get_content(self) -> str:
        """Get the accumulated content."""
        return self._content


class StreamingMessageWidget(_widgets.Static, can_focus=True):
    """A widget that displays streaming text as it arrives."""

    DEFAULT_CSS = """
    StreamingMessageWidget {
        margin: 1 0;
        padding: 1 2;
        background: $success-darken-3;
        border: solid $success;
        border-title-color: $success-lighten-2;
    }

    StreamingMessageWidget:focus {
        border: double $success;
    }

    StreamingMessageWidget.has-thinking {
        /* Visual indicator that clicking will toggle thinking */
    }

    StreamingMessageWidget .thinking-inline {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    StreamingMessageWidget .response-content {
        /* Main response content */
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Create a streaming message widget."""
        super().__init__(name=name, id=id)
        self._content = ""
        self._thinking = ""
        self._thinking_done = False
        self._thinking_expanded = False  # Track if thinking is expanded
        self.border_title = "Assistant"

    def append_thinking(self, text: str) -> None:
        """Append text to the thinking content."""
        self._thinking += text
        self._update_display()

    def append_text(self, text: str) -> None:
        """Append text to the main response."""
        # If this is the first real text, mark thinking as done
        if not self._thinking_done and self._thinking:
            self._thinking_done = True
            # Add class to indicate this message has thinking
            self.add_class("has-thinking")
        self._content += text
        self._update_display()

    def toggle_thinking(self) -> bool:
        """Toggle between expanded and collapsed thinking view.

        Returns:
            True if toggled, False if no thinking to toggle.
        """
        if self._thinking and self._thinking_done:
            self._thinking_expanded = not self._thinking_expanded
            self._update_display()
            return True
        return False

    def has_thinking(self) -> bool:
        """Check if this message has thinking content."""
        return bool(self._thinking and self._thinking_done)

    def on_click(self) -> None:
        """Handle click to toggle thinking."""
        if self.has_thinking():
            self.toggle_thinking()
            # Show notification via app
            if self.app:
                if self._thinking_expanded:
                    self.app.notify("💭 Thinking expanded")
                else:
                    self.app.notify("💭 Thinking collapsed")

    def _update_display(self) -> None:
        """Update the display with current content."""
        parts = []

        # Show thinking if in progress (not done yet)
        if self._thinking and not self._thinking_done:
            parts.append(f"*💭 {self._thinking}*")

        # Show thinking (expanded or collapsed) if done
        if self._thinking and self._thinking_done:
            word_count = len(self._thinking.split())
            if self._thinking_expanded:
                # Show full thinking content
                parts.append(f"*💭 Thinking ({word_count} words) [click to collapse]:*\n\n")
                parts.append(f"> {self._thinking.replace(chr(10), chr(10) + '> ')}\n")
            else:
                # Show collapsed summary
                parts.append(f"*💭 [Thinking: {word_count} words - click to expand]*")

        # Show main content
        if self._content:
            if parts:
                parts.append("\n\n---\n\n")
            parts.append(self._content)

        display_text = "".join(parts)
        self.update(_rich_markdown.Markdown(display_text))

        # Auto-scroll only if user is already at (or near) the bottom
        # This prevents interrupting if they've scrolled up to read something
        self._maybe_scroll_to_bottom()

    def _maybe_scroll_to_bottom(self) -> None:
        """Scroll to keep new content visible, but only if already at/near the bottom.

        This prevents interrupting the user if they've scrolled up to read earlier content.
        """
        # Find the parent scrollable container
        try:
            container = self.ancestors_with_self
            for ancestor in container:
                # Check if this is a scrollable container
                if hasattr(ancestor, "scroll_y") and hasattr(ancestor, "max_scroll_y"):
                    # Allow some slack (within 50 pixels of bottom counts as "at bottom")
                    slack = 50
                    at_bottom = ancestor.scroll_y >= (ancestor.max_scroll_y - slack)
                    if at_bottom:
                        self.scroll_visible()
                    return
        except Exception:
            # If anything goes wrong, just scroll (safe fallback)
            self.scroll_visible()

    def get_content(self) -> str:
        """Get the accumulated response content (not thinking)."""
        return self._content

    def get_thinking(self) -> str:
        """Get the accumulated thinking content."""
        return self._thinking

    def is_thinking_expanded(self) -> bool:
        """Check if thinking is currently expanded."""
        return self._thinking_expanded

    def clear_content(self) -> None:
        """Clear all accumulated content."""
        self._content = ""
        self._thinking = ""
        self._thinking_done = False
        self._thinking_expanded = False
        self.remove_class("has-thinking")
        self.update("")


class PermissionDialog(_widgets.Static):
    """A dialog for requesting tool execution permission."""

    DEFAULT_CSS = """
    PermissionDialog {
        align: center middle;
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $warning;
        border-title-color: $warning;
    }

    PermissionDialog .buttons {
        margin-top: 1;
        align: center middle;
        width: 100%;
    }

    PermissionDialog Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        tool_call: ui_base.ToolCallDisplay,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Create a permission dialog."""
        super().__init__(name=name, id=id)
        self._tool_call = tool_call
        self.border_title = f"Permission: {tool_call.tool_name}"

    def compose(self) -> _app.ComposeResult:
        """Compose the dialog content."""
        yield _widgets.Static(f"Allow **{self._tool_call.tool_name}**?")

        # Show tool input
        lines = []
        for key, value in self._tool_call.tool_input.items():
            value_str = str(value)
            if len(value_str) > 60:
                value_str = value_str[:57] + "..."
            lines.append(f"  {key}: {value_str}")
        if lines:
            yield _widgets.Static("\n".join(lines))

        # Buttons
        with _containers.Horizontal(classes="buttons"):
            yield _widgets.Button("Allow", id="allow", variant="success")
            yield _widgets.Button("Deny", id="deny", variant="error")
            yield _widgets.Button("Allow All", id="allow-all", variant="warning")

