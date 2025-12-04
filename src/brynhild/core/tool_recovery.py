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
import re as _re
import typing as _typing
import uuid as _uuid

import brynhild.api.types as api_types

if _typing.TYPE_CHECKING:
    import brynhild.tools.registry as tools_registry


# Search window for recovery (default 16k chars from end)
DEFAULT_SEARCH_WINDOW = 16384

# Intent phrases that suggest a tool call is intended
INTENT_PATTERNS = [
    _re.compile(r"I will (call|use|invoke)", _re.IGNORECASE),
    _re.compile(r"I'll (call|use|invoke)", _re.IGNORECASE),
    _re.compile(r"Let me (call|use|invoke)", _re.IGNORECASE),
    _re.compile(r"Now I (should|will|need to) (call|use)", _re.IGNORECASE),
    _re.compile(r"Using the .* tool", _re.IGNORECASE),
    _re.compile(r"Next.*(call|use)", _re.IGNORECASE),
    _re.compile(r"I('ll| will| should) search", _re.IGNORECASE),
]

# Anti-patterns that suggest JSON is example/descriptive, not intended for execution
ANTI_PATTERNS = [
    _re.compile(r"[Ee]xample:"),
    _re.compile(r"[Ff]or instance"),
    _re.compile(r"[Tt]he format is:"),
    _re.compile(r"might look like:"),
    _re.compile(r"would look like:"),
    _re.compile(r"looks like this:"),
    _re.compile(r"[Hh]ere's (an|the) example"),
]


def _has_intent_signal(text_before_json: str, window: int = 200) -> bool:
    """Check if text before JSON contains intent phrases.

    Args:
        text_before_json: Text that appears before the JSON
        window: Number of chars before JSON to search (default 200)

    Returns:
        True if intent phrase found, False otherwise
    """
    search_text = text_before_json[-window:] if len(text_before_json) > window else text_before_json
    return any(p.search(search_text) for p in INTENT_PATTERNS)


def _has_anti_pattern(text_before_json: str, window: int = 100) -> bool:
    """Check if text before JSON contains example/descriptive patterns.

    Args:
        text_before_json: Text that appears before the JSON
        window: Number of chars before JSON to search (default 100)

    Returns:
        True if anti-pattern found (suggesting JSON is not for execution)
    """
    search_text = text_before_json[-window:] if len(text_before_json) > window else text_before_json
    return any(p.search(search_text) for p in ANTI_PATTERNS)


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

    tool_risk_level: str = "read_only"
    """Risk level of the recovered tool."""

    requires_confirmation: bool = False
    """Whether this recovery requires user confirmation before execution."""

    has_intent_signal: bool = False
    """Whether intent phrases were found near the JSON."""

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
            "tool_risk_level": self.tool_risk_level,
            "requires_confirmation": self.requires_confirmation,
            "has_intent_signal": self.has_intent_signal,
        }


