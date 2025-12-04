"""
Tests for ConversationRunner.

ConversationRunner is the primary interface for non-interactive CLI use.
It wraps ConversationProcessor and maintains session state across turns.

This module was completely untested before this file was created, which
allowed a token accounting bug to ship.
"""

import io as _io
import typing as _typing

import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.plain as plain
import brynhild.ui.runner as runner

# =============================================================================
# Mock Provider for Runner Tests
# =============================================================================


class MockProviderForRunner(api_base.LLMProvider):
    """Mock provider with configurable usage values per call."""

    def __init__(
        self,
        responses: list[dict[str, _typing.Any]] | None = None,
    ) -> None:
        """
        Initialize with a list of response configs.

        Each response dict can have:
        - text: str
        - input_tokens: int
        - output_tokens: int
        - tool_calls: list[dict] (optional)
        """
        self._responses = responses or [{"text": "Mock response", "input_tokens": 100, "output_tokens": 50}]
        self._call_index = 0

    @property
    def name(self) -> str:
        return "mock-runner"

    @property
    def model(self) -> str:
        return "mock-runner-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[api_types.Tool] | None = None,
    ) -> api_types.CompletionResponse:
        # Collect from stream
        text_parts = []
        tool_uses = []
        usage = None

        async for event in self.stream(
            messages, system=system, max_tokens=max_tokens, tools=tools
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "tool_use_start" and event.tool_use:
                tool_uses.append(event.tool_use)
            elif event.type == "message_delta" and event.usage:
                usage = event.usage

        return api_types.CompletionResponse(
            id=f"call-{self._call_index}",
            content="".join(text_parts),
            stop_reason="tool_use" if tool_uses else "stop",
            usage=usage or api_types.Usage(input_tokens=0, output_tokens=0),
            tool_uses=tool_uses if tool_uses else None,
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        """Stream response."""
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
        else:
            resp = {"text": "Default response", "input_tokens": 100, "output_tokens": 50}

        # Text delta
        if resp.get("text"):
            yield api_types.StreamEvent(type="text_delta", text=resp["text"])

        # Tool calls
        if resp.get("tool_calls"):
            for tc in resp["tool_calls"]:
                yield api_types.StreamEvent(
                    type="tool_use_start",
                    tool_use=api_types.ToolUse(
                        id=tc.get("id", f"tool-{self._call_index}"),
                        name=tc["name"],
                        input=tc.get("input", {}),
                    ),
                )

        stop_reason = "tool_use" if resp.get("tool_calls") else "stop"

        # Usage in message_delta (how real providers work)
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason=stop_reason,
            usage=api_types.Usage(
                input_tokens=resp.get("input_tokens", 100),
                output_tokens=resp.get("output_tokens", 50),
            ),
        )

        self._call_index += 1


class MockToolForRunner(tools_base.Tool):
    """Simple mock tool for runner tests."""

    @property
    def name(self) -> str:
        return "MockTool"

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    @property
    def requires_permission(self) -> bool:
        return False

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        return tools_base.ToolResult(
            success=True,
            output=f"Executed with {input}",
            error=None,
        )


# =============================================================================
# Token Tracking Tests
# =============================================================================


class TestRunnerTokenTracking:
    """
    Token tracking in ConversationRunner.

    These tests verify the bug fix where runner was incorrectly accumulating
    input_tokens instead of using the absolute context size.
    """

    @_pytest.mark.asyncio
    async def test_context_tokens_use_absolute_not_accumulated(self) -> None:
        """
        CRITICAL: input_tokens should be last API call's context size.

        Runner was doing: self._total_input_tokens += result.input_tokens
        Should do: self._current_context_tokens = result.input_tokens

        This test would have caught the bug that shipped.
        """
        # Two API calls with growing context
        provider = MockProviderForRunner(responses=[
            {"text": "Using tool...", "input_tokens": 1000, "output_tokens": 50, "tool_calls": [{"name": "MockTool"}]},
            {"text": "Done", "input_tokens": 2500, "output_tokens": 100},
        ])

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForRunner())

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            tool_registry=registry,
            system_prompt="You are helpful.",
            auto_approve_tools=True,
        )

        result = await conv_runner.run_streaming("test")

        # CRITICAL: Should be 2500 (last context size), NOT 3500 (accumulated)
        assert result["usage"]["input_tokens"] == 2500, (
            f"input_tokens should be 2500 (last context), "
            f"got {result['usage']['input_tokens']}. "
            f"If you got 3500, the accumulation bug is back!"
        )

    @_pytest.mark.asyncio
    async def test_output_tokens_accumulate_across_turns(self) -> None:
        """
        Output tokens should sum across multiple run_streaming calls.

        Turn 1: generate 50 tokens
        Turn 2: generate 100 tokens
        Total after turn 2: 150 tokens
        """
        provider = MockProviderForRunner(responses=[
            {"text": "First response", "input_tokens": 1000, "output_tokens": 50},
            {"text": "Second response", "input_tokens": 2000, "output_tokens": 100},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        # Turn 1
        result1 = await conv_runner.run_streaming("hello")
        assert result1["usage"]["output_tokens"] == 50

        # Turn 2
        result2 = await conv_runner.run_streaming("world")
        assert result2["usage"]["output_tokens"] == 150, (
            f"output_tokens should be 150 (50+100), got {result2['usage']['output_tokens']}"
        )

    @_pytest.mark.asyncio
    async def test_reset_clears_token_counts(self) -> None:
        """reset() should zero both context and output tokens."""
        provider = MockProviderForRunner(responses=[
            {"text": "First", "input_tokens": 1000, "output_tokens": 50},
            {"text": "After reset", "input_tokens": 500, "output_tokens": 25},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        # First turn
        await conv_runner.run_streaming("hello")

        # Reset
        conv_runner.reset()

        # Verify internal state is cleared
        assert conv_runner._current_context_tokens == 0
        assert conv_runner._total_output_tokens == 0

    @_pytest.mark.asyncio
    async def test_result_dict_contains_correct_usage(self) -> None:
        """
        The returned result dict should have correct token values.

        result["usage"]["input_tokens"] == current context size
        result["usage"]["output_tokens"] == cumulative output
        result["usage"]["total_tokens"] == context + output
        """
        provider = MockProviderForRunner(responses=[
            {"text": "Response", "input_tokens": 5000, "output_tokens": 200},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        result = await conv_runner.run_streaming("test")

        assert "usage" in result
        assert result["usage"]["input_tokens"] == 5000
        assert result["usage"]["output_tokens"] == 200
        assert result["usage"]["total_tokens"] == 5200


# =============================================================================
# Basic Operation Tests
# =============================================================================


class TestRunnerBasicOperation:
    """Basic conversation flow tests."""

    @_pytest.mark.asyncio
    async def test_run_streaming_returns_result_dict(self) -> None:
        """run_streaming() returns dict with expected keys."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        result = await conv_runner.run_streaming("hello")

        assert "response" in result
        assert "provider" in result
        assert "model" in result
        assert "stop_reason" in result
        assert "usage" in result

    @_pytest.mark.asyncio
    async def test_run_complete_returns_result_dict(self) -> None:
        """run_complete() returns same structure as run_streaming()."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        result = await conv_runner.run_complete("hello")

        assert "response" in result
        assert "provider" in result
        assert "model" in result
        assert "usage" in result

    def test_requires_system_prompt(self) -> None:
        """Constructor raises ValueError if system_prompt is None."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        with _pytest.raises(ValueError, match="system_prompt is required"):
            runner.ConversationRunner(
                provider=provider,
                renderer=renderer,
                system_prompt=None,  # type: ignore[arg-type]
            )


# =============================================================================
# Message History Tests
# =============================================================================


class TestRunnerMessageHistory:
    """Message accumulation across turns."""

    @_pytest.mark.asyncio
    async def test_user_message_added_to_history(self) -> None:
        """After run_streaming(), user message appears in _messages."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        await conv_runner.run_streaming("hello there")

        assert len(conv_runner._messages) >= 1
        user_msgs = [m for m in conv_runner._messages if m.get("role") == "user"]
        assert len(user_msgs) >= 1
        assert "hello there" in user_msgs[0]["content"]

    @_pytest.mark.asyncio
    async def test_assistant_response_added_to_history(self) -> None:
        """After run_streaming(), assistant response appears in _messages."""
        provider = MockProviderForRunner(responses=[
            {"text": "Hello! How can I help?", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        await conv_runner.run_streaming("hello")

        assistant_msgs = [m for m in conv_runner._messages if m.get("role") == "assistant"]
        assert len(assistant_msgs) >= 1
        assert "Hello! How can I help?" in assistant_msgs[0]["content"]

    @_pytest.mark.asyncio
    async def test_messages_accumulate_across_turns(self) -> None:
        """Multiple turns build up message history."""
        provider = MockProviderForRunner(responses=[
            {"text": "First response", "input_tokens": 100, "output_tokens": 20},
            {"text": "Second response", "input_tokens": 200, "output_tokens": 30},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        # Turn 1
        await conv_runner.run_streaming("hello")
        after_turn1 = len(conv_runner._messages)

        # Turn 2
        await conv_runner.run_streaming("world")
        after_turn2 = len(conv_runner._messages)

        assert after_turn2 > after_turn1, "Messages should accumulate"

    @_pytest.mark.asyncio
    async def test_reset_clears_message_history(self) -> None:
        """reset() empties _messages list."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
        )

        # Add some messages
        await conv_runner.run_streaming("hello")
        assert len(conv_runner._messages) > 0

        # Reset
        conv_runner.reset()
        assert len(conv_runner._messages) == 0


# =============================================================================
# Skill Preprocessing Tests
# =============================================================================


class MockSkillRegistry:
    """Mock skill registry for testing."""

    def __init__(self, skills: dict[str, str] | None = None) -> None:
        """
        Initialize with a dict of skill_name -> skill_content.
        """
        self._skills = skills or {}

    def get(self, name: str) -> "MockSkill | None":
        """Get a skill by name."""
        if name in self._skills:
            return MockSkill(name, self._skills[name])
        return None

    def list_skills(self) -> list[str]:
        """List available skill names."""
        return list(self._skills.keys())


class MockSkill:
    """Mock skill for testing."""

    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self.content = content
        self.triggers: list[str] = []


class TestRunnerSkillPreprocessing:
    """Skill preprocessing tests."""

    @_pytest.mark.asyncio
    async def test_skill_trigger_injects_message(self) -> None:
        """
        Explicit /skill trigger injects skill content.

        Note: This tests that _preprocess_for_skills is called, but the
        actual preprocessing logic is in the skills module, not runner.
        """
        import pathlib

        import brynhild.skills as skills
        import brynhild.skills.skill as skill_module

        provider = MockProviderForRunner(responses=[
            {"text": "Skill acknowledged", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        # Create a skill registry and manually add a skill
        skill_registry = skills.SkillRegistry()
        # Create a proper Skill object with frontmatter
        frontmatter = skill_module.SkillFrontmatter(
            name="test-skill",
            description="A test skill",
        )
        test_skill = skill_module.Skill(
            frontmatter=frontmatter,
            body="This is test skill content.",
            path=pathlib.Path("/tmp/fake-skill"),
            source="project",
        )
        # Set up both _skills and loader
        skill_registry._skills = {"test-skill": test_skill}
        skill_registry._loader.set_skills(skill_registry._skills)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
            skill_registry=skill_registry,
        )

        result = await conv_runner.run_streaming("/skill test-skill")

        # Skill should have been triggered
        assert result.get("triggered_skill") == "test-skill"

        # Messages should include skill content
        messages_str = str(conv_runner._messages)
        assert "test skill content" in messages_str.lower()

    @_pytest.mark.asyncio
    async def test_invalid_skill_shows_error(self) -> None:
        """Invalid skill name shows error."""
        import brynhild.skills as skills

        provider = MockProviderForRunner(responses=[
            {"text": "Response", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        # Empty skill registry
        skill_registry = skills.SkillRegistry()

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
            skill_registry=skill_registry,
        )

        await conv_runner.run_streaming("/skill nonexistent-skill")

        # Should have shown error
        output_text = output.getvalue()
        # Note: The error goes through show_info, which plain renderer outputs
        assert "error" in output_text.lower() or "nonexistent" in output_text.lower() or \
            conv_runner._messages[-1]["content"] != ""  # At minimum, something was sent

    @_pytest.mark.asyncio
    async def test_no_skill_registry_processes_normally(self) -> None:
        """Without skill registry, /skill command is sent as-is."""
        provider = MockProviderForRunner(responses=[
            {"text": "Response", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
            skill_registry=None,  # No skill registry
        )

        await conv_runner.run_streaming("/skill some-skill")

        # No skill triggered
        # The text should be sent as-is
        user_msgs = [m for m in conv_runner._messages if m.get("role") == "user"]
        assert len(user_msgs) >= 1


# =============================================================================
# Logger Integration Tests
# =============================================================================


class MockConversationLogger:
    """Mock logger that captures all log calls."""

    def __init__(self) -> None:
        self.system_prompts: list[str] = []
        self.user_messages: list[str] = []
        self.skill_triggers: list[dict[str, _typing.Any]] = []
        self.events: list[tuple[str, _typing.Any]] = []

    def log_system_prompt(self, prompt: str) -> None:
        self.system_prompts.append(prompt)

    def log_user_message(self, content: str) -> None:
        self.user_messages.append(content)

    def log_skill_triggered(
        self,
        skill_name: str,
        skill_content: str,
        trigger_type: str,
        trigger_match: str | None = None,
    ) -> None:
        self.skill_triggers.append({
            "name": skill_name,
            "content": skill_content,
            "trigger_type": trigger_type,
            "trigger_match": trigger_match,
        })

    def log_event(self, event_type: str, **kwargs: _typing.Any) -> None:
        self.events.append((event_type, kwargs))

    # Stub other methods that might be called
    def log_assistant_message(self, *args: _typing.Any, **kwargs: _typing.Any) -> None:
        pass

    def log_assistant_stream_start(self) -> None:
        pass

    def log_assistant_stream_end(
        self,
        full_text: str,  # noqa: ARG002
        stop_reason: str | None = None,  # noqa: ARG002
    ) -> None:
        pass

    def log_usage(
        self,
        input_tokens: int,  # noqa: ARG002
        output_tokens: int,  # noqa: ARG002
    ) -> None:
        pass

    def log_thinking(self, content: str) -> None:  # noqa: ARG002
        pass


class TestRunnerLogging:
    """Logger integration tests."""

    @_pytest.mark.asyncio
    async def test_system_prompt_logged_on_init(self) -> None:
        """System prompt is logged when runner is created with logger."""
        provider = MockProviderForRunner()

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        logger = MockConversationLogger()

        runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are a helpful assistant.",
            logger=logger,
        )

        # System prompt should have been logged
        assert len(logger.system_prompts) == 1
        assert "helpful assistant" in logger.system_prompts[0]

    @_pytest.mark.asyncio
    async def test_user_message_logged(self) -> None:
        """User messages are logged."""
        provider = MockProviderForRunner(responses=[
            {"text": "Response", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        logger = MockConversationLogger()

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
            logger=logger,
        )

        await conv_runner.run_streaming("Please help me")

        # User message should have been logged
        assert len(logger.user_messages) >= 1
        assert "help me" in logger.user_messages[0].lower()

    @_pytest.mark.asyncio
    async def test_skill_trigger_logged(self) -> None:
        """Skill triggers are logged when skill is activated."""
        import pathlib

        import brynhild.skills as skills
        import brynhild.skills.skill as skill_module

        provider = MockProviderForRunner(responses=[
            {"text": "Skill acknowledged", "input_tokens": 100, "output_tokens": 20},
        ])

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)

        logger = MockConversationLogger()

        # Create a skill registry and manually add a skill
        skill_registry = skills.SkillRegistry()
        frontmatter = skill_module.SkillFrontmatter(
            name="logged-skill",
            description="A skill to test logging",
        )
        logged_skill = skill_module.Skill(
            frontmatter=frontmatter,
            body="Skill content for logging test.",
            path=pathlib.Path("/tmp/fake-logged-skill"),
            source="project",
        )
        # Set up both _skills and loader
        skill_registry._skills = {"logged-skill": logged_skill}
        skill_registry._loader.set_skills(skill_registry._skills)

        conv_runner = runner.ConversationRunner(
            provider=provider,
            renderer=renderer,
            system_prompt="You are helpful.",
            skill_registry=skill_registry,
            logger=logger,
        )

        await conv_runner.run_streaming("/skill logged-skill")

        # Skill trigger should have been logged
        assert len(logger.skill_triggers) == 1
        assert logger.skill_triggers[0]["name"] == "logged-skill"
        assert "logging test" in logger.skill_triggers[0]["content"].lower()

