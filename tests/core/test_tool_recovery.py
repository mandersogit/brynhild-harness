"""
Tests for tool call recovery from thinking output.
"""

import typing as _typing
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api.types as api_types
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
        self, input_data: dict[str, _typing.Any]
    ) -> tools_base.ToolResult:
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
        thinking = '''I analyzed the search results and found information about norigami.
Now I should search for more specific information about the reduce functionality.

{
  "corpus_key": "memcomp-support-list-new",
  "query": "norigami reduce",
  "limit": 5
}'''

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
        thinking = '''Let me use semantic_search to find more information.

{
  "corpus_key": "test-corpus",
  "query": "test query"
}'''

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
        thinking = '''Here is some analysis.

{"corpus_key": "test", "query": "test"}

And here is more text after the JSON.'''

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
        thinking = '''Let me search.

{
  "corpus_key": "test",
  "query": "test"
  missing_comma: true
}'''

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_no_recovery_for_unmatched_tool(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when JSON doesn't match any registered tool."""
        thinking = '''Let me do something.

{
  "completely": "unrelated",
  "json": "object"
}'''

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_no_recovery_without_required_params(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Returns None when required parameters are missing."""
        thinking = '''Search for something.

{
  "limit": 5
}'''

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is None

    def test_handles_empty_thinking(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Handles empty or None thinking gracefully."""
        assert (
            tool_recovery.try_recover_tool_call_from_thinking(
                "", registry_with_search_tool
            )
            is None
        )
        assert (
            tool_recovery.try_recover_tool_call_from_thinking(
                None, registry_with_search_tool  # type: ignore
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
        thinking = '''Search for info.

{
  "corpus_key": "test-corpus",
  "query": "test query"
}'''

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_multiple_tools
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"

    def test_recovers_with_trailing_whitespace(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON even with trailing whitespace/newlines."""
        thinking = '''Search now.

{
  "corpus_key": "test",
  "query": "test"
}

'''

        result = tool_recovery.try_recover_tool_call_from_thinking(
            thinking, registry_with_search_tool
        )

        assert result is not None
        assert result.tool_use.name == "semantic_search"

    def test_recovers_without_double_newline(
        self, registry_with_search_tool: tools_registry.ToolRegistry
    ) -> None:
        """Recovers JSON even without double newline separator."""
        thinking = '''I should search for more info.
{"corpus_key": "test", "query": "norigami"}'''

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
        thinking = '''The config looks like {"other": "stuff"} but I need to search.
{"corpus_key": "test", "query": "final"}'''

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
        thinking = '''Let me search: {"corpus_key": "test", "query": "match"}
Some more analysis...
Final note: {"unrelated": true}'''

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
        thinking = '''First object: {"a": 1}
Second object: {"b": 2}
Third: {"c": 3}'''

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
        thinking = '''Valid: {"a": 1}
Invalid: {not json}
Also valid: {"b": 2}'''

        results = tool_recovery.extract_all_json_from_thinking(thinking)

        assert len(results) == 2
        assert {"a": 1} in results
        assert {"b": 2} in results

