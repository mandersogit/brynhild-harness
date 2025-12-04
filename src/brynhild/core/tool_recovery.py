"""
Tool call recovery from model thinking output.

Some models (notably gpt-oss-120b) sometimes place tool call JSON in their
thinking/analysis channel instead of properly emitting it as a tool_call.
This module detects and recovers these misplaced tool calls.

Pattern detected:
    <thinking>
    ...analysis...
    Let's search for X.

    {
      "query": "X",
      "limit": 5
    }
    </thinking>
    [no tool_calls emitted]

The recovery extracts the JSON and creates a ToolUse that can be executed.
"""

import dataclasses as _dataclasses
import json as _json
import typing as _typing
import uuid as _uuid

import brynhild.api.types as api_types

if _typing.TYPE_CHECKING:
    import brynhild.tools.registry as tools_registry


@_dataclasses.dataclass
class RecoveryResult:
    """Result of a successful tool call recovery.

    Contains the recovered ToolUse plus diagnostic information about
    what kind of recovery was needed. This helps identify model misbehavior
    patterns even when we successfully recover.
    """

    tool_use: api_types.ToolUse
    """The recovered ToolUse object."""

    recovery_type: str
    """Type of recovery performed:
    - 'trailing_json': JSON was at the very end of text
    - 'json_with_trailing_text': JSON followed by other text (punctuation, tags, etc.)
    - 'fallback_json': Earlier JSON matched after later candidates failed
    """

    json_position: int
    """Character position where the JSON started in the original text."""

    text_length: int
    """Total length of the thinking text."""

    candidates_tried: int
    """Number of JSON candidates tried before finding a match."""

    extracted_json: str
    """The raw JSON string that was extracted."""

    context_before: str
    """Up to 100 chars of text before the JSON (for debugging)."""

    context_after: str
    """Text after the JSON, if any (for debugging)."""

    def to_log_dict(self) -> dict[str, _typing.Any]:
        """Convert to a dict suitable for logging."""
        return {
            "tool_name": self.tool_use.name,
            "tool_id": self.tool_use.id,
            "recovery_type": self.recovery_type,
            "json_position": self.json_position,
            "text_length": self.text_length,
            "candidates_tried": self.candidates_tried,
            "extracted_json": self.extracted_json[:500],  # Truncate for logs
            "context_before": self.context_before,
            "context_after": self.context_after,
        }


def try_recover_tool_call_from_thinking(
    thinking: str,
    tool_registry: "tools_registry.ToolRegistry",
) -> RecoveryResult | None:
    """
    Attempt to recover a tool call that was placed in thinking instead of being emitted.

    Uses a robust heuristic: finds all potential JSON objects near the end of the
    text and tries to match each one against registered tools until a match is found.

    Args:
        thinking: The model's thinking/analysis text.
        tool_registry: Registry of available tools to match against.

    Returns:
        RecoveryResult with the ToolUse and diagnostic info, or None if no recovery.
    """
    if not thinking or not tool_registry:
        return None

    text_length = len(thinking)
    candidates_tried = 0

    # Try each JSON candidate until one matches a tool
    for args, json_start, json_end in _extract_json_candidates(thinking):
        candidates_tried += 1

        # Try to match against known tools by schema
        tool_use = _match_args_to_tool(args, tool_registry)

        # Also check if tool name is mentioned in context before the JSON
        if tool_use is None and json_start > 0:
            text_before = thinking[:json_start]
            tool_use = _match_with_context(text_before, args, tool_registry)

        if tool_use is not None:
            # Determine recovery type
            stripped = thinking.strip()
            if stripped.endswith("}") and json_end >= len(stripped) - 1:
                recovery_type = "trailing_json"
            elif candidates_tried > 1:
                recovery_type = "fallback_json"
            else:
                recovery_type = "json_with_trailing_text"

            # Extract context for debugging
            context_start = max(0, json_start - 100)
            context_before = thinking[context_start:json_start]
            context_after = thinking[json_end + 1 : json_end + 101]

            return RecoveryResult(
                tool_use=tool_use,
                recovery_type=recovery_type,
                json_position=json_start,
                text_length=text_length,
                candidates_tried=candidates_tried,
                extracted_json=thinking[json_start : json_end + 1],
                context_before=context_before,
                context_after=context_after,
            )

    return None


