"""Integration tests for tool call recovery from malformed model responses.

These tests simulate the scenario where an LLM places tool call JSON in its
thinking/analysis text instead of emitting a proper tool_call. The recovery
system should detect this and execute the tool anyway.

This exercises the full conversation processor pipeline with mocked providers.
"""

import typing as _typing

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.base as ui_base
import tests.conftest as conftest


class RecordingCallbacks(conversation.ConversationCallbacks):
    """Callbacks that record all events for detailed inspection."""

    def __init__(self, grant_permission: bool = True) -> None:
        self.grant_permission = grant_permission
        self.text_deltas: list[str] = []
        self.thinking_deltas: list[str] = []
        self.tool_calls: list[ui_base.ToolCallDisplay] = []
        self.tool_results: list[ui_base.ToolResultDisplay] = []
        self.info_messages: list[str] = []
        self.events: list[tuple[str, _typing.Any]] = []
        self._cancelled = False

    async def on_stream_start(self) -> None:
        self.events.append(("stream_start", None))

    async def on_stream_end(self) -> None:
        self.events.append(("stream_end", None))

    async def on_thinking_delta(self, text: str) -> None:
        self.thinking_deltas.append(text)
        self.events.append(("thinking_delta", text))

    async def on_thinking_complete(self, full_text: str) -> None:
        self.events.append(("thinking_complete", full_text))

    async def on_text_delta(self, text: str) -> None:
        self.text_deltas.append(text)
        self.events.append(("text_delta", text))

    async def on_text_complete(
        self, full_text: str, thinking: str | None
    ) -> None:
        self.events.append(("text_complete", (full_text, thinking)))

    async def on_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        self.tool_calls.append(tool_call)
        self.events.append(("tool_call", tool_call))

    async def request_tool_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,  # noqa: ARG002
    ) -> bool:
        self.events.append(("permission_request", None))
        return self.grant_permission

    async def on_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        self.tool_results.append(result)
        self.events.append(("tool_result", result))

    async def on_round_start(self, round_num: int) -> None:
        self.events.append(("round_start", round_num))

    async def on_info(self, message: str) -> None:
        self.info_messages.append(message)
        self.events.append(("info", message))

    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


