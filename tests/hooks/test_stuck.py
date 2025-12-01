"""Tests for stuck detection."""

import brynhild.hooks.stuck as stuck
import brynhild.tools.base as tools_base


class TestStuckDetector:
    """Tests for StuckDetector class."""

    def test_not_stuck_initially(self) -> None:
        """New detector reports not stuck."""
        detector = stuck.StuckDetector()
        state = detector.check()
        assert state.is_stuck is False

    def test_single_tool_call_not_stuck(self) -> None:
        """Single tool call doesn't trigger stuck."""
        detector = stuck.StuckDetector()
        detector.record_tool_call("Bash", {"command": "ls"})
        state = detector.check()
        assert state.is_stuck is False

    def test_repeated_tool_calls_triggers_stuck(self) -> None:
        """Same tool call repeated N times triggers stuck."""
        detector = stuck.StuckDetector(repeat_threshold=3)

        # Same call 3 times
        for _ in range(3):
            detector.record_tool_call("Bash", {"command": "ls"})

        state = detector.check()
        assert state.is_stuck is True
        assert "repeated" in state.reason.lower()  # type: ignore[union-attr]
        assert state.suggestion is not None

    def test_different_tool_calls_not_stuck(self) -> None:
        """Different tool calls don't trigger stuck."""
        detector = stuck.StuckDetector(repeat_threshold=3)

        detector.record_tool_call("Bash", {"command": "ls"})
        detector.record_tool_call("Bash", {"command": "pwd"})
        detector.record_tool_call("Bash", {"command": "whoami"})

        state = detector.check()
        assert state.is_stuck is False

    def test_repeated_errors_triggers_stuck(self) -> None:
        """Same error repeated N times triggers stuck."""
        detector = stuck.StuckDetector(error_repeat_threshold=3)

        error_result = tools_base.ToolResult(
            success=False,
            output="",
            error="Command not found: foo",
        )

        # Same error 3 times
        for _ in range(3):
            detector.record_tool_result("Bash", error_result)

        state = detector.check()
        assert state.is_stuck is True
        assert "error" in state.reason.lower()  # type: ignore[union-attr]

    def test_different_errors_not_stuck(self) -> None:
        """Different errors don't trigger stuck."""
        detector = stuck.StuckDetector(error_repeat_threshold=3)

        for i in range(3):
            result = tools_base.ToolResult(
                success=False,
                output="",
                error=f"Error {i}",
            )
            detector.record_tool_result("Bash", result)

        state = detector.check()
        assert state.is_stuck is False

    def test_success_results_not_counted(self) -> None:
        """Successful results don't count toward error threshold."""
        detector = stuck.StuckDetector(error_repeat_threshold=3)

        success = tools_base.ToolResult(success=True, output="ok")
        for _ in range(5):
            detector.record_tool_result("Bash", success)

        state = detector.check()
        assert state.is_stuck is False

    def test_no_progress_triggers_stuck(self) -> None:
        """No tool use for N messages triggers stuck."""
        detector = stuck.StuckDetector(no_progress_threshold=3)

        # 3 messages without tool use
        for _ in range(3):
            detector.record_assistant_message(had_tool_use=False)

        state = detector.check()
        assert state.is_stuck is True
        assert "tool" in state.reason.lower()  # type: ignore[union-attr]

    def test_tool_use_resets_no_progress(self) -> None:
        """Tool use resets the no-progress counter."""
        detector = stuck.StuckDetector(no_progress_threshold=3)

        # 2 messages without tool use
        detector.record_assistant_message(had_tool_use=False)
        detector.record_assistant_message(had_tool_use=False)

        # Then a message with tool use
        detector.record_assistant_message(had_tool_use=True)

        # Then 2 more without
        detector.record_assistant_message(had_tool_use=False)
        detector.record_assistant_message(had_tool_use=False)

        # Should not be stuck (counter was reset)
        state = detector.check()
        assert state.is_stuck is False

    def test_reset_clears_history(self) -> None:
        """reset() clears all tracking state."""
        detector = stuck.StuckDetector(repeat_threshold=3)

        # Get close to stuck
        for _ in range(2):
            detector.record_tool_call("Bash", {"command": "ls"})

        # Reset
        detector.reset()

        # More calls should not trigger stuck
        detector.record_tool_call("Bash", {"command": "ls"})

        state = detector.check()
        assert state.is_stuck is False

    def test_suggestions_are_helpful(self) -> None:
        """Suggestions contain actionable advice."""
        detector = stuck.StuckDetector(repeat_threshold=2)

        for _ in range(2):
            detector.record_tool_call("Bash", {"command": "ls"})

        state = detector.check()
        assert state.suggestion is not None
        # Should suggest trying something different
        assert "different" in state.suggestion.lower() or "approach" in state.suggestion.lower()

    def test_tool_call_with_different_input_not_stuck(self) -> None:
        """Same tool with different inputs doesn't trigger stuck."""
        detector = stuck.StuckDetector(repeat_threshold=3)

        detector.record_tool_call("Read", {"file_path": "file1.txt"})
        detector.record_tool_call("Read", {"file_path": "file2.txt"})
        detector.record_tool_call("Read", {"file_path": "file3.txt"})

        state = detector.check()
        assert state.is_stuck is False