def try_recover_tool_call_from_thinking(
    thinking: str,
    tool_registry: "tools_registry.ToolRegistry",
    *,
    model_recovery_enabled: bool = True,
    search_window: int = DEFAULT_SEARCH_WINDOW,
) -> RecoveryResult | None:
    """
    Attempt to recover a tool call that was placed in thinking instead of being emitted.

    Uses a robust heuristic: finds all potential JSON objects near the end of the
    text and tries to match each one against registered tools until a match is found.

    Respects tool-level recovery policies:
    - "allow": Auto-recover and execute
    - "deny": Skip this tool, try other candidates
    - "confirm": Recover but mark requires_confirmation=True

    Skips JSON candidates that appear to be examples (preceded by "Example:", etc.)

    Args:
        thinking: The model's thinking/analysis text.
        tool_registry: Registry of available tools to match against.
        model_recovery_enabled: Whether the model profile allows recovery.
            If False, returns None immediately.
        search_window: Maximum characters to search from end of thinking text.
            Default is 16k. Set to 0 or negative to search full text.

    Returns:
        RecoveryResult with the ToolUse and diagnostic info, or None if no recovery.
    """
    if not model_recovery_enabled:
        return None

    if not thinking or not tool_registry:
        return None

    original_text_length = len(thinking)

    # Apply search window - only search last N characters
    window_offset = 0
    if search_window > 0 and len(thinking) > search_window:
        window_offset = len(thinking) - search_window
        thinking = thinking[-search_window:]

    candidates_tried = 0

    # Try each JSON candidate until one matches a tool
    for args, json_start, json_end in _extract_json_candidates(thinking):
        candidates_tried += 1

        # Get text before JSON for context checking
        text_before = thinking[:json_start] if json_start > 0 else ""

        # Skip JSON candidates that appear to be examples
        if text_before and _has_anti_pattern(text_before):
            continue

        # Try to match against known tools by schema
        tool_match = _match_args_to_tool_with_policy(args, tool_registry)

        # Also check if tool name is mentioned in context before the JSON
        if tool_match is None and json_start > 0:
            tool_match = _match_with_context_and_policy(text_before, args, tool_registry)

        if tool_match is not None:
            tool_use, risk_level, recovery_policy = tool_match

            # Check for intent signal
            has_intent = _has_intent_signal(text_before) if text_before else False

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

            # Adjust position to account for window offset
            actual_json_position = json_start + window_offset

            return RecoveryResult(
                tool_use=tool_use,
                recovery_type=recovery_type,
                json_position=actual_json_position,
                text_length=original_text_length,
                candidates_tried=candidates_tried,
                extracted_json=thinking[json_start : json_end + 1],
                context_before=context_before,
                context_after=context_after,
                tool_risk_level=risk_level,
                requires_confirmation=(recovery_policy == "confirm"),
                has_intent_signal=has_intent,
            )

    return None


# Type alias for tool match result: (ToolUse, risk_level, recovery_policy)
_ToolMatch = tuple[api_types.ToolUse, str, str]


MAX_JSON_CANDIDATES = 20
"""Maximum number of JSON candidates to try before giving up."""


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

    Limited to MAX_JSON_CANDIDATES (20) to prevent excessive CPU usage
    in pathological cases.

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
    candidates_yielded = 0

    # Try each } from end to start
    for close_pos in reversed(close_brace_positions):
        if candidates_yielded >= MAX_JSON_CANDIDATES:
            break

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
                    candidates_yielded += 1
                    yield (obj, open_pos, close_pos)
                    # Found valid JSON for this }, move to next }
                    break
            except _json.JSONDecodeError:
                continue


def _match_args_to_tool_with_policy(
    args: dict[str, _typing.Any],
    tool_registry: "tools_registry.ToolRegistry",
) -> _ToolMatch | None:
    """
    Try to match args to a tool based on required parameters, respecting recovery policy.

    We look for tools where:
    1. Args contain all required parameters from the tool's input schema
    2. Tool's recovery_policy is not "deny"
    """
    import brynhild.tools.base as tools_base

    # (tool, score) - tool object so we can access risk_level and recovery_policy
    candidates: list[tuple[tools_base.Tool, int]] = []

    for tool in tool_registry.list_tools():
        # Skip tools that deny recovery
        if tool.recovery_policy == "deny":
            continue

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

        candidates.append((tool, score))

    if not candidates:
        return None

    # Pick best match
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_tool = candidates[0][0]

    tool_use = api_types.ToolUse(
        id=f"recovered-{_uuid.uuid4().hex[:12]}",
        name=best_tool.name,
        input=args,
    )

    return (tool_use, best_tool.risk_level, best_tool.recovery_policy)


def _match_with_context_and_policy(
    text_before: str,
    args: dict[str, _typing.Any],
    tool_registry: "tools_registry.ToolRegistry",
) -> _ToolMatch | None:
    """
    Try to match args to a tool using context clues, respecting recovery policy.

    Looks for tool names mentioned in the text before the JSON.
    """
    # Get last ~500 chars before JSON
    context = text_before[-500:].lower()

    for tool in tool_registry.list_tools():
        # Skip tools that deny recovery
        if tool.recovery_policy == "deny":
            continue

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
                        tool_use = api_types.ToolUse(
                            id=f"recovered-{_uuid.uuid4().hex[:12]}",
                            name=tool.name,
                            input=args,
                        )
                        return (tool_use, tool.risk_level, tool.recovery_policy)

    return None


