"""System tests for full tool execution pipeline."""

import pathlib as _pathlib
import typing as _typing

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.hooks.config as hooks_config
import brynhild.hooks.manager as hooks_manager
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.base as ui_base
import tests.conftest as conftest


class MinimalCallbacks(conversation.ConversationCallbacks):
    """Minimal callbacks for system tests."""

    def __init__(self) -> None:
        self.tool_results: list[ui_base.ToolResultDisplay] = []

    async def on_stream_start(self) -> None:
        pass

    async def on_stream_end(self) -> None:
        pass

    async def on_thinking_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_thinking_complete(self, full_text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:  # noqa: ARG002
        pass

    async def on_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:  # noqa: ARG002
        pass

    async def request_tool_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,  # noqa: ARG002
    ) -> bool:
        return True

    async def on_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        self.tool_results.append(result)

    async def on_round_start(self, round_num: int) -> None:  # noqa: ARG002
        pass

    def is_cancelled(self) -> bool:
        return False


@_pytest.mark.system
class TestToolPipelineSystem:
    """System tests for full tool execution pipeline."""

    @_pytest.mark.asyncio
    async def test_tool_chain_multiple_tools_in_sequence(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Multiple tools execute in sequence during a conversation."""
        # Setup: Registry with multiple tools
        tool1 = conftest.MockTool(name="Tool1", output="Result from Tool1")
        tool2 = conftest.MockTool(name="Tool2", output="Result from Tool2")
        registry = tools_registry.ToolRegistry()
        registry.register(tool1)
        registry.register(tool2)

        # Provider script: call Tool1, then Tool2, then respond
        events1 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="Tool1", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t2", name="Tool2", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=20, output_tokens=10),
            ),
        ]
        events3 = [
            api_types.StreamEvent(type="text_delta", text="Both tools completed"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=30, output_tokens=15),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2, events3])
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            cwd=tmp_path,
        )

        # Execute
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Use both tools"}],
            system_prompt="test",
        )

        # Verify: Both tools executed
        assert tool1.call_count == 1
        assert tool2.call_count == 1

        # Verify: Final response received
        assert "completed" in result.response_text.lower()

        # Verify: Both tool uses and results recorded
        assert len(result.tool_uses) == 2
        assert len(result.tool_results) == 2

    @_pytest.mark.asyncio
    async def test_tool_with_hook_blocking(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hook can block tool execution in the pipeline."""
        # Setup: Tool and blocking hook
        tool = conftest.MockTool(name="BlockedTool", output="Should not see this")
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Create blocking hook
        hook = hooks_config.HookDefinition(
            name="blocker",
            type="command",
            command="exit 1",  # Non-zero = block
            message="Tool blocked by security hook",
            match={"tool": "BlockedTool"},
        )
        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hook_mgr = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Provider requests the blocked tool
        events1 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="BlockedTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="I see it was blocked"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=10),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            hook_manager=hook_mgr,
            auto_approve_tools=True,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Use blocked tool"}],
            system_prompt="test",
        )

        # Verify: Tool was NOT executed (hook blocked it)
        assert tool.call_count == 0

        # Verify: Tool was blocked - check through the result
        # When blocked by hook, the tool execution is prevented
        assert len(result.tool_uses) == 1
        # The tool_result should indicate failure due to blocking
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is False

    @_pytest.mark.asyncio
    async def test_tool_with_hook_allowing(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hook can allow tool execution in the pipeline."""
        # Setup: Tool and allowing hook
        tool = conftest.MockTool(name="AllowedTool", output="Execution successful")
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Create allowing hook (exit 0 = continue)
        hook = hooks_config.HookDefinition(
            name="logger",
            type="command",
            command="exit 0",
        )
        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hook_mgr = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        events1 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="AllowedTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=10),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            hook_manager=hook_mgr,
            auto_approve_tools=True,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute
        await processor.process_streaming(
            messages=[{"role": "user", "content": "Use allowed tool"}],
            system_prompt="test",
        )

        # Verify: Tool WAS executed
        assert tool.call_count == 1

        # Verify: Tool result shows success
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0].result.success is True

    @_pytest.mark.asyncio
    async def test_tool_execution_with_input_validation(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Tool receives validated input from LLM."""

        class InputCapturingTool(tools_base.Tool):
            """Tool that captures its input for verification."""

            def __init__(self) -> None:
                self.captured_inputs: list[dict[str, _typing.Any]] = []

            @property
            def name(self) -> str:
                return "InputTool"

            @property
            def description(self) -> str:
                return "Captures input"

            @property
            def requires_permission(self) -> bool:
                return False

            @property
            def input_schema(self) -> dict[str, _typing.Any]:
                return {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "line_count": {"type": "integer"},
                    },
                    "required": ["filename"],
                }

            async def execute(
                self,
                input: dict[str, _typing.Any],
            ) -> tools_base.ToolResult:
                self.captured_inputs.append(input)
                return tools_base.ToolResult(
                    success=True,
                    output=f"Got: {input}",
                )

        tool = InputCapturingTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events1 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(
                    id="t1",
                    name="InputTool",
                    input={"filename": "test.py", "line_count": 42},
                ),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=20, output_tokens=10),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            cwd=tmp_path,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "read file"}],
            system_prompt="test",
        )

        # Verify: Tool received correct input
        assert len(tool.captured_inputs) == 1
        assert tool.captured_inputs[0]["filename"] == "test.py"
        assert tool.captured_inputs[0]["line_count"] == 42

