"""Tests for ToolUse serialization and subclassing."""

import dataclasses as _dataclasses
import json as _json
import typing as _typing

import brynhild.api.types as api_types
import brynhild.core.types as core_types


class TestToolUseToToolCallDict:
    """Tests for ToolUse.to_tool_call_dict() method."""

    def test_basic_serialization(self) -> None:
        """Base ToolUse serializes to OpenAI tool_call format."""
        tool_use = api_types.ToolUse(
            id="call_123",
            name="get_weather",
            input={"location": "San Francisco"},
        )

        result = tool_use.to_tool_call_dict()

        assert result["id"] == "call_123"
        assert result["type"] == "function"
        assert result["function"]["name"] == "get_weather"
        assert result["function"]["arguments"] == '{"location": "San Francisco"}'

    def test_empty_input(self) -> None:
        """ToolUse with empty input serializes correctly."""
        tool_use = api_types.ToolUse(
            id="call_456",
            name="no_args_tool",
            input={},
        )

        result = tool_use.to_tool_call_dict()

        assert result["function"]["arguments"] == "{}"

    def test_complex_input(self) -> None:
        """ToolUse with nested/complex input serializes as JSON."""
        tool_use = api_types.ToolUse(
            id="call_789",
            name="complex_tool",
            input={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "bool": True,
                "null": None,
            },
        )

        result = tool_use.to_tool_call_dict()

        # Parse the JSON to verify structure
        parsed = _json.loads(result["function"]["arguments"])
        assert parsed["nested"]["key"] == "value"
        assert parsed["list"] == [1, 2, 3]
        assert parsed["bool"] is True
        assert parsed["null"] is None


class TestToolUseSubclassing:
    """Tests for subclassing ToolUse with custom fields."""

    def test_subclass_can_add_fields(self) -> None:
        """Subclass can add custom fields."""

        @_dataclasses.dataclass
        class CustomToolUse(api_types.ToolUse):
            custom_field: str | None = None

        tool_use = CustomToolUse(
            id="call_1",
            name="tool",
            input={},
            custom_field="extra_data",
        )

        assert tool_use.custom_field == "extra_data"
        assert tool_use.id == "call_1"

    def test_subclass_can_override_to_tool_call_dict(self) -> None:
        """Subclass can override to_tool_call_dict to include custom fields."""

        @_dataclasses.dataclass
        class ExtendedToolUse(api_types.ToolUse):
            thought_signature: str | None = None

            def to_tool_call_dict(self) -> dict[str, _typing.Any]:
                d = super().to_tool_call_dict()
                if self.thought_signature:
                    d["thought_signature"] = self.thought_signature
                return d

        tool_use = ExtendedToolUse(
            id="call_gemini",
            name="get_data",
            input={"query": "test"},
            thought_signature="abc123xyz",
        )

        result = tool_use.to_tool_call_dict()

        # Base fields present
        assert result["id"] == "call_gemini"
        assert result["function"]["name"] == "get_data"
        # Custom field included
        assert result["thought_signature"] == "abc123xyz"

    def test_subclass_without_custom_field_omits_it(self) -> None:
        """Subclass with None value omits the field."""

        @_dataclasses.dataclass
        class ExtendedToolUse(api_types.ToolUse):
            optional_field: str | None = None

            def to_tool_call_dict(self) -> dict[str, _typing.Any]:
                d = super().to_tool_call_dict()
                if self.optional_field:
                    d["optional_field"] = self.optional_field
                return d

        tool_use = ExtendedToolUse(
            id="call_1",
            name="tool",
            input={},
            optional_field=None,  # Not set
        )

        result = tool_use.to_tool_call_dict()

        assert "optional_field" not in result


class TestFormatAssistantToolCallIntegration:
    """Tests for format_assistant_tool_call using to_tool_call_dict."""

    def test_delegates_to_to_tool_call_dict(self) -> None:
        """format_assistant_tool_call calls to_tool_call_dict on each ToolUse."""

        @_dataclasses.dataclass
        class TrackedToolUse(api_types.ToolUse):
            """ToolUse that tracks if to_tool_call_dict was called."""

            _was_called: bool = _dataclasses.field(default=False, repr=False)

            def to_tool_call_dict(self) -> dict[str, _typing.Any]:
                # Can't mutate frozen dataclass, so we use a class variable
                TrackedToolUse._call_count = getattr(TrackedToolUse, "_call_count", 0) + 1
                return super().to_tool_call_dict()

        TrackedToolUse._call_count = 0

        tool_uses = [
            TrackedToolUse(id="1", name="a", input={}),
            TrackedToolUse(id="2", name="b", input={}),
        ]

        core_types.format_assistant_tool_call(tool_uses, "content")

        assert TrackedToolUse._call_count == 2

    def test_subclass_fields_appear_in_formatted_message(self) -> None:
        """Custom fields from subclass appear in the formatted message."""

        @_dataclasses.dataclass
        class GeminiToolUse(api_types.ToolUse):
            thought_signature: str | None = None

            def to_tool_call_dict(self) -> dict[str, _typing.Any]:
                d = super().to_tool_call_dict()
                if self.thought_signature:
                    d["thought_signature"] = self.thought_signature
                return d

        tool_uses = [
            GeminiToolUse(
                id="call_1",
                name="weather",
                input={"loc": "SF"},
                thought_signature="sig_abc",
            ),
            GeminiToolUse(
                id="call_2",
                name="time",
                input={},
                thought_signature="sig_def",
            ),
        ]

        result = core_types.format_assistant_tool_call(tool_uses, "checking...")

        assert result["role"] == "assistant"
        assert result["content"] == "checking..."
        assert len(result["tool_calls"]) == 2

        # First tool call has its signature
        assert result["tool_calls"][0]["id"] == "call_1"
        assert result["tool_calls"][0]["thought_signature"] == "sig_abc"

        # Second tool call has its signature
        assert result["tool_calls"][1]["id"] == "call_2"
        assert result["tool_calls"][1]["thought_signature"] == "sig_def"

    def test_mixed_base_and_subclass_tool_uses(self) -> None:
        """Can mix base ToolUse and subclass in same call."""

        @_dataclasses.dataclass
        class ExtendedToolUse(api_types.ToolUse):
            extra: str = "default"

            def to_tool_call_dict(self) -> dict[str, _typing.Any]:
                d = super().to_tool_call_dict()
                d["extra"] = self.extra
                return d

        tool_uses: list[api_types.ToolUse] = [
            api_types.ToolUse(id="base_1", name="base_tool", input={}),
            ExtendedToolUse(id="ext_1", name="extended_tool", input={}, extra="custom"),
        ]

        result = core_types.format_assistant_tool_call(tool_uses, "")

        # Base ToolUse - no extra field
        assert "extra" not in result["tool_calls"][0]

        # Extended ToolUse - has extra field
        assert result["tool_calls"][1]["extra"] == "custom"