# Pattern to match [tool_call: ToolName(args)] format
# Examples:
#   [tool_call: Bash(command="pwd")]
#   [tool_call: Inspect(operation="cwd")]
#   [tool_call: Search(query="something", limit=5)]
TOOL_CALL_TAG_PATTERN = _re.compile(
    r'\[tool_call:\s*(\w+)\s*\(([^)]*)\)\s*\]',
    _re.IGNORECASE
)


def try_recover_tool_call_from_content(
    content: str,
    tool_registry: "tools_registry.ToolRegistry",
    *,
    model_recovery_enabled: bool = True,
) -> RecoveryResult | None:
    """
    Attempt to recover tool calls from content text in [tool_call: ...] format.

    Some providers translate Harmony format tool calls into text patterns like:
        [tool_call: Bash(command="pwd")]
        [tool_call: Search(query="test", limit=5)]

    This function parses these patterns and creates ToolUse objects.

    Args:
        content: The model's response content text.
        tool_registry: Registry of available tools to match against.
        model_recovery_enabled: Whether the model profile allows recovery.

    Returns:
        RecoveryResult with the ToolUse and diagnostic info, or None if no recovery.
    """
    if not model_recovery_enabled:
        return None

    if not content or not tool_registry:
        return None

    # Find all [tool_call: ...] patterns
    matches = list(TOOL_CALL_TAG_PATTERN.finditer(content))
    if not matches:
        return None

    candidates_tried = 0

    # Try each match (from last to first, preferring later tool calls)
    for match in reversed(matches):
        candidates_tried += 1
        tool_name = match.group(1)
        args_str = match.group(2)

        # Parse the arguments from Python-like syntax: key="value", key=5
        args = _parse_tool_call_args(args_str)
        if args is None:
            continue

        # Try to match against registered tools
        tool = tool_registry.get(tool_name)
        if tool is None:
            # Try case-insensitive match
            for t in tool_registry.list_tools():
                if t.name.lower() == tool_name.lower():
                    tool = t
                    break

        if tool is None:
            continue

        # Check recovery policy
        if tool.recovery_policy == "deny":
            continue

        tool_use = api_types.ToolUse(
            id=f"recovered-content-{_uuid.uuid4().hex[:12]}",
            name=tool.name,
            input=args,
        )

        # Extract context
        start_pos = match.start()
        end_pos = match.end()
        context_start = max(0, start_pos - 100)
        context_before = content[context_start:start_pos]
        context_after = content[end_pos:end_pos + 100]

        return RecoveryResult(
            tool_use=tool_use,
            recovery_type="content_tag",
            json_position=start_pos,
            text_length=len(content),
            candidates_tried=candidates_tried,
            extracted_json=match.group(0),
            context_before=context_before,
            context_after=context_after,
            tool_risk_level=tool.risk_level,
            requires_confirmation=(tool.recovery_policy == "confirm"),
            has_intent_signal=True,  # Tag format implies intent
        )

    return None


def _parse_tool_call_args(args_str: str) -> dict[str, _typing.Any] | None:
    """
    Parse Python-like argument syntax into a dict.

    Handles:
        command="pwd"
        query="test", limit=5
        operation="cwd", filter="all"

    Returns:
        Dict of parsed arguments, or None if parsing fails.
    """
    if not args_str.strip():
        return {}

    args: dict[str, _typing.Any] = {}

    # Pattern for key=value pairs
    # Handles: key="string", key=123, key=true/false
    arg_pattern = _re.compile(
        r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\d+(?:\.\d+)?|true|false)',
        _re.IGNORECASE
    )

    for match in arg_pattern.finditer(args_str):
        key = match.group(1)
        value_str = match.group(2)

        # Parse the value
        if value_str.startswith('"') and value_str.endswith('"'):
            # String with double quotes
            value = value_str[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        elif value_str.startswith("'") and value_str.endswith("'"):
            # String with single quotes
            value = value_str[1:-1].replace("\\'", "'").replace('\\\\', '\\')
        elif value_str.lower() == 'true':
            value = True
        elif value_str.lower() == 'false':
            value = False
        elif '.' in value_str:
            value = float(value_str)
        else:
            value = int(value_str)

        args[key] = value

    return args if args else None


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

