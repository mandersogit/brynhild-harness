# Plugin Migration Notes

> **Version**: 0.2.0  
> **Date**: 2024-12-04

This document covers recent upstream changes that may affect plugin developers.

## Summary

All changes are **backwards-compatible** - existing plugins will continue to work. However, plugin authors may want to implement new optional interfaces for better integration.

---

## Provider Plugins

### New: Reasoning Format Support

Providers can now specify how reasoning/thinking content should be formatted when sent to the LLM.

**New optional property:**

```python
from brynhild.api.base import ReasoningFormat  # Literal["reasoning_field", "thinking_tags", "none"]

class Provider(LLMProvider):
    @property
    def default_reasoning_format(self) -> ReasoningFormat:
        """How to format reasoning content for this provider.
        
        - "reasoning_field": Use OpenRouter-style `reasoning` field on message
        - "thinking_tags": Wrap in <thinking></thinking> tags in content
        - "none": Don't include reasoning in API calls
        
        Default if not implemented: "none"
        """
        return "reasoning_field"  # or "thinking_tags" or "none"
```

**When to implement:**
- If your provider/model supports chain-of-thought reasoning
- If you want reasoning from previous turns to be included in follow-up calls

**User override:** Users can override the provider default via `BRYNHILD_REASONING_FORMAT` environment variable.

### New: Message Format - `reasoning` Field

When processing conversation history, assistant messages may now include a `reasoning` field:

```python
{
    "role": "assistant",
    "content": "Here's the answer...",
    "reasoning": "Let me think about this...",  # NEW - may be present
    "tool_calls": [...]
}
```

**Provider responsibility:** 
- If your provider supports reasoning, preserve this field when formatting messages for your API
- If your provider doesn't support it, the base class will handle stripping based on `default_reasoning_format`

---

## Tool Plugins

### New: Risk Level and Recovery Policy

Tools can now declare their risk level, which affects tool call recovery behavior:

```python
class Tool(ToolBase):
    @property
    def risk_level(self) -> str:
        """Risk level: "read_only", "mutating", or "high_impact".
        
        Default: "read_only"
        
        Used by the recovery system to determine how to handle tool calls
        that were recovered from model thinking (malformed responses).
        """
        return "read_only"
    
    @property
    def recovery_policy(self) -> str:
        """Recovery policy: "allow", "deny", or "confirm".
        
        Default: Based on risk_level
        - read_only → "allow"
        - mutating → "confirm" 
        - high_impact → "deny"
        
        Controls whether recovered tool calls can be auto-executed.
        """
        return "allow"
```

**When to implement:**
- Set `risk_level = "mutating"` for tools that modify state (files, databases, etc.)
- Set `risk_level = "high_impact"` for tools with irreversible effects (deployments, deletions)
- Override `recovery_policy` if you want different behavior than the default

### New: Input Validation

The base `Tool` class now provides input validation against your `input_schema`:

```python
# Available on all tools automatically:
validation = tool.validate_input(input_dict)

# validation.is_valid - bool
# validation.errors - list of error messages
# validation.unknown_parameters - list of unexpected params
# validation.missing_required_parameters - list of missing required params
```

**Plugin impact:** None required - this is handled by the framework. Your tools get automatic validation and the model receives feedback on invalid inputs.

---

## UI/Renderer Plugins

### New: Session Banner

Renderers can now implement a session info banner:

```python
def show_session_banner(
    self,
    *,
    model: str,
    provider: str,
    profile: str | None = None,
    session: str | None = None,
) -> None:
    """Display session info at conversation start."""
    # Optional - default is no-op
```

### New: Thinking Stream

Renderers can support streaming thinking content:

```python
def start_thinking_stream(self) -> None:
    """Start live display for thinking content."""
    ...

def update_thinking_stream(self, text: str) -> None:
    """Update thinking display with new content."""
    ...

def end_thinking_stream(self, *, persist: bool = False) -> None:
    """End thinking display. If persist=True, print final panel."""
    ...
```

### New: Token Tracking

Renderers can show running token counts:

```python
def update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
    """Update cumulative token counts for display."""
    ...
```

---

## No Changes Required For

- **Existing tools** - All new properties have sensible defaults
- **Existing providers** - New methods are optional with no-op defaults
- **Existing renderers** - New methods are optional

## Recommended Actions

1. **Provider plugins**: Consider implementing `default_reasoning_format` if your backend supports reasoning
2. **Tool plugins**: Consider setting appropriate `risk_level` for non-read-only tools
3. **All plugins**: Review your implementation against the updated [Plugin API Reference](plugin-api-reference.md)

## Questions?

Open an issue or contact the maintainers.

