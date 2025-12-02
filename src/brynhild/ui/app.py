"""
Interactive TUI application for Brynhild.

This is Layer 4 of the UI system - a full interactive terminal application
built on Textual.
"""

import asyncio as _asyncio
import typing as _typing

import textual as _textual
import textual.app as _app
import textual.binding as _binding
import textual.containers as _containers
import textual.css.query as _query
import textual.events as _events
import textual.message as _message
import textual.screen as _screen
import textual.widgets as _widgets

import brynhild.api.base as api_base
import brynhild.constants as _constants
import brynhild.core.conversation as core_conversation
import brynhild.core.prompts as core_prompts
import brynhild.core.types as core_types
import brynhild.logging as brynhild_logging
import brynhild.skills as skills
import brynhild.tools.registry as tools_registry
import brynhild.ui.base as ui_base
import brynhild.ui.widgets as widgets

# Re-export for backwards compatibility
get_system_prompt = core_prompts.get_system_prompt


class ConversationUpdated(_message.Message):
    """Message sent when conversation state changes."""

    pass


class ToolPermissionRequest(_message.Message):
    """Message requesting tool execution permission."""

    def __init__(self, tool_call: ui_base.ToolCallDisplay) -> None:
        super().__init__()
        self.tool_call = tool_call
        self.result: _asyncio.Future[bool] = _asyncio.get_event_loop().create_future()


