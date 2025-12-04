"""
Developer tools and demos (hidden from main CLI help).

This module provides commands for testing and demonstrating
Brynhild features during development.
"""

import asyncio as _asyncio
import typing as _typing

import click as _click

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.core.conversation as core_conversation
import brynhild.core.tool_recovery as tool_recovery
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.adapters as ui_adapters
import brynhild.ui.base as ui_base
import brynhild.ui.json_renderer as json_renderer
import brynhild.ui.rich_renderer as rich_renderer

# =============================================================================
# Mock Tools for Demos
# =============================================================================


class MockSemanticSearch(tools_base.Tool):
    """Mock semantic search tool for demos."""

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return "Search for information in the knowledge base"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        query = input.get("query", "")
        return tools_base.ToolResult(
            success=True,
            output=(
                f"Search results for '{query}':\n"
                "1. AsyncIO Best Practices Guide\n"
                "2. Python Concurrency Patterns\n"
                "3. Await vs Threading comparison"
            ),
        )


class MockFileRead(tools_base.Tool):
    """Mock file read tool for demos."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read a file from the filesystem"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        _ = input  # unused in mock
        return tools_base.ToolResult(
            success=True,
            output="# AsyncIO Best Practices\n\nWhen working with async/await...",
        )


# =============================================================================
# Mock Provider for Demos
# =============================================================================


class RecoveryDemoProvider(api_base.LLMProvider):
    """Mock provider that simulates a model emitting tool calls in thinking."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def name(self) -> str:
        return "demo"

    @property
    def model(self) -> str:
        return "recovery-demo-model"

    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[api_types.Tool] | None = None,
        max_tokens: int = 4096,
        use_profile: bool = True,
    ) -> api_types.CompletionResponse:
        # Silence unused args (mock doesn't need them)
        _ = messages, system, tools, max_tokens, use_profile
        """Return scripted responses to demo recovery."""
        self._call_count += 1

        if self._call_count == 1:
            # First call: emit tool call JSON in thinking (recovery needed)
            return api_types.CompletionResponse(
                id="demo_1",
                content="",
                thinking=(
                    "I need to search for information about Python async patterns.\n\n"
                    "Let me use the semantic_search tool to find relevant documentation.\n\n"
                    '{"name": "semantic_search", "input": {"query": "Python async patterns"}}'
                ),
                tool_uses=[],  # No proper tool call - it's in thinking!
                usage=api_types.Usage(input_tokens=100, output_tokens=50),
                stop_reason="end_turn",
            )
        elif self._call_count == 2:
            # Second call: emit proper tool call (native)
            return api_types.CompletionResponse(
                id="demo_2",
                content="",
                thinking="Now I'll read the documentation file for more details.",
                tool_uses=[
                    api_types.ToolUse(
                        id="native_001",
                        name="file_read",
                        input={"path": "/docs/async-guide.md"},
                    )
                ],
                usage=api_types.Usage(input_tokens=150, output_tokens=30),
                stop_reason="tool_use",
            )
        else:
            # Final response
            return api_types.CompletionResponse(
                id="demo_3",
                content=(
                    "Based on my search and the documentation, here are the key "
                    "Python async patterns:\n\n"
                    "1. **Use `async with` for context managers** - Ensures proper cleanup\n"
                    "2. **Prefer `asyncio.gather()` for concurrent tasks** - More efficient\n"
                    "3. **Avoid blocking calls** - Use `run_in_executor()` for sync operations"
                ),
                thinking=None,
                tool_uses=[],
                usage=api_types.Usage(input_tokens=200, output_tokens=100),
                stop_reason="end_turn",
            )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[api_types.Tool] | None = None,
        max_tokens: int = 4096,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        """Stream version - just wraps complete() for demo."""
        response = await self.complete(
            messages,
            system=system,
            max_tokens=max_tokens,
            tools=tools,
            use_profile=use_profile,
        )

        # Message start
        yield api_types.StreamEvent(
            type="message_start",
            message_id=response.id,
        )

        # Emit thinking if present
        if response.thinking:
            yield api_types.StreamEvent(
                type="thinking_delta",
                thinking=response.thinking,
            )

        # Emit content if present
        if response.content:
            yield api_types.StreamEvent(
                type="text_delta",
                text=response.content,
            )

        # Emit tool uses if present
        for tool_use in response.tool_uses:
            yield api_types.StreamEvent(
                type="tool_use_start",
                tool_use=tool_use,
            )

        # Final event
        yield api_types.StreamEvent(
            type="message_stop",
            stop_reason=response.stop_reason,
            usage=response.usage,
        )


# =============================================================================
# CLI Group
# =============================================================================


@_click.group(name="dev", hidden=True)
def dev_group() -> None:
    """Developer tools and demos (hidden from help)."""
    pass


# =============================================================================
# Demo Commands
# =============================================================================


