"""
Tests for tool call recovery from thinking output.
"""

import typing as _typing

import pytest as _pytest

import brynhild.core.tool_recovery as tool_recovery
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry


class MockTool(tools_base.Tool):
    """Mock tool for testing."""

    def __init__(
        self,
        name: str,
        schema: dict[str, _typing.Any],
    ) -> None:
        self._name = name
        self._schema = schema

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool: {self._name}"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return self._schema

    @property
    def requires_permission(self) -> bool:
        return False

    async def execute(
        self,
        input: dict[str, _typing.Any],  # noqa: A002
    ) -> tools_base.ToolResult:
        _ = input  # unused in mock
        return tools_base.ToolResult(success=True, output="mock result", error=None)


@_pytest.fixture
def registry_with_search_tool() -> tools_registry.ToolRegistry:
    """Create a registry with a semantic_search tool."""
    registry = tools_registry.ToolRegistry()
    registry.register(
        MockTool(
            name="semantic_search",
            schema={
                "type": "object",
                "properties": {
                    "corpus_key": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "generate_summary": {"type": "boolean"},
                },
                "required": ["corpus_key", "query"],
            },
        )
    )
    return registry


@_pytest.fixture
def registry_with_bash_tool() -> tools_registry.ToolRegistry:
    """Create a registry with a Bash tool."""
    registry = tools_registry.ToolRegistry()
    registry.register(
        MockTool(
            name="Bash",
            schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "background": {"type": "boolean"},
                },
                "required": ["command"],
            },
        )
    )
    return registry


@_pytest.fixture
def registry_with_multiple_tools() -> tools_registry.ToolRegistry:
    """Create a registry with multiple tools."""
    registry = tools_registry.ToolRegistry()
    registry.register(
        MockTool(
            name="semantic_search",
            schema={
                "type": "object",
                "properties": {
                    "corpus_key": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["corpus_key", "query"],
            },
        )
    )
    registry.register(
        MockTool(
            name="read_file",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                },
                "required": ["path"],
            },
        )
    )
    return registry