class HelpScreen(_screen.Screen[None]):
    """Modal help screen that dismisses on any keypress."""

    BINDINGS = [
        _binding.Binding("escape", "dismiss", "Close"),
        _binding.Binding("any", "dismiss", "", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #help-content {
        height: auto;
    }

    #help-footer {
        text-align: center;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> _app.ComposeResult:
        with _containers.Container(id="help-container"):
            yield _widgets.Static("Brynhild Help", id="help-title")
            yield _widgets.Static(
                """[b]Leader Key (^T)[/b] - press Ctrl+T, then:
  [b]h[/b] - This help
  [b]t[/b] - Toggle thinking
  [b]c[/b] - Clear conversation
  [b]p[/b] - Command palette
  [b]q[/b] - Quit

[b]Text Input[/b] (emacs-style):
  Ctrl+A/E - Start/End of line
  Ctrl+K/U - Kill to end/start
  Ctrl+W   - Kill word backward

[b]Cancel:[/b] Esc/Ctrl+C/Ctrl+G (stops generation), Ctrl+Q=quit
[b]F-keys:[/b] F1=help F2=💭 F3=palette F5=clear F10=quit""",
                id="help-content",
            )
            yield _widgets.Static("[dim]Press any key to close[/dim]", id="help-footer")

    def on_key(self, event: _events.Key) -> None:  # noqa: ARG002
        """Dismiss on any keypress."""
        self.dismiss()


class PermissionScreen(_screen.Screen[bool | None]):
    """Modal screen for tool permission requests.

    Returns:
        True: Allow the tool
        False: Deny the tool (continue generation)
        None: Cancel entire generation
    """

    BINDINGS = [
        _binding.Binding("a", "allow", "Allow"),
        _binding.Binding("y", "allow", "Allow", show=False),
        _binding.Binding("enter", "allow", "Allow", show=False),
        _binding.Binding("d", "deny", "Deny"),
        _binding.Binding("n", "deny", "Deny", show=False),
        _binding.Binding("escape", "deny", "Deny", show=False),
        _binding.Binding("c", "cancel", "Cancel All"),
        _binding.Binding("q", "cancel", "Cancel All", show=False),
        _binding.Binding("ctrl+c", "cancel", "Cancel All", show=False),
    ]

    CSS = """
    PermissionScreen {
        align: center middle;
    }

    #permission-container {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }

    #permission-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #permission-tool {
        margin-bottom: 1;
    }

    #permission-input {
        background: $surface-darken-1;
        padding: 1;
        margin-bottom: 1;
    }

    #permission-footer {
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(self, tool_call: ui_base.ToolCallDisplay) -> None:
        super().__init__()
        self._tool_call = tool_call

    def compose(self) -> _app.ComposeResult:
        with _containers.Container(id="permission-container"):
            yield _widgets.Static(
                "⚠️ Permission Required",
                id="permission-title",
            )
            yield _widgets.Static(
                f"Tool: [bold]{self._tool_call.tool_name}[/bold]",
                id="permission-tool",
            )

            # Show tool input
            lines = []
            for key, value in self._tool_call.tool_input.items():
                value_str = str(value)
                # Truncate long values but show more context
                if len(value_str) > 200:
                    value_str = value_str[:197] + "..."
                lines.append(f"[dim]{key}:[/dim] {value_str}")

            if lines:
                yield _widgets.Static(
                    "\n".join(lines),
                    id="permission-input",
                )

            yield _widgets.Static(
                "[b]a[/b] Allow  |  [b]d[/b] Deny  |  [b]c[/b] Cancel All",
                id="permission-footer",
            )

    def action_allow(self) -> None:
        """Allow the tool execution."""
        self.dismiss(True)

    def action_deny(self) -> None:
        """Deny the tool execution."""
        self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel entire generation."""
        self.dismiss(None)


class TUICallbacks(core_conversation.ConversationCallbacks):
    """
    Callback adapter for the TUI.

    Implements ConversationCallbacks by delegating to BrynhildApp methods.
    This allows ConversationProcessor to drive the TUI without knowing
    about Textual-specific details.
    """

    def __init__(self, app: "BrynhildApp") -> None:
        self._app = app
        self._stream_widget: widgets.StreamingMessageWidget | None = None

    # === Streaming lifecycle ===

    async def on_stream_start(self) -> None:
        """Start streaming - create widget."""
        self._stream_widget = await self._app._start_streaming()

    async def on_stream_end(self) -> None:
        """End streaming."""
        await self._app._end_streaming()
        self._stream_widget = None

    # === Thinking callbacks ===

    async def on_thinking_delta(self, text: str) -> None:
        """Pass thinking delta to streaming widget."""
        if self._stream_widget:
            self._stream_widget.append_thinking(text)

    async def on_thinking_complete(self, full_text: str) -> None:
        """Thinking complete - widget handles display internally."""
        # StreamingMessageWidget already displays thinking summary when
        # content starts, so this is a no-op
        pass

    # === Response text callbacks ===

    async def on_text_delta(self, text: str) -> None:
        """Pass text delta to streaming widget."""
        if self._stream_widget:
            self._stream_widget.append_text(text)

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        """Text complete - already shown via deltas."""
        # Text is already displayed incrementally, no action needed
        pass

    # === Tool callbacks ===

    async def on_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        """Show tool call in UI."""
        await self._app._add_tool_call(tool_call)

    async def request_tool_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
    ) -> bool:
        """Show permission dialog."""
        return await self._app._request_permission(tool_call)

    async def on_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        """Show tool result in UI."""
        await self._app._add_tool_result(result)

    # === Round lifecycle ===

    async def on_round_start(self, round_num: int) -> None:
        """Update subtitle on new round."""
        if round_num > 1:
            self._app.sub_title = (
                f"{self._app._provider.name} / {self._app._provider.model} "
                f"[Round {round_num}]"
            )

    # === Cancellation ===

    def is_cancelled(self) -> bool:
        """Check if user cancelled."""
        return self._app._generation_cancelled

    # === Info ===

    async def on_info(self, message: str) -> None:
        """Show notification."""
        self._app.notify(message)