class SemanticSearchTool(tools_base.Tool):
    """Mock semantic search tool for recovery tests."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_input: dict[str, _typing.Any] = {}

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return "Search for information in a corpus"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "corpus_key": {
                    "type": "string",
                    "description": "The corpus to search",
                },
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["corpus_key", "query"],
        }

    @property
    def requires_permission(self) -> bool:
        return False  # Skip permission for tests

    async def execute(
        self, input: dict[str, _typing.Any]
    ) -> tools_base.ToolResult:
        self.call_count += 1
        self.last_input = input
        return tools_base.ToolResult(
            success=True,
            output=f"Found 3 results for '{input.get('query', '')}'",
        )


@_pytest.mark.integration
class TestToolRecoveryIntegration:
    """Integration tests for tool call recovery from thinking text."""

    @_pytest.mark.asyncio
    async def test_recovers_tool_call_from_thinking_text(self) -> None:
        """Model puts tool JSON in thinking, processor recovers and executes it."""
        # Setup: Tool registry with semantic search
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Simulate malformed response: thinking contains tool JSON, no tool_use event
        # This is what gpt-oss-120b sometimes does
        malformed_thinking = '''Let me search for information about Python.

I'll use the semantic_search tool to find relevant documentation.

{"corpus_key": "docs", "query": "Python async await"}'''

        events1 = [
            # Thinking with embedded tool call JSON
            api_types.StreamEvent(type="thinking_delta", thinking=malformed_thinking),
            # NO tool_use_start event - this is the bug we're recovering from
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",  # Model thinks it's done, but didn't emit tool call
                usage=api_types.Usage(input_tokens=50, output_tokens=20),
            ),
        ]
        # Second response after tool execution
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Based on the search results, "),
            api_types.StreamEvent(type="text_delta", text="Python async/await is used for..."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=100, output_tokens=30),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = RecordingCallbacks()

        # Recovery config with recovery ENABLED
        recovery_config = conversation.RecoveryConfig(
            enabled=True,
            feedback_enabled=False,  # Disable feedback for cleaner test
        )

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=recovery_config,
        )

        # Execute
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Tell me about Python async"}],
            system_prompt="You are helpful.",
        )

        # Verify: Tool was recovered and executed
        assert tool.call_count == 1, "Tool should have been executed via recovery"
        assert tool.last_input == {"corpus_key": "docs", "query": "Python async await"}

        # Verify: Recovery info message was sent
        recovery_messages = [m for m in callbacks.info_messages if "Recovered" in m]
        assert len(recovery_messages) >= 1, "Should have info message about recovery"
        assert "semantic_search" in recovery_messages[0]

        # Verify: Tool call display shows is_recovered=True
        assert len(callbacks.tool_calls) == 1
        assert callbacks.tool_calls[0].is_recovered is True
        assert callbacks.tool_calls[0].tool_name == "semantic_search"

        # Verify: Conversation continued after tool execution
        assert "async/await" in result.response_text

    @_pytest.mark.asyncio
    async def test_no_recovery_when_disabled(self) -> None:
        """Recovery is skipped when recovery_config.enabled=False."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        malformed_thinking = '{"corpus_key": "docs", "query": "test"}'

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=malformed_thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events])
        callbacks = RecordingCallbacks()

        # Recovery DISABLED (default)
        recovery_config = conversation.RecoveryConfig(enabled=False)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            recovery_config=recovery_config,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Tool was NOT executed
        assert tool.call_count == 0, "Tool should not be executed when recovery disabled"
        assert len(callbacks.tool_calls) == 0

    @_pytest.mark.asyncio
    async def test_native_tool_calls_not_marked_as_recovered(self) -> None:
        """Normal tool calls (via tool_use_start) are not marked as recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Normal/native tool call via proper API
        events1 = [
            api_types.StreamEvent(type="text_delta", text="Let me search."),
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(
                    id="native-123",
                    name="semantic_search",
                    input={"corpus_key": "docs", "query": "native test"},
                ),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=20, output_tokens=10),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=30, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = RecordingCallbacks()

        recovery_config = conversation.RecoveryConfig(enabled=True)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=recovery_config,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Tool was executed
        assert tool.call_count == 1

        # Verify: Tool call is NOT marked as recovered
        assert len(callbacks.tool_calls) == 1
        assert callbacks.tool_calls[0].is_recovered is False
        assert callbacks.tool_calls[0].tool_id == "native-123"

    @_pytest.mark.asyncio
    async def test_recovery_session_budget_limits_recoveries(self) -> None:
        """Session-level recovery budget prevents excessive recoveries."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Create multiple rounds of malformed responses
        def make_malformed_events(query: str) -> list[api_types.StreamEvent]:
            return [
                api_types.StreamEvent(
                    type="thinking_delta",
                    thinking=f'{{"corpus_key": "docs", "query": "{query}"}}',
                ),
                api_types.StreamEvent(
                    type="message_stop",
                    stop_reason="stop",
                    usage=api_types.Usage(input_tokens=10, output_tokens=5),
                ),
            ]

        # 5 malformed responses (exceeds session budget of 3)
        stream_events = [
            make_malformed_events("q1"),
            make_malformed_events("q2"),
            make_malformed_events("q3"),
            make_malformed_events("q4"),
            make_malformed_events("q5"),
            # Final normal response
            [
                api_types.StreamEvent(type="text_delta", text="Done"),
                api_types.StreamEvent(
                    type="message_stop",
                    stop_reason="stop",
                    usage=api_types.Usage(input_tokens=10, output_tokens=5),
                ),
            ],
        ]

        provider = conftest.MockProvider(stream_events=stream_events)
        callbacks = RecordingCallbacks()

        recovery_config = conversation.RecoveryConfig(
            enabled=True,
            max_recoveries_per_turn=10,  # High per-turn limit
            max_recoveries_per_session=3,  # Low session limit
        )

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=recovery_config,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "search many times"}],
            system_prompt="test",
        )

        # Verify: Only 3 recoveries happened (session budget limit)
        assert tool.call_count == 3, f"Expected 3 calls (session budget), got {tool.call_count}"

    @_pytest.mark.asyncio
    async def test_recovery_loop_detection(self) -> None:
        """Same tool+args repeated triggers loop detection."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Same JSON repeated (loop scenario)
        repeated_thinking = '{"corpus_key": "docs", "query": "same query"}'

        stream_events = [
            # First time - should recover
            [
                api_types.StreamEvent(type="thinking_delta", thinking=repeated_thinking),
                api_types.StreamEvent(
                    type="message_stop",
                    stop_reason="stop",
                    usage=api_types.Usage(input_tokens=10, output_tokens=5),
                ),
            ],
            # Second time - same args, should detect loop
            [
                api_types.StreamEvent(type="thinking_delta", thinking=repeated_thinking),
                api_types.StreamEvent(
                    type="message_stop",
                    stop_reason="stop",
                    usage=api_types.Usage(input_tokens=10, output_tokens=5),
                ),
            ],
            # Final response
            [
                api_types.StreamEvent(type="text_delta", text="Done"),
                api_types.StreamEvent(
                    type="message_stop",
                    stop_reason="stop",
                    usage=api_types.Usage(input_tokens=10, output_tokens=5),
                ),
            ],
        ]

        provider = conftest.MockProvider(stream_events=stream_events)
        callbacks = RecordingCallbacks()

        recovery_config = conversation.RecoveryConfig(
            enabled=True,
            max_recoveries_per_turn=10,  # High budget
            max_recoveries_per_session=20,
        )

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=recovery_config,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Only 1 execution (loop detection blocked second)
        assert tool.call_count == 1, "Loop detection should block repeated recovery"

        # Verify: Loop detection message was sent
        loop_messages = [m for m in callbacks.info_messages if "loop" in m.lower()]
        assert len(loop_messages) >= 1, "Should have loop detection message"

    @_pytest.mark.asyncio
    async def test_high_impact_tool_not_recovered_by_default(self) -> None:
        """Tools with recovery_policy='deny' are not recovered."""

        class HighImpactTool(tools_base.Tool):
            """Tool that denies recovery."""

            def __init__(self) -> None:
                self.call_count = 0

            @property
            def name(self) -> str:
                return "dangerous_tool"

            @property
            def description(self) -> str:
                return "Dangerous operation"

            @property
            def input_schema(self) -> dict[str, _typing.Any]:
                return {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                    "required": ["command"],
                }

            @property
            def risk_level(self) -> str:
                return "high_impact"

            # recovery_policy defaults to "deny" for high_impact

            async def execute(
                self, input: dict[str, _typing.Any]  # noqa: ARG002
            ) -> tools_base.ToolResult:
                self.call_count += 1
                return tools_base.ToolResult(success=True, output="executed")

        tool = HighImpactTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events = [
            api_types.StreamEvent(
                type="thinking_delta",
                thinking='{"command": "rm -rf /"}',
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events])
        callbacks = RecordingCallbacks()

        recovery_config = conversation.RecoveryConfig(enabled=True)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            recovery_config=recovery_config,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Tool was NOT executed (recovery denied)
        assert tool.call_count == 0, "High-impact tool should not be recovered"

    @_pytest.mark.asyncio
    async def test_feedback_injection_after_recovery(self) -> None:
        """Feedback message is injected after recovery when enabled."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events1 = [
            api_types.StreamEvent(
                type="thinking_delta",
                thinking='{"corpus_key": "docs", "query": "test"}',
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Got it"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=50, output_tokens=10),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = RecordingCallbacks()

        recovery_config = conversation.RecoveryConfig(
            enabled=True,
            feedback_enabled=True,
        )

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=recovery_config,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Tool was recovered and executed
        assert tool.call_count == 1

        # Note: We can't directly verify feedback injection in messages without
        # inspecting the provider's received messages, but we can verify the
        # conversation completed successfully after recovery
        assert result.response_text == "Got it"


@_pytest.mark.integration
class TestRecoveryHeuristics:
    """Tests for specific recovery heuristics and edge cases."""

    @_pytest.mark.asyncio
    async def test_recovers_trailing_json(self) -> None:
        """JSON at the very end of thinking is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # JSON is at the very end - simplest case
        thinking = '''I need to search for information.

{"corpus_key": "docs", "query": "trailing json test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Found it."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "trailing json test"

    @_pytest.mark.asyncio
    async def test_recovers_json_with_trailing_whitespace(self) -> None:
        """JSON followed by whitespace is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''Searching now.

{"corpus_key": "docs", "query": "whitespace test"}

'''  # Note trailing newlines

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "whitespace test"

    @_pytest.mark.asyncio
    async def test_recovers_json_with_trailing_punctuation(self) -> None:
        """JSON followed by punctuation (period, etc) is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''Let me search.

{"corpus_key": "docs", "query": "punctuation test"}.'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "punctuation test"

    @_pytest.mark.asyncio
    async def test_recovers_json_with_trailing_comment(self) -> None:
        """JSON followed by comment text is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''Searching.

{"corpus_key": "docs", "query": "comment test"}
// This should find what we need'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "comment test"

    @_pytest.mark.asyncio
    async def test_recovers_json_with_trailing_xml_tag(self) -> None:
        """JSON followed by XML/closing tag is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''<tool_call>
{"corpus_key": "docs", "query": "xml tag test"}
</tool_call>'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "xml tag test"

    @_pytest.mark.asyncio
    async def test_recovers_json_embedded_in_middle(self) -> None:
        """JSON in middle of thinking (not at end) is recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''Let me think about this.

{"corpus_key": "docs", "query": "middle json test"}

That should give us the information we need to answer the question.'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "middle json test"

    @_pytest.mark.asyncio
    async def test_recovers_with_tool_name_in_context(self) -> None:
        """Tool name in context enables recovery when schema match fails.

        Schema matching requires ALL required fields. Context matching only
        requires SOME overlap with properties AND the tool name in text.

        This test uses JSON missing a required field (corpus_key), which would
        fail schema matching. But tool name "semantic_search" in context allows
        context matching to succeed.
        """
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # JSON is missing "corpus_key" (required), only has "query"
        # Schema matching would fail, but context matching should work
        # because "semantic_search" is mentioned and "query" is a valid property
        thinking = '''I'll use the semantic_search tool to find this.

{"query": "context match test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Context matching should have recovered this
        assert tool.call_count == 1, (
            "Tool should be called via context matching. "
            "If this fails, context matching may be broken."
        )
        assert tool.last_input["query"] == "context match test"

    @_pytest.mark.asyncio
    async def test_skips_json_in_example_context(self) -> None:
        """JSON preceded by 'Example:' or similar is skipped.

        CRITICAL: The "example" JSON must be AFTER the "real" JSON in the text,
        so that the anti-pattern detection is actually exercised. We search
        end-to-start, so we'll find the example first and must skip it.
        """
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # IMPORTANT: "real query" comes FIRST, "example" comes LAST (closer to end)
        # This forces anti-pattern detection to skip the example JSON
        thinking = '''Now let me actually search:
{"corpus_key": "docs", "query": "real query"}

Here's an example of the format:
{"corpus_key": "example", "query": "should skip this"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Anti-pattern detection should skip "example" (at end) and find "real query"
        assert tool.call_count == 1
        assert tool.last_input["query"] == "real query", (
            "Should have found 'real query', not the example. "
            "If this fails with 'should skip this', anti-pattern detection is broken."
        )

    @_pytest.mark.asyncio
    async def test_handles_multiple_json_objects_finds_matching_one(self) -> None:
        """With multiple JSON objects, finds the one matching a tool schema."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Multiple JSON objects - only one matches the tool schema
        thinking = '''Here's some data:
{"unrelated": "data", "foo": "bar"}

And now the search:
{"corpus_key": "docs", "query": "correct tool match"}

Some other JSON:
{"different": "structure"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Should find the one that matches semantic_search schema
        assert tool.call_count == 1
        assert tool.last_input["query"] == "correct tool match"

    @_pytest.mark.asyncio
    async def test_recovery_works_with_intent_phrases(self) -> None:
        """Recovery succeeds when intent phrases are present.

        Note: Intent phrase detection (has_intent_signal) is verified in unit tests.
        This integration test verifies recovery completes successfully with intent phrases.
        """
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # "I will call" is an intent phrase - recovery should still work
        thinking = '''I will call the search tool now.

{"corpus_key": "docs", "query": "intent phrase test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Recovery should succeed
        assert tool.call_count == 1
        assert tool.last_input["query"] == "intent phrase test"
        # Verify a recovery message was emitted
        recovery_messages = [m for m in callbacks.info_messages if "Recovered" in m]
        assert len(recovery_messages) >= 1

    @_pytest.mark.asyncio
    async def test_nested_json_handled_correctly(self) -> None:
        """Nested JSON objects are parsed correctly."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # JSON with nested structure (query contains JSON-like content)
        thinking = '''Search for config.

{"corpus_key": "configs", "query": "settings with {option: true}"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert "settings with {option: true}" in tool.last_input["query"]

    @_pytest.mark.asyncio
    async def test_recovers_from_double_newline_pattern(self) -> None:
        """The classic gpt-oss pattern: double newline then JSON."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # This is the exact pattern reported by CEGAI team
        thinking = '''Let me analyze this request and search for relevant information.


{"corpus_key": "knowledge_base", "query": "double newline pattern test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Based on the results..."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "double newline pattern test"

    @_pytest.mark.asyncio
    async def test_no_recovery_for_unmatched_json(self) -> None:
        """JSON that doesn't match any tool schema is not recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # JSON with wrong field names
        thinking = '''Some data:
{"wrong_field": "value", "also_wrong": "test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # No recovery - JSON doesn't match any tool
        assert tool.call_count == 0

    @_pytest.mark.asyncio
    async def test_no_recovery_for_invalid_json(self) -> None:
        """Malformed JSON is not recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        thinking = '''Broken JSON:
{"corpus_key": "docs", "query": broken}'''  # Missing quotes around 'broken'

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # No recovery - JSON is invalid
        assert tool.call_count == 0

    @_pytest.mark.asyncio
    async def test_multiple_tools_best_match_selected(self) -> None:
        """With multiple tools, the best schema match is selected."""

        class OtherSearchTool(tools_base.Tool):
            """Another search tool with different schema."""

            def __init__(self) -> None:
                self.call_count = 0

            @property
            def name(self) -> str:
                return "other_search"

            @property
            def description(self) -> str:
                return "Different search"

            @property
            def input_schema(self) -> dict[str, _typing.Any]:
                return {
                    "type": "object",
                    "properties": {
                        "search_term": {"type": "string"},
                    },
                    "required": ["search_term"],
                }

            @property
            def requires_permission(self) -> bool:
                return False

            async def execute(
                self, input: dict[str, _typing.Any]  # noqa: ARG002
            ) -> tools_base.ToolResult:
                self.call_count += 1
                return tools_base.ToolResult(success=True, output="other result")

        semantic_tool = SemanticSearchTool()
        other_tool = OtherSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(semantic_tool)
        registry.register(other_tool)

        # JSON matches semantic_search schema (corpus_key + query)
        thinking = '''Searching:
{"corpus_key": "docs", "query": "best match test"}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # semantic_search should be selected (better match)
        assert semantic_tool.call_count == 1
        assert other_tool.call_count == 0

    @_pytest.mark.asyncio
    async def test_very_long_thinking_with_json_at_end(self) -> None:
        """Long thinking text with JSON at end is still recovered."""
        tool = SemanticSearchTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Long analysis followed by JSON
        long_analysis = "This is a detailed analysis. " * 500  # ~15k chars
        thinking = f'''{long_analysis}

Based on all this analysis, I need to search:
{{"corpus_key": "docs", "query": "long thinking test"}}'''

        events = [
            api_types.StreamEvent(type="thinking_delta", thinking=thinking),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done."),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=5),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            recovery_config=conversation.RecoveryConfig(enabled=True),
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        assert tool.call_count == 1
        assert tool.last_input["query"] == "long thinking test"

