"""
Tests for JSON renderer bugs.

These tests expose real bugs found during code review.
"""

import io as _io
import json as _json

import brynhild.core.types as core_types
import brynhild.tools.base as tools_base
import brynhild.ui.json_renderer as json_renderer


class TestJSONRendererBugs:
    """Tests for JSON renderer bugs."""

    def test_bug_reset_doesnt_clear_finish_result(self) -> None:
        """
        BUG: reset() doesn't clear _finish_result.

        If someone calls reset() to start a new conversation after
        one that used the Finish tool, the old finish result persists.
        """
        output = _io.StringIO()
        renderer = json_renderer.JSONRenderer(output)

        # First conversation - agent calls Finish
        renderer.show_assistant_text("Done!")
        renderer.show_finish(
            status="success",
            summary="Completed task",
            next_steps=None,
        )

        # Reset for new conversation
        renderer.reset()

        # Second conversation - NO finish tool
        renderer.show_assistant_text("Hello!")

        # Finalize
        renderer.finalize()
        output_str = output.getvalue()

        # BUG: The old finish result should NOT be in the output!
        result = _json.loads(output_str)
        assert "finish" not in result, (
            f"BUG: Old finish result persisted after reset()! Got: {result.get('finish')}"
        )

    def test_reset_clears_all_state(self) -> None:
        """Verify reset() clears ALL accumulated state."""
        output = _io.StringIO()
        renderer = json_renderer.JSONRenderer(output)

        # Accumulate various state
        renderer.show_user_message("User message")
        renderer.show_assistant_text("Assistant text")

        # Create mock tool call/result objects
        tool_call = core_types.ToolCallDisplay(
            tool_name="TestTool",
            tool_input={"arg": "value"},
            tool_id="test-123",
            is_recovered=False,
        )
        renderer.show_tool_call(tool_call)

        tool_result = core_types.ToolResultDisplay(
            tool_name="TestTool",
            tool_id="test-123",
            result=tools_base.ToolResult(success=True, output="output", error=None),
        )
        renderer.show_tool_result(tool_result)

        renderer.show_error("Test error")
        renderer.show_finish(status="success", summary="Done")

        # Reset
        renderer.reset()

        # All internal state should be cleared
        assert renderer._messages == []
        assert renderer._tool_calls == []
        assert renderer._tool_results == []
        assert renderer._errors == []
        assert renderer._assistant_text == ""
        assert renderer._streaming is False
        assert renderer._finish_result is None  # This is the BUG!