class BrynhildApp(_app.App[None]):
    """
    Interactive TUI for Brynhild.

    This app provides:
    - Message input and display
    - Streaming response rendering
    - Tool execution with permission prompts
    - Session management (future)
    """

    TITLE = "Brynhild"
    SUB_TITLE = "AI Coding Assistant"

    # Override Textual's default ctrl+p (conflicts with emacs previous-line)
    # Use Ctrl+Shift+P instead (VS Code style, emacs-safe)
    COMMAND_PALETTE_BINDING = "ctrl+shift+p"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 1;
        grid-rows: 1fr auto;
    }

    #messages-container {
        height: 100%;
        overflow-y: auto;
        padding: 1 2;
    }

    #input-container {
        dock: bottom;
        height: auto;
        padding: 1 2;
        background: $surface;
        border-top: solid $primary;
    }

    #prompt-input {
        width: 100%;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-darken-2;
        padding: 0 1;
    }

    .hidden {
        display: none;
    }

    #permission-overlay {
        align: center middle;
    }
    """

    # Keybindings designed to avoid conflicts with emacs editing commands.
    # See workflow/keybinding-policy.md for the full policy.
    #
    # Reserved emacs keys (DO NOT USE):
    #   ctrl+a/e (line start/end), ctrl+f/b (char forward/back),
    #   ctrl+n/p (line down/up), ctrl+d (delete), ctrl+k (kill line),
    #   ctrl+y (yank), ctrl+w (kill word), ctrl+t (transpose),
    #   ctrl+u (universal arg), ctrl+l (recenter), ctrl+o (open line)
    #
    # Textual Input widget already handles: ctrl+a, ctrl+e, ctrl+d, ctrl+k,
    #   ctrl+w, ctrl+u, ctrl+f, ctrl+c (copy), ctrl+x (cut), ctrl+v (paste)
    BINDINGS = [
        # Leader key: Ctrl+T (terminal multiplexer style)
        # Press Ctrl+T, then: h=help, q=quit, t=thinking, c=clear, p=palette
        _binding.Binding("ctrl+t", "leader", "^T ...", priority=True),
        # Direct bindings (F-keys as fallback)
        _binding.Binding("f1", "help", "", show=False),
        _binding.Binding("f2", "toggle_thinking", "", show=False),
        _binding.Binding("f3", "command_palette", "", show=False),
        _binding.Binding("f5", "clear", "", show=False),
        _binding.Binding("f10", "quit", "", show=False),
        _binding.Binding("escape", "cancel_or_exit_leader", "Esc"),
        # Ctrl alternatives
        _binding.Binding("ctrl+q", "quit", "", show=False, priority=True),
        _binding.Binding("ctrl+g", "cancel", "", show=False, priority=True),
        _binding.Binding("ctrl+c", "cancel", "", show=False, priority=True),
    ]

    def __init__(
        self,
        provider: api_base.LLMProvider,
        *,
        tool_registry: tools_registry.ToolRegistry | None = None,
        skill_registry: skills.SkillRegistry | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        auto_approve_tools: bool = False,
        dry_run: bool = False,
        conv_logger: brynhild_logging.ConversationLogger | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """
        Initialize the Brynhild TUI.

        Args:
            provider: LLM provider instance.
            tool_registry: Tool registry (None to disable tools).
            skill_registry: Skill registry for runtime skill triggering.
            max_tokens: Maximum tokens for responses.
            auto_approve_tools: Auto-approve all tool executions.
            dry_run: Show tool calls without executing.
            conv_logger: Conversation logger instance.
            system_prompt: System prompt (required).
        """
        super().__init__()
        self._provider = provider
        self._tool_registry = tool_registry
        self._skill_registry = skill_registry
        self._max_tokens = max_tokens
        self._auto_approve = auto_approve_tools
        self._dry_run = dry_run
        self._conv_logger = conv_logger
        if system_prompt is None:
            raise ValueError("system_prompt is required")
        self._system_prompt = system_prompt

        # Conversation state
        self._messages: list[dict[str, _typing.Any]] = []
        self._is_processing = False
        self._current_stream: widgets.StreamingMessageWidget | None = None
        self._current_worker: _typing.Any = None  # Worker for current generation
        self._generation_cancelled = False

        # Permission handling
        self._pending_permission: ToolPermissionRequest | None = None

        # Leader key mode (Ctrl+T prefix, terminal multiplexer style)
        self._leader_mode = False

    def compose(self) -> _app.ComposeResult:
        """Compose the app layout."""
        yield _widgets.Header()

        with _containers.ScrollableContainer(id="messages-container"):
            yield _widgets.Static(
                "Welcome to Brynhild! Type a message below to start.",
                id="welcome",
            )

        with _containers.Container(id="input-container"):
            yield _widgets.Input(
                placeholder="Type your message... (^T h for help)",
                id="prompt-input",
            )

        yield _widgets.Footer()

    def on_mount(self) -> None:
        """Handle app mount."""
        # Focus the input
        self.query_one("#prompt-input", _widgets.Input).focus()

        # Update title with model info
        self.sub_title = f"{self._provider.name} / {self._provider.model}"

        # Log system prompt
        if self._conv_logger:
            self._conv_logger.log_system_prompt(self._system_prompt)

    def on_key(self, event: _events.Key) -> None:
        """Handle key events for leader key mode."""
        if not self._leader_mode:
            return

        # We're in leader mode - consume this key and dispatch
        event.stop()
        event.prevent_default()
        self._leader_mode = False
        self.sub_title = f"{self._provider.name} / {self._provider.model}"

        # Leader key dispatch table
        key = event.key.lower()
        if key == "h" or key == "question_mark":
            self.action_help()
        elif key == "q":
            self.exit()
        elif key == "t":
            self.action_toggle_thinking()
        elif key == "c":
            self.action_clear()
        elif key == "p":
            self.action_command_palette()
        elif key == "escape":
            pass  # Silent cancel, subtitle already restored
        elif key == "ctrl+t":
            # Ctrl+T Ctrl+T - just cancel leader mode
            pass  # Silent cancel
        else:
            self.notify(f"Unknown: ^T {key}", timeout=3)

        # Re-focus input after command
        self.query_one("#prompt-input", _widgets.Input).focus()

    async def on_input_submitted(self, event: _widgets.Input.Submitted) -> None:
        """Handle user input submission."""
        if self._is_processing:
            self.notify("Please wait for the current response to complete.")
            return

        prompt = event.value.strip()
        if not prompt:
            return

        # Clear input
        event.input.value = ""

        # Remove welcome message if present
        try:
            welcome = self.query_one("#welcome", _widgets.Static)
            welcome.remove()
        except _query.NoMatches:
            pass

        # Add user message
        await self._add_user_message(prompt)

        # Process the message (runs in a worker to allow push_screen_wait)
        self._generation_cancelled = False
        self._current_worker = self._process_message(prompt)

    async def _add_user_message(self, content: str) -> None:
        """Add a user message to the display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        message_widget = widgets.MessageWidget.construct_user_message(content)
        await container.mount(message_widget)
        message_widget.scroll_visible()

    async def _add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        message_widget = widgets.MessageWidget.construct_assistant_message(content)
        await container.mount(message_widget)
        message_widget.scroll_visible()

    async def _add_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        """Add a tool call to the display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        message_widget = widgets.MessageWidget.construct_tool_call(tool_call)
        await container.mount(message_widget)
        message_widget.scroll_visible()

    async def _add_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        """Add a tool result to the display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        message_widget = widgets.MessageWidget.construct_tool_result(result)
        await container.mount(message_widget)
        message_widget.scroll_visible()

    async def _add_error(self, error: str) -> None:
        """Add an error message to the display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        message_widget = widgets.MessageWidget.construct_error_message(error)
        await container.mount(message_widget)
        message_widget.scroll_visible()

    async def _start_streaming(self) -> widgets.StreamingMessageWidget:
        """Start a streaming message widget."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        stream_widget = widgets.StreamingMessageWidget()
        await container.mount(stream_widget)
        stream_widget.scroll_visible()
        self._current_stream = stream_widget
        # Update subtitle to show cancellation hint
        self.sub_title = f"{self._provider.name} / {self._provider.model} [Esc/^C/^G to stop]"
        return stream_widget

    async def _end_streaming(self) -> str:
        """End streaming and return the accumulated content."""
        if self._current_stream:
            content = self._current_stream.get_content()
            self._current_stream = None
            # Restore normal subtitle
            self.sub_title = f"{self._provider.name} / {self._provider.model}"
            return content
        return ""

    async def _request_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,
    ) -> bool:
        """Request permission to execute a tool.

        Returns:
            True: User allowed the tool
            False: User denied OR cancelled (check _generation_cancelled)
        """
        if self._auto_approve:
            return True

        # Show permission modal and wait for user response
        # Returns: True (allow), False (deny), None (cancel all)
        result = await self.push_screen_wait(PermissionScreen(tool_call))

        if result is None:
            # User chose to cancel entire generation
            self._generation_cancelled = True
            self.notify("Generation cancelled.", severity="warning")
            return False

        return result

    @_textual.work(exclusive=True)
    async def _process_message(self, prompt: str) -> None:
        """Process a user message and get a response.

        This method is decorated with @work to run in a worker context,
        which is required for push_screen_wait (permission dialogs).

        Delegates to ConversationProcessor for the actual conversation loop,
        using TUICallbacks to drive the UI.
        """
        self._is_processing = True

        try:
            # Preprocess for skill triggers (/skill command)
            preprocess_result = skills.preprocess_for_skills(
                prompt,
                self._skill_registry,
            )

            # Handle skill errors (e.g., /skill unknown-name)
            if preprocess_result.error:
                self.notify(preprocess_result.error, severity="warning")
                # Continue with original message (don't abort)

            # If a skill was triggered, inject it as a system message
            if preprocess_result.skill_injection:
                # Log the skill trigger
                if self._conv_logger:
                    self._conv_logger.log_skill_triggered(
                        skill_name=preprocess_result.skill_name or "unknown",
                        skill_content=preprocess_result.skill_injection,
                        trigger_type=preprocess_result.trigger_type or "explicit",
                        trigger_match=prompt if preprocess_result.trigger_type == "explicit" else None,
                    )

                # Inject skill as a system message before user message
                skill_message = skills.format_skill_injection_message(
                    preprocess_result.skill_injection,
                    preprocess_result.skill_name or "unknown",
                )
                self._messages.append({
                    "role": "user",
                    "content": f"[System: The following skill has been activated]\n\n{skill_message}",
                })

                # Notify user that skill was activated
                self.notify(
                    f"Skill '{preprocess_result.skill_name}' activated",
                    severity="information",
                )

            # Use the (possibly modified) user message
            user_message = preprocess_result.user_message

            # If the message is empty after /skill command, don't send anything
            if not user_message.strip() and preprocess_result.skill_injection:
                # Just the skill was injected, no additional user message
                # Add a minimal prompt to get the model to respond
                user_message = "Please acknowledge the skill and wait for my request."

            # Add user message to history
            self._messages.append({"role": "user", "content": user_message})

            # Log user message
            if self._conv_logger:
                self._conv_logger.log_user_message(user_message)

            # Create callbacks and processor
            callbacks = TUICallbacks(self)
            processor = core_conversation.ConversationProcessor(
                provider=self._provider,
                callbacks=callbacks,
                tool_registry=self._tool_registry,
                max_tokens=self._max_tokens,
                auto_approve_tools=self._auto_approve,
                dry_run=self._dry_run,
                logger=self._conv_logger,
            )

            # Process the conversation turn
            result = await processor.process_streaming(
                messages=self._messages,
                system_prompt=self._system_prompt,
            )

            # Update message history from processor's result
            # (processor returns the complete updated message list)
            self._messages = result.messages

        except _asyncio.CancelledError:
            # Worker was cancelled - clean exit
            pass

        except Exception as e:
            await self._add_error(str(e))
            if self._conv_logger:
                self._conv_logger.log_error(str(e), context="streaming")

        finally:
            self._is_processing = False
            self._current_worker = None

    def action_clear(self) -> None:
        """Clear the message display."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        container.remove_children()
        self._messages = []
        self.notify("Conversation cleared.")

    def action_cancel(self) -> None:
        """Cancel current generation."""
        if self._is_processing and self._current_worker is not None:
            self._generation_cancelled = True
            self._current_worker.cancel()
            self.notify("Generation cancelled.", severity="warning")
            # Update UI to show cancellation
            if self._current_stream:
                self._current_stream.append_text("\n\n*[Generation cancelled by user]*")
            self._is_processing = False
            self._current_worker = None

    def action_cancel_or_exit_leader(self) -> None:
        """Cancel operation or exit leader mode."""
        if self._leader_mode:
            self._leader_mode = False
            self.sub_title = f"{self._provider.name} / {self._provider.model}"
            # Re-focus input
            self.query_one("#prompt-input", _widgets.Input).focus()
        else:
            self.action_cancel()

    def action_leader(self) -> None:
        """Enter leader key mode (terminal multiplexer style prefix key)."""
        self._leader_mode = True
        self.sub_title = "^T → h:help q:quit t:💭 c:clear p:palette  [Esc to cancel]"
        # Blur input so keys come to app, not the text box
        self.set_focus(None)

    def action_help(self) -> None:
        """Show help modal (dismisses on any key)."""
        self.push_screen(HelpScreen())

    def action_toggle_thinking(self) -> None:
        """Toggle thinking visibility on the most recent message."""
        # Find all StreamingMessageWidget instances
        try:
            stream_widgets = self.query(widgets.StreamingMessageWidget)
            if stream_widgets:
                # Get the last one (most recent message)
                last_widget = list(stream_widgets)[-1]
                last_widget.toggle_thinking()
                if last_widget.is_thinking_expanded():
                    self.notify("Thinking expanded (F2 to collapse)")
                else:
                    self.notify("Thinking collapsed (F2 to expand)")
            else:
                self.notify("No messages with thinking to toggle")
        except _query.NoMatches:
            self.notify("No messages with thinking to toggle")

    # === Test Hooks ===

    async def send_message_for_test(self, message: str) -> None:
        """
        Send a message programmatically (for testing).

        This simulates user input without UI interaction.
        """
        # Remove welcome if present
        try:
            welcome = self.query_one("#welcome", _widgets.Static)
            welcome.remove()
        except _query.NoMatches:
            pass

        await self._add_user_message(message)
        # _process_message is a worker, so call it and wait for completion
        worker = self._process_message(message)
        await worker.wait()

    def get_message_count(self) -> int:
        """Get the number of messages in the conversation (for testing)."""
        return len(self._messages)

    def get_displayed_messages(self) -> list[widgets.MessageWidget]:
        """Get all displayed message widgets (for testing)."""
        container = self.query_one("#messages-container", _containers.ScrollableContainer)
        return list(container.query(widgets.MessageWidget))

    def is_processing(self) -> bool:
        """Check if the app is currently processing a message (for testing)."""
        return self._is_processing


def create_app(
    provider: api_base.LLMProvider,
    *,
    tool_registry: tools_registry.ToolRegistry | None = None,
    skill_registry: skills.SkillRegistry | None = None,
    max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
    auto_approve_tools: bool = False,
    dry_run: bool = False,
    conv_logger: brynhild_logging.ConversationLogger | None = None,
    system_prompt: str | None = None,
) -> BrynhildApp:
    """
    Create a Brynhild TUI app instance.

    This factory function allows easy creation of the app for both
    interactive use and testing.
    """
    return BrynhildApp(
        provider=provider,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        max_tokens=max_tokens,
        auto_approve_tools=auto_approve_tools,
        dry_run=dry_run,
        conv_logger=conv_logger,
        system_prompt=system_prompt,
    )