def _extract_json_candidates(
    text: str,
) -> _typing.Iterator[tuple[dict[str, _typing.Any], int, int]]:
    """
    Extract JSON object candidates from the end of text.

    Finds all "}" characters and for each one (from end to start), tries to
    find a matching "{" that forms valid JSON. This handles cases where:
    - Text has trailing punctuation/comments after JSON
    - Multiple JSON objects exist and we need to try several
    - JSON is followed by closing tags or other syntax

    Args:
        text: The text to search for JSON.

    Yields:
        Tuples of (parsed_dict, start_position, end_position) for each valid JSON found,
        ordered from end of text to start.
    """
    text = text.strip()

    # Find all } positions
    close_brace_positions = [i for i, c in enumerate(text) if c == "}"]
    if not close_brace_positions:
        return

    # Track which ranges we've already yielded to avoid duplicates
    yielded_ranges: set[tuple[int, int]] = set()

    # Try each } from end to start
    for close_pos in reversed(close_brace_positions):
        # Get text up to and including this }
        text_to_close = text[: close_pos + 1]

        # Find all { positions in this substring
        open_brace_positions = [i for i, c in enumerate(text_to_close) if c == "{"]

        # Try each { from closest to this } to furthest
        for open_pos in reversed(open_brace_positions):
            # Skip if we've already yielded this exact range
            if (open_pos, close_pos) in yielded_ranges:
                continue

            candidate = text_to_close[open_pos:]
            try:
                obj = _json.loads(candidate)
                if isinstance(obj, dict):
                    yielded_ranges.add((open_pos, close_pos))
                    yield (obj, open_pos, close_pos)
                    # Found valid JSON for this }, move to next }
                    break
            except _json.JSONDecodeError:
                continue


def _match_args_to_tool(
    args: dict[str, _typing.Any],
    tool_registry: "tools_registry.ToolRegistry",
) -> api_types.ToolUse | None:
    """
    Try to match args to a tool based on required parameters.

    We look for tools where the args contain all required parameters
    from the tool's input schema.
    """
    candidates: list[tuple[str, int]] = []  # (tool_name, match_score)

    for tool in tool_registry.list_tools():
        schema = tool.input_schema
        if not schema:
            continue

        required = set(schema.get("required", []))
        properties = set(schema.get("properties", {}).keys())
        arg_keys = set(args.keys())

        # Check if all required params are present
        if not required.issubset(arg_keys):
            continue

        # Check if args are subset of valid properties (allow extra for flexibility)
        valid_keys = arg_keys.intersection(properties)
        if not valid_keys:
            continue

        # Score: more matching properties = better match
        score = len(valid_keys)
        if required and required.issubset(arg_keys):
            score += 10  # Bonus for having all required

        candidates.append((tool.name, score))

    if not candidates:
        return None

    # Pick best match
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_tool_name = candidates[0][0]

    return api_types.ToolUse(
        id=f"recovered-{_uuid.uuid4().hex[:12]}",
        name=best_tool_name,
        input=args,
    )


def _match_with_context(
    text_before: str,
    args: dict[str, _typing.Any],
    tool_registry: "tools_registry.ToolRegistry",
) -> api_types.ToolUse | None:
    """
    Try to match args to a tool using context clues from surrounding text.

    Looks for tool names mentioned in the text before the JSON.
    """
    # Get last ~500 chars before JSON
    context = text_before[-500:].lower()

    for tool in tool_registry.list_tools():
        tool_name_lower = tool.name.lower()

        # Check if tool name appears in context
        # Allow for common variations: "semantic_search", "semantic search", "SemanticSearch"
        name_variants = [
            tool_name_lower,
            tool_name_lower.replace("_", " "),
            tool_name_lower.replace("_", ""),
        ]

        for variant in name_variants:
            if variant in context:
                # Found tool name in context - validate args minimally
                schema = tool.input_schema
                if schema:
                    properties = set(schema.get("properties", {}).keys())
                    if set(args.keys()).intersection(properties):
                        return api_types.ToolUse(
                            id=f"recovered-{_uuid.uuid4().hex[:12]}",
                            name=tool.name,
                            input=args,
                        )

    return None


def extract_all_json_from_thinking(thinking: str) -> list[dict[str, _typing.Any]]:
    """
    Extract all JSON objects from thinking text.

    This is a more aggressive extraction that finds any JSON objects,
    not just those at the end. Useful for debugging/analysis.

    Args:
        thinking: The model's thinking text.

    Returns:
        List of parsed JSON objects found in the text.
    """
    results: list[dict[str, _typing.Any]] = []
    used_ranges: list[tuple[int, int]] = []

    # Find all { positions
    brace_positions = [i for i, c in enumerate(thinking) if c == "{"]

    for start_pos in brace_positions:
        # Skip if this position is inside a range we've already extracted
        if any(start <= start_pos < end for start, end in used_ranges):
            continue

        # Try to find a matching } and parse as JSON
        # Start with shortest possible and expand
        depth = 0
        for end_pos in range(start_pos, len(thinking)):
            c = thinking[end_pos]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    # Found matching brace, try to parse
                    candidate = thinking[start_pos : end_pos + 1]
                    try:
                        obj = _json.loads(candidate)
                        if isinstance(obj, dict):
                            results.append(obj)
                            used_ranges.append((start_pos, end_pos + 1))
                    except _json.JSONDecodeError:
                        pass
                    break

    return results