@dev_group.command(name="demo-recovery")
@_click.option("--tui", is_flag=True, help="Run in interactive TUI mode")
@_click.option("--json", "json_output", is_flag=True, help="JSON output (CLI mode only)")
def demo_recovery(tui: bool, json_output: bool) -> None:
    """Demo the tool call recovery through the real processor.

    Runs a simulated conversation where a mock model emits tool calls
    in its thinking instead of as proper tool calls, triggering the
    recovery mechanism through the real ConversationProcessor.

    Use --tui to run in the interactive TUI (type any message to trigger).
    """
    import rich.console as _rich_console

    # Create tool registry with mock tools
    registry = tools_registry.ToolRegistry()
    registry.register(MockSemanticSearch())
    registry.register(MockFileRead())

    # Create mock provider
    provider = RecoveryDemoProvider()

    # Create recovery config with recovery ENABLED
    recovery_config = core_conversation.RecoveryConfig(
        enabled=True,
        feedback_enabled=False,  # Don't inject feedback for cleaner demo
    )

    if tui:
        # Run in TUI mode
        import brynhild.ui as ui

        app = ui.create_app(
            provider=provider,
            tool_registry=registry,
            max_tokens=4096,
            auto_approve_tools=True,
            system_prompt=(
                "You are a demo assistant. The mock provider will return "
                "scripted responses to demonstrate tool call recovery. "
                "Type any message to see the demo."
            ),
            recovery_config=recovery_config,
        )
        app.run()
        return

    # CLI mode
    console = _rich_console.Console()

    # Create renderer
    if json_output:
        renderer: ui_base.Renderer = json_renderer.JSONRenderer()
    else:
        renderer = rich_renderer.RichConsoleRenderer()

    # Create callbacks
    callbacks = ui_adapters.RendererCallbacks(
        renderer,
        auto_approve=True,  # Auto-approve for demo
        verbose=False,
    )

    processor = core_conversation.ConversationProcessor(
        provider=provider,
        callbacks=callbacks,
        tool_registry=registry,
        max_tokens=4096,
        auto_approve_tools=True,
        recovery_config=recovery_config,
    )

    # Header
    console.print("\n" + "=" * 60)
    console.print("  TOOL RECOVERY DEMO (Real Processor)", style="bold")
    console.print("=" * 60)
    console.print("\nThis demo runs through the real ConversationProcessor.")
    console.print("The mock model will:")
    console.print("  1. Emit a tool call JSON in thinking (recovery needed)")
    console.print("  2. Emit a proper native tool call")
    console.print("  3. Provide a final response")
    console.print("\nTip: Use --tui to run in interactive TUI mode")
    console.print("\n" + "-" * 60 + "\n")

    # Run the conversation
    async def run() -> core_conversation.ConversationResult:
        return await processor.process_streaming(
            messages=[{"role": "user", "content": "Search for Python async patterns"}],
            system_prompt="You are a helpful assistant.",
        )

    result = _asyncio.run(run())

    # Summary
    console.print("\n" + "=" * 60)
    console.print("  SUMMARY", style="bold")
    console.print("=" * 60)
    console.print(f"\nRecoveries this session: [orange3]{processor.recovery_count}[/]")
    console.print(f"Stop reason: {result.stop_reason}")
    console.print(f"Total tokens: {result.input_tokens + result.output_tokens}")
    console.print("\nRecovered calls show with [orange3]orange border[/] and ↺ icon")
    console.print("")

    if json_output:
        renderer.finalize()


@dev_group.command(name="demo-recovery-scenarios")
def demo_recovery_scenarios() -> None:
    """Demo various recovery scenarios with different JSON positions."""
    import rich.console as _rich_console

    console = _rich_console.Console()

    # Create registry with mock tool
    registry = tools_registry.ToolRegistry()
    registry.register(MockSemanticSearch())

    scenarios = [
        (
            "Trailing JSON (most common)",
            """I should search for this information.

{"name": "semantic_search", "input": {"query": "test"}}""",
        ),
        (
            "JSON with trailing punctuation",
            """Let me search for that.

{"name": "semantic_search", "input": {"query": "test"}}.""",
        ),
        (
            "JSON with trailing XML tag",
            """I'll perform a search.

{"name": "semantic_search", "input": {"query": "test"}}</think>""",
        ),
        (
            "JSON in middle of text",
            """First I'll search {"name": "semantic_search", "input": {"query": "test"}} and then analyze.""",
        ),
        (
            "Multiple JSON objects (last one wins)",
            """First search: {"name": "semantic_search", "input": {"query": "first"}}
Now another: {"name": "semantic_search", "input": {"query": "second"}}""",
        ),
    ]

    console.print("\n" + "=" * 60)
    console.print("  RECOVERY SCENARIOS DEMO", style="bold")
    console.print("=" * 60)

    for title, thinking in scenarios:
        console.print(f"\n[bold]{title}[/bold]")
        console.print("-" * 40)
        console.print(f"Input:\n{thinking}\n")

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking,
            registry,
            model_recovery_enabled=True,
        )

        if result:
            console.print(f"[green]✓[/green] Recovered: {result.tool_use.name}")
            console.print(f"  Type: {result.recovery_type}")
            console.print(f"  Position: {result.json_position}/{result.text_length}")
            console.print(f"  Candidates tried: {result.candidates_tried}")
            if result.tool_use.input:
                console.print(f"  Input: {result.tool_use.input}")
        else:
            console.print("[red]✗[/red] No recovery (no matching tool or invalid JSON)")

    console.print("\n")