class TestToolCallRecovery:
    """Tests for try_recover_tool_call_from_thinking."""

    def test_recovers_json_at_end_of_thinking(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers tool call JSON that appears after double newline at end of thinking."""
        thinking = """I analyzed the search results and found information about norigami.
Now I should search for more specific information about the reduce functionality.

{
  "corpus_key": "memcomp-support-list-new",
  "query": "norigami reduce",
  "limit": 5
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"
        assert result.tool_use.input["corpus_key"] == "memcomp-support-list-new"
        assert result.tool_use.input["query"] == "norigami reduce"
        assert result.tool_use.id.startswith("recovered-")
        # Check recovery metadata
        assert result.recovery_type == "trailing_json"
        assert result.candidates_tried == 1
        assert result.text_length == len(thinking)

    def test_recovers_with_tool_name_in_context(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers when tool name is mentioned near the JSON."""
        thinking = """Let me use semantic_search to find more information.

{
  "corpus_key": "test-corpus",
  "query": "test query"
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"
        # Context before should contain the tool name mention
        assert "semantic_search" in result.context_before

    def test_no_recovery_without_json(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when thinking has no JSON."""
        thinking = "I analyzed the results and here is my summary."

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_recovers_json_in_middle_of_text(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Now recovers JSON even when it's not at the very end."""
        thinking = """Here is some analysis.

{"corpus_key": "test", "query": "test"}

And here is more text after the JSON."""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        # With rfind("}"), we now find JSON even in the middle
        assert result is not None
        assert result.tool_use.name == "semantic_search"
        assert result.recovery_type == "json_with_trailing_text"
        assert result.context_after  # Should have trailing text

    def test_no_recovery_when_no_json_at_all(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when there's no JSON anywhere in the text."""
        thinking = "Just plain text with no JSON objects anywhere."

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_no_recovery_for_invalid_json(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when JSON is malformed."""
        thinking = """Let me search.

{
  "corpus_key": "test",
  "query": "test"
  missing_comma: true
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_no_recovery_for_unmatched_tool(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when JSON doesn't match any registered tool."""
        thinking = """Let me do something.

{
  "completely": "unrelated",
  "json": "object"
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_no_recovery_without_required_params(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when required parameters are missing."""
        thinking = """Search for something.

{
  "limit": 5
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_handles_empty_thinking(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Handles empty or None thinking gracefully."""
        assert (
            tool_recovery.try_recover_tool_call_from_thinking("", registry_with_search_tool) is None
        )
        assert (
            tool_recovery.try_recover_tool_call_from_thinking(
                None,
                registry_with_search_tool,  # type: ignore
            )
            is None
        )

    def test_handles_none_registry(self) -> None:
        """Handles None registry gracefully."""
        thinking = '{"query": "test"}'
        assert (
            tool_recovery.try_recover_tool_call_from_thinking(thinking, None)  # type: ignore
            is None
        )

    def test_picks_best_match_with_multiple_tools(
        self, registry_with_multiple_tools: tools_registry.ToolRegistry
    ) -> None:
        """Picks the tool that best matches the JSON parameters."""
        # This JSON matches semantic_search better (has corpus_key and query)
        thinking = """Search for info.

{
  "corpus_key": "test-corpus",
  "query": "test query"
}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_multiple_tools
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"

    def test_recovers_with_trailing_whitespace(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON even with trailing whitespace/newlines."""
        thinking = """Search now.

{
  "corpus_key": "test",
  "query": "test"
}

"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"

    def test_recovers_without_double_newline(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON even without double newline separator."""
        thinking = """I should search for more info.
{"corpus_key": "test", "query": "norigami"}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"
        assert result.tool_use.input["query"] == "norigami"

    def test_recovers_inline_json(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON that's inline at end of text."""
        thinking = 'Let me search: {"corpus_key": "test", "query": "inline"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.input["query"] == "inline"

    def test_finds_correct_json_with_multiple_braces(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Finds the correct JSON when text has multiple { characters."""
        thinking = """The config looks like {"other": "stuff"} but I need to search.
{"corpus_key": "test", "query": "final"}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        # Should get the last valid JSON that matches a tool
        assert result.tool_use.input["query"] == "final"

    def test_recovers_with_trailing_punctuation(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON followed by trailing punctuation."""
        thinking = 'I will search now: {"corpus_key": "test", "query": "punct"}.'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.input["query"] == "punct"
        assert result.recovery_type == "json_with_trailing_text"

    def test_recovers_with_trailing_comment(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON followed by a comment."""
        thinking = '{"corpus_key": "test", "query": "comment"} // this should work'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.input["query"] == "comment"
        assert "// this should work" in result.context_after

    def test_recovers_with_trailing_tag(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON followed by closing tags."""
        thinking = '{"corpus_key": "test", "query": "tag"}</analysis>'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.input["query"] == "tag"
        assert "</analysis>" in result.context_after

    def test_tries_multiple_json_until_tool_match(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """When last JSON doesn't match a tool, tries earlier JSON objects."""
        # Last JSON is {"unrelated": true} which doesn't match semantic_search
        # But earlier JSON does match
        thinking = """Let me search: {"corpus_key": "test", "query": "match"}
Some more analysis...
Final note: {"unrelated": true}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        # Should find the semantic_search-matching JSON, not the unrelated one
        assert result.tool_use.input["query"] == "match"
        assert result.recovery_type == "fallback_json"
        assert result.candidates_tried > 1


class TestExtractAllJson:
    """Tests for extract_all_json_from_thinking helper."""

    def test_extracts_multiple_json_objects(self) -> None:
        """Extracts all JSON objects from text."""
        thinking = """First object: {"a": 1}
Second object: {"b": 2}
Third: {"c": 3}"""

        results = tool_recovery.extract_all_json_from_thinking(thinking)

        assert len(results) == 3
        assert {"a": 1} in results
        assert {"b": 2} in results
        assert {"c": 3} in results

    def test_handles_no_json(self) -> None:
        """Returns empty list when no JSON found."""
        thinking = "Just plain text with no JSON."

        results = tool_recovery.extract_all_json_from_thinking(thinking)

        assert results == []

    def test_skips_invalid_json(self) -> None:
        """Skips malformed JSON while extracting valid ones."""
        thinking = """Valid: {"a": 1}
Invalid: {not json}
Also valid: {"b": 2}"""

        results = tool_recovery.extract_all_json_from_thinking(thinking)

        assert len(results) == 2
        assert {"a": 1} in results
        assert {"b": 2} in results


class TestModelRecoveryGating:
    """Tests for model-level recovery gating."""

    def test_disabled_when_model_recovery_false(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when model recovery is disabled."""
        thinking = '{"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking,
            registry_with_search_tool,
            model_recovery_enabled=False,
        )

        assert result is None

    def test_enabled_when_model_recovery_true(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns result when model recovery is enabled."""
        thinking = '{"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking,
            registry_with_search_tool,
            model_recovery_enabled=True,
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"


class TestToolRecoveryPolicy:
    """Tests for tool-level recovery policy."""

    def test_skips_tool_with_deny_policy(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Skips tools that have recovery_policy='deny'."""
        # Get the tool and override its recovery_policy
        tool = registry_with_search_tool.get("semantic_search")
        assert tool is not None

        # Create a new registry with a tool that denies recovery
        class DenyRecoveryTool(MockTool):
            @property
            def recovery_policy(self) -> str:
                return "deny"

        deny_registry = tools_registry.ToolRegistry()
        deny_registry.register(
            DenyRecoveryTool(
                name="semantic_search",
                schema={
                    "type": "object",
                    "properties": {
                        "corpus_key": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["corpus_key", "query"],
                },
            )
        )

        thinking = '{"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(thinking, deny_registry)

        # Should not recover because tool denies it
        assert result is None


class TestIntentDetection:
    """Tests for intent phrase detection."""

    def test_has_intent_signal_positive(self) -> None:
        """Detects intent phrases before JSON."""
        assert tool_recovery._has_intent_signal("I will call the search tool")
        assert tool_recovery._has_intent_signal("Let me use semantic_search")
        assert tool_recovery._has_intent_signal("Now I should call the API")
        assert tool_recovery._has_intent_signal("I'll search for more info")

    def test_has_intent_signal_negative(self) -> None:
        """Returns False when no intent phrases."""
        assert not tool_recovery._has_intent_signal("Here is some text")
        assert not tool_recovery._has_intent_signal("The results show")
        assert not tool_recovery._has_intent_signal("")


class TestAntiPatternDetection:
    """Tests for anti-pattern (example context) detection."""

    def test_has_anti_pattern_positive(self) -> None:
        """Detects example/descriptive patterns."""
        assert tool_recovery._has_anti_pattern("Example:")
        assert tool_recovery._has_anti_pattern("For instance, the format is:")
        assert tool_recovery._has_anti_pattern("The format is:")
        assert tool_recovery._has_anti_pattern("might look like:")

    def test_has_anti_pattern_negative(self) -> None:
        """Returns False when no anti-patterns."""
        assert not tool_recovery._has_anti_pattern("Let me call the tool")
        assert not tool_recovery._has_anti_pattern("I will search now")
        assert not tool_recovery._has_anti_pattern("")

    def test_skips_json_in_example_context(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Skips JSON that appears in example/descriptive context."""
        # The anti-pattern detection uses a 100-char window before the JSON
        # So we need enough padding between the example text and the "real" JSON
        padding = "x" * 150  # Enough to push anti-pattern out of window

        thinking = f"""The format is:
{{"corpus_key": "example", "query": "example"}}
{padding}
Now let me actually search:
{{"corpus_key": "real", "query": "real query"}}"""

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        # Should skip the "format is" example and find the real one
        assert result is not None
        assert result.tool_use.input["query"] == "real query"


class TestSearchWindowing:
    """Tests for search window functionality."""

    def test_respects_search_window(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Only searches within the specified window."""
        # Put JSON at start, outside a small window
        early_json = '{"corpus_key": "early", "query": "early"}'
        padding = "x" * 200  # Padding to push early JSON outside window
        late_json = '{"corpus_key": "late", "query": "late"}'

        thinking = early_json + padding + late_json

        # With small window, should find late JSON
        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking,
            registry_with_search_tool,
            search_window=250,  # Only includes late JSON
        )

        assert result is not None
        assert result.tool_use.input["query"] == "late"

    def test_full_text_when_window_zero(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Searches full text when window is 0 or negative."""
        early_json = '{"corpus_key": "early", "query": "early"}'
        padding = "x" * 100
        late_json = '{"corpus_key": "late", "query": "late"}'

        thinking = early_json + padding + late_json

        # With window=0, searches full text, finds late JSON first (end to start)
        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking,
            registry_with_search_tool,
            search_window=0,
        )

        assert result is not None
        # Should still find from end (late JSON first)
        assert result.tool_use.input["query"] == "late"


class TestRecoveryResultFields:
    """Tests for new RecoveryResult fields."""

    def test_has_intent_signal_field(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """RecoveryResult includes has_intent_signal field."""
        thinking = 'I will call search: {"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.has_intent_signal is True

    def test_no_intent_signal_field(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """has_intent_signal is False when no intent phrases."""
        thinking = '{"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.has_intent_signal is False

    def test_tool_risk_level_field(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """RecoveryResult includes tool_risk_level field."""
        thinking = '{"corpus_key": "test", "query": "test"}'

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_risk_level == "read_only"  # Default for MockTool


class TestContentTagRecovery:
    """Tests for [tool_call: ToolName(args)] format recovery from content."""

    def test_recovers_tool_call_tag(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers tool call from [tool_call: Bash(command="pwd")]."""
        content = 'Let me check the current directory.\n\n[tool_call: Bash(command="pwd")]'

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is not None
        assert result.tool_use.name == "Bash"
        assert result.tool_use.input == {"command": "pwd"}
        assert result.recovery_type == "content_tag"
        assert result.has_intent_signal is True

    def test_recovers_with_multiple_args(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers tool call with multiple arguments."""
        content = (
            '[tool_call: semantic_search(corpus_key="test", query="find something", limit=10)]'
        )

        result = tool_recovery.try_recover_tool_call_from_content(
            content, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"
        assert result.tool_use.input["query"] == "find something"
        assert result.tool_use.input["limit"] == 10

    def test_case_insensitive_tool_name(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """Matches tool names case-insensitively."""
        content = '[tool_call: bash(command="ls")]'

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is not None
        assert result.tool_use.name == "Bash"

    def test_recovers_boolean_args(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """Parses boolean argument values."""
        content = '[tool_call: Bash(command="echo test", background=true)]'

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is not None
        assert result.tool_use.input["command"] == "echo test"
        assert result.tool_use.input["background"] is True

    def test_recovers_numeric_args(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Parses numeric argument values."""
        content = '[tool_call: semantic_search(corpus_key="test", query="q", limit=5)]'

        result = tool_recovery.try_recover_tool_call_from_content(
            content, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.input["limit"] == 5

    def test_no_match_for_unknown_tool(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """No recovery for unknown tool names."""
        content = '[tool_call: UnknownTool(arg="value")]'

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is None

    def test_no_match_for_plain_text(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """No recovery for content without tool_call tags."""
        content = "Just some text about using tools"

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is None

    def test_recovers_last_tool_call_when_multiple(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers the last tool call tag when multiple are present."""
        content = """[tool_call: Bash(command="first")]
More text here
[tool_call: Bash(command="second")]"""

        result = tool_recovery.try_recover_tool_call_from_content(content, registry_with_bash_tool)

        assert result is not None
        assert result.tool_use.input["command"] == "second"

    def test_disabled_when_model_recovery_false(
        self, registry_with_bash_tool: tools_registry.ToolRegistry
    ) -> None:
        """No recovery when model_recovery_enabled=False."""
        content = '[tool_call: Bash(command="pwd")]'

        result = tool_recovery.try_recover_tool_call_from_content(
            content, registry_with_bash_tool, model_recovery_enabled=False
        )

        assert result is None

    def test_respects_deny_recovery_policy(self) -> None:
        """Skips tool with deny recovery policy."""

        class DenyRecoveryTool(MockTool):
            @property
            def recovery_policy(self) -> str:
                return "deny"

        registry = tools_registry.ToolRegistry()
        registry.register(
            DenyRecoveryTool(
                name="Bash",
                schema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            )
        )

        content = '[tool_call: Bash(command="pwd")]'

        result = tool_recovery.try_recover_tool_call_from_content(content, registry)

        assert result is None
