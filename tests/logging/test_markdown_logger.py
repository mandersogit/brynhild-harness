"""Tests for brynhild.logging.MarkdownLogger and export_log_to_markdown."""

import pathlib as _pathlib
import tempfile as _tempfile

import brynhild.logging as logging


class TestExportLogToMarkdown:
    """Tests for export_log_to_markdown function."""

    def test_basic_export(self) -> None:
        """Test exporting basic log events to markdown."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "20251205_120000",
                "provider": "openrouter",
                "model": "test-model",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Hello"},
            {"event_type": "assistant_message", "content": "Hi there!"},
            {"event_type": "usage", "input_tokens": 100, "output_tokens": 50},
        ]

        markdown = logging.export_log_to_markdown(events)

        assert "# Brynhild Session:" in markdown
        assert "**Model**: test-model" in markdown
        assert "**Provider**: openrouter" in markdown
        assert "### User" in markdown
        assert "Hello" in markdown
        assert "### Assistant" in markdown
        assert "Hi there!" in markdown
        assert "100 in / 50 out" in markdown

    def test_export_with_tools(self) -> None:
        """Test exporting logs with tool calls."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Read a file"},
            {
                "event_type": "tool_call",
                "tool_name": "Read",
                "tool_input": {"path": "/tmp/test.txt"},
            },
            {
                "event_type": "tool_result",
                "tool_name": "Read",
                "success": True,
                "output": "file contents",
            },
            {"event_type": "assistant_message", "content": "Done."},
        ]

        markdown = logging.export_log_to_markdown(events)

        assert "### 🔧 Tool: Read" in markdown
        assert '"/tmp/test.txt"' in markdown
        assert "✅ Success" in markdown
        assert "file contents" in markdown
        assert "Tools Used" in markdown
        assert "Read (1)" in markdown

    def test_export_with_thinking(self) -> None:
        """Test exporting logs with thinking."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Hello"},
            {"event_type": "thinking", "content": "Let me think about this..."},
            {"event_type": "assistant_message", "content": "Response"},
        ]

        # With thinking
        markdown = logging.export_log_to_markdown(events, include_thinking=True)
        assert "Let me think about this..." in markdown
        assert "<details>" in markdown

        # Without thinking
        markdown = logging.export_log_to_markdown(events, include_thinking=False)
        assert "Let me think about this..." not in markdown

    def test_export_with_custom_title(self) -> None:
        """Test exporting with custom title."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Hello"},
        ]

        markdown = logging.export_log_to_markdown(events, title="Custom Title")
        assert "# Brynhild Session: Custom Title" in markdown

    def test_export_with_error(self) -> None:
        """Test exporting logs with errors."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Hello"},
            {"event_type": "error", "error": "Something went wrong", "context": "API call"},
        ]

        markdown = logging.export_log_to_markdown(events)
        assert "### ❌ Error" in markdown
        assert "Something went wrong" in markdown
        assert "API call" in markdown

    def test_export_finish_tool(self) -> None:
        """Test Finish tool renders as Task Complete section."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Do something"},
            {"event_type": "assistant_message", "content": "Done."},
            {
                "event_type": "tool_call",
                "tool_name": "Finish",
                "tool_input": {
                    "status": "success",
                    "summary": "Completed the task.",
                    "next_steps": "Review the output.",
                },
            },
            {
                "event_type": "tool_result",
                "tool_name": "Finish",
                "success": True,
                "output": "Task finished",
            },
        ]

        markdown = logging.export_log_to_markdown(events)

        # Should have Task Complete section
        assert "### ✅ Task Complete" in markdown
        assert "**Status:** Success" in markdown
        assert "**Summary:** Completed the task." in markdown
        assert "**Next Steps:**" in markdown
        assert "Review the output." in markdown

        # Should NOT have Finish as a tool call or result
        assert "### 🔧 Tool: Finish" not in markdown
        assert "Task finished" not in markdown  # tool_result output

    def test_export_skips_finish_json_in_assistant(self) -> None:
        """Test that raw Finish JSON in assistant messages is skipped."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "test",
                "provider": "test",
                "model": "test",
                "timestamp": "2025-12-05T12:00:00",
            },
            {"event_type": "user_message", "content": "Do something"},
            {
                "event_type": "assistant_message",
                "content": '{"status":"success","summary":"Task done."}',
            },
        ]

        markdown = logging.export_log_to_markdown(events)

        # Raw JSON should not appear
        assert '{"status":"success"' not in markdown


class TestMarkdownLogger:
    """Tests for MarkdownLogger."""

    def test_basic_conversation(self) -> None:
        """Test logging a basic conversation produces valid markdown."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                title="Test Session",
                provider="test-provider",
                model="test-model",
                profile="test-profile",
            )
            logger.log_session_start("20251205_120000")
            logger.log_user_message("Hello, how are you?")
            logger.log_assistant_message("I'm doing well, thank you!")
            logger.close()

            content = output_path.read_text()

            # Check header
            assert "# Brynhild Session: Test Session" in content
            assert "**Model**: test-model" in content
            assert "**Provider**: test-provider" in content
            assert "**Profile**: test-profile" in content

            # Check conversation
            assert "### User" in content
            assert "Hello, how are you?" in content
            assert "### Assistant" in content
            assert "I'm doing well, thank you!" in content

    def test_tool_call_and_result(self) -> None:
        """Test logging tool calls and results."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Read a file")
            logger.log_tool_call(
                tool_name="Read",
                tool_input={"path": "/tmp/test.txt"},
                tool_id="call_123",
            )
            logger.log_tool_result(
                tool_name="Read",
                success=True,
                output="file contents here",
                tool_id="call_123",
            )
            logger.log_assistant_message("Here's the content.")
            logger.close()

            content = output_path.read_text()

            # Check tool call
            assert "### 🔧 Tool: Read" in content
            assert '"path": "/tmp/test.txt"' in content

            # Check tool result
            assert "✅ Success" in content
            assert "file contents here" in content

    def test_tool_failure(self) -> None:
        """Test logging failed tool results."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_tool_call(
                tool_name="Bash",
                tool_input={"command": "invalid"},
            )
            logger.log_tool_result(
                tool_name="Bash",
                success=False,
                error="Permission denied",
            )
            logger.close()

            content = output_path.read_text()

            assert "❌ Failed" in content
            assert "Permission denied" in content

    def test_thinking_collapsible(self) -> None:
        """Test thinking is rendered as collapsible by default."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                include_thinking=True,
                thinking_style="collapsible",
            )
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_assistant_message(
                "Response text",
                thinking="This is my reasoning process.",
            )
            logger.close()

            content = output_path.read_text()

            assert "<details>" in content
            assert "<summary>💭 Thinking" in content
            assert "This is my reasoning process." in content
            assert "</details>" in content

    def test_thinking_hidden(self) -> None:
        """Test thinking can be hidden."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                include_thinking=True,
                thinking_style="hidden",
            )
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_assistant_message(
                "Response text",
                thinking="This should not appear.",
            )
            logger.close()

            content = output_path.read_text()

            assert "This should not appear." not in content

    def test_thinking_disabled(self) -> None:
        """Test thinking can be completely disabled."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                include_thinking=False,
            )
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_assistant_message(
                "Response text",
                thinking="This should not appear.",
            )
            logger.close()

            content = output_path.read_text()

            assert "Thinking" not in content
            assert "This should not appear." not in content

    def test_finish_tool(self) -> None:
        """Test logging Finish tool calls."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Complete the task")
            logger.log_finish(
                status="success",
                summary="Task completed successfully.",
                next_steps="Review the changes.",
            )
            logger.close()

            content = output_path.read_text()

            assert "### ✅ Task Complete" in content
            assert "**Status:** Success" in content
            assert "**Summary:** Task completed successfully." in content
            assert "**Next Steps:**" in content
            assert "Review the changes." in content

    def test_error_logging(self) -> None:
        """Test logging errors."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_error("Something went wrong", context="API call failed")
            logger.close()

            content = output_path.read_text()

            assert "### ❌ Error" in content
            assert "Something went wrong" in content
            assert "**Context:** API call failed" in content

    def test_usage_tracking(self) -> None:
        """Test token usage is tracked in summary."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_usage(input_tokens=1000, output_tokens=500, cost=0.01)
            logger.close()

            content = output_path.read_text()

            assert "1,000 in / 500 out" in content
            assert "$0.0100" in content

    def test_tools_used_tracking(self) -> None:
        """Test tools used are tracked in summary."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_tool_call("Read", {"path": "/a"})
            logger.log_tool_result("Read", True, "content")
            logger.log_tool_call("Read", {"path": "/b"})
            logger.log_tool_result("Read", True, "content")
            logger.log_tool_call("Write", {"path": "/c", "content": "x"})
            logger.log_tool_result("Write", True, "written")
            logger.close()

            content = output_path.read_text()

            assert "Tools Used" in content
            assert "Read (2)" in content
            assert "Write (1)" in content

    def test_truncation(self) -> None:
        """Test long content is truncated."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                truncate_tool_output=100,
            )
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_tool_call("Read", {"long": "x" * 200})
            logger.close()

            content = output_path.read_text()

            assert "... [truncated]" in content
            assert "x" * 200 not in content

    def test_context_manager(self) -> None:
        """Test using logger as context manager."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            with logging.MarkdownLogger(output_path=output_path) as logger:
                logger.log_session_start("test")
                logger.log_user_message("Hello")
                logger.log_assistant_message("Hi")

            content = output_path.read_text()
            assert "Hello" in content
            assert "Hi" in content

    def test_thinking_via_log_thinking(self) -> None:
        """Test thinking logged via log_thinking before assistant message."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(
                output_path=output_path,
                include_thinking=True,
                thinking_style="collapsible",
            )
            logger.log_session_start("test")
            logger.log_user_message("Test")
            logger.log_thinking("First I will think about this.")
            logger.log_assistant_message("Here's my response.")
            logger.close()

            content = output_path.read_text()

            # Thinking should be attached to the assistant message
            assert "First I will think about this." in content
            assert "<details>" in content

    def test_default_title_from_session_id(self) -> None:
        """Test default title uses session ID when no title specified."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("20251205_143022")
            logger.log_user_message("Test")
            logger.close()

            content = output_path.read_text()

            assert "Session 20251205_143022" in content

    def test_multiple_user_messages(self) -> None:
        """Test multiple user/assistant exchanges."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            output_path = _pathlib.Path(tmpdir) / "test.md"

            logger = logging.MarkdownLogger(output_path=output_path)
            logger.log_session_start("test")
            logger.log_user_message("First question")
            logger.log_assistant_message("First answer")
            logger.log_user_message("Second question")
            logger.log_assistant_message("Second answer")
            logger.close()

            content = output_path.read_text()

            # Check order is preserved
            first_q = content.find("First question")
            first_a = content.find("First answer")
            second_q = content.find("Second question")
            second_a = content.find("Second answer")

            assert first_q < first_a < second_q < second_a

