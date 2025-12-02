"""Tests for the Textual TUI application."""


import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.tools.base as tools_base
import brynhild.ui as ui
import brynhild.ui.widgets as widgets

# Test system prompt - minimal but valid
_TEST_SYSTEM_PROMPT = "You are a test assistant."


class MockProvider(api_base.LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or ["Hello! I'm a mock assistant."]
        self._response_index = 0
        self._name = "mock"
        self._model = "mock-model"

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        _messages: list[dict],
        *,
        _system: str | None = None,
        _tools: list[api_types.Tool] | None = None,
        _max_tokens: int = 8192,
    ) -> api_types.CompletionResponse:
        response = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1
        return api_types.CompletionResponse(
            id="mock-id",
            content=response,
            stop_reason="end_turn",
            usage=api_types.Usage(input_tokens=10, output_tokens=20),
        )

    async def stream(
        self,
        _messages: list[dict],
        *,
        _system: str | None = None,
        _tools: list[api_types.Tool] | None = None,
        _max_tokens: int = 8192,
    ):
        """Stream response as events."""
        response = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1

        # Yield text in chunks
        for i in range(0, len(response), 10):
            chunk = response[i : i + 10]
            yield api_types.StreamEvent(type="text_delta", text=chunk)

        # Final event
        yield api_types.StreamEvent(
            type="message_stop",
            stop_reason="end_turn",
            usage=api_types.Usage(input_tokens=10, output_tokens=20),
        )


class TestMessageWidget:
    """Tests for MessageWidget."""

    def test_user_message_creation(self) -> None:
        """Should create a user message widget."""
        widget = widgets.MessageWidget.construct_user_message("Hello!")
        assert widget._content == "Hello!"
        assert widget._role == "user"
        assert widget._title == "You"

    def test_assistant_message_creation(self) -> None:
        """Should create an assistant message widget."""
        widget = widgets.MessageWidget.construct_assistant_message("Hi there!")
        assert widget._content == "Hi there!"
        assert widget._role == "assistant"
        assert widget._title == "Assistant"

    def test_tool_call_creation(self) -> None:
        """Should create a tool call widget."""
        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "echo hello"},
        )
        widget = widgets.MessageWidget.construct_tool_call(tool_call)
        assert widget._role == "tool-call"
        assert "Bash" in widget._title

    def test_tool_result_success(self) -> None:
        """Should create a success tool result widget."""
        result = tools_base.ToolResult(success=True, output="hello", error=None)
        display = ui.ToolResultDisplay(tool_name="Bash", result=result)
        widget = widgets.MessageWidget.construct_tool_result(display)
        assert widget._role == "tool-result"
        assert "✓" in widget._title

    def test_tool_result_error(self) -> None:
        """Should create an error tool result widget."""
        result = tools_base.ToolResult(success=False, output="", error="Failed!")
        display = ui.ToolResultDisplay(tool_name="Bash", result=result)
        widget = widgets.MessageWidget.construct_tool_result(display)
        assert widget._role == "tool-result"
        assert "✗" in widget._title

    def test_error_message_creation(self) -> None:
        """Should create an error message widget."""
        widget = widgets.MessageWidget.construct_error_message("Something went wrong")
        assert widget._content == "Something went wrong"
        assert widget._role == "error"


class TestStreamingMessageWidget:
    """Tests for StreamingMessageWidget."""

    def test_append_text(self) -> None:
        """Should accumulate text."""
        widget = widgets.StreamingMessageWidget()
        widget._content = ""  # Initialize
        widget.append_text("Hello")
        widget.append_text(" world")
        assert widget.get_content() == "Hello world"

    def test_clear_content(self) -> None:
        """Should clear accumulated content."""
        widget = widgets.StreamingMessageWidget()
        widget._content = "Some content"
        widget.clear_content()
        assert widget.get_content() == ""


class TestBrynhildApp:
    """Tests for BrynhildApp."""

    def test_app_creation(self) -> None:
        """Should create app with required parameters."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)
        assert app._provider == provider
        assert app._tool_registry is None
        assert app._auto_approve is False
        assert app._dry_run is False

    def test_app_creation_with_options(self) -> None:
        """Should create app with all options."""
        provider = MockProvider()
        app = ui.create_app(
            provider,
            max_tokens=4096,
            auto_approve_tools=True,
            dry_run=True,
            system_prompt=_TEST_SYSTEM_PROMPT,
        )
        assert app._max_tokens == 4096
        assert app._auto_approve is True
        assert app._dry_run is True

    def test_get_message_count_initially_zero(self) -> None:
        """Message count should be zero initially."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)
        assert app.get_message_count() == 0

    def test_is_processing_initially_false(self) -> None:
        """Should not be processing initially."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)
        assert app.is_processing() is False


class TestBrynhildAppAsync:
    """Async tests for BrynhildApp using Textual pilot."""

    @_pytest.mark.asyncio
    async def test_app_mounts(self) -> None:
        """App should mount and compose correctly."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)

        async with app.run_test():
            # Check that key components exist
            assert app.query_one("#messages-container") is not None
            assert app.query_one("#prompt-input") is not None

    @_pytest.mark.asyncio
    async def test_welcome_message_shown(self) -> None:
        """Welcome message should be shown initially."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)

        async with app.run_test():
            welcome = app.query_one("#welcome")
            # The welcome widget should exist
            assert welcome is not None

    @_pytest.mark.asyncio
    async def test_input_submission(self) -> None:
        """Submitting input should add user message."""
        provider = MockProvider(["Test response"])
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)

        async with app.run_test() as pilot:
            # Type and submit
            await pilot.click("#prompt-input")
            await pilot.press("h", "e", "l", "l", "o")
            await pilot.press("enter")

            # Wait for processing
            await pilot.pause()

            # Should have messages in history
            assert app.get_message_count() >= 1

    @_pytest.mark.asyncio
    async def test_clear_action(self) -> None:
        """Clear action should reset messages."""
        provider = MockProvider()
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)

        async with app.run_test():
            # Add a message first
            app._messages.append({"role": "user", "content": "test"})
            assert app.get_message_count() == 1

            # Clear
            app.action_clear()
            assert app.get_message_count() == 0

    @_pytest.mark.asyncio
    async def test_send_message_for_test_hook(self) -> None:
        """Test hook should allow programmatic message sending."""
        provider = MockProvider(["Programmatic response"])
        app = ui.create_app(provider, system_prompt=_TEST_SYSTEM_PROMPT)

        async with app.run_test() as pilot:
            await app.send_message_for_test("Hello from test")
            await pilot.pause()

            # Should have at least user message recorded
            assert app.get_message_count() >= 1


class TestPermissionDialog:
    """Tests for PermissionDialog widget."""

    def test_dialog_creation(self) -> None:
        """Should create dialog with tool call info."""
        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
        )
        dialog = widgets.PermissionDialog(tool_call)
        assert "Bash" in dialog.border_title
        assert dialog._tool_call == tool_call


class TestPermissionScreen:
    """Tests for PermissionScreen modal."""

    def test_screen_has_cancel_binding(self) -> None:
        """Screen should have cancel keybinding."""
        import brynhild.ui.app as app_module

        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        screen = app_module.PermissionScreen(tool_call)

        # Check bindings include cancel
        binding_keys = [b.key for b in screen.BINDINGS]
        assert "c" in binding_keys
        assert "q" in binding_keys
        assert "ctrl+c" in binding_keys

    def test_screen_has_allow_deny_cancel_actions(self) -> None:
        """Screen should have all three action methods."""
        import brynhild.ui.app as app_module

        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        screen = app_module.PermissionScreen(tool_call)

        # Check all actions exist
        assert hasattr(screen, "action_allow")
        assert hasattr(screen, "action_deny")
        assert hasattr(screen, "action_cancel")

    def test_screen_return_type_allows_none(self) -> None:
        """Screen should return bool | None (None = cancel)."""
        import brynhild.ui.app as app_module
        import typing as _typing

        # Check the type annotation
        # PermissionScreen inherits from Screen[bool | None]
        origin = _typing.get_origin(app_module.PermissionScreen.__orig_bases__[0])  # type: ignore  # noqa: F841
        args = _typing.get_args(app_module.PermissionScreen.__orig_bases__[0])  # type: ignore

        # Should be Screen[bool | None]
        assert args == (bool | None,)

