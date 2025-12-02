# Plugin Tool Interface

This document describes the interface that plugin tools must implement to work with Brynhild.

## Overview

Plugin tools extend Brynhild's capabilities by providing new operations for the LLM to use. Tools are defined in Python modules within your plugin's `tools/` directory.

## Quick Start

Here's a minimal working plugin tool:

```python
"""Example plugin tool."""

from __future__ import annotations

import typing as _typing

# Import from brynhild when available, use stubs for standalone testing
try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    # Stubs for standalone testing - see "Testing" section below
    from dataclasses import dataclass

    @dataclass
    class ToolResult:
        success: bool
        output: str
        error: str | None = None

    class ToolBase:
        pass


class Tool(ToolBase):
    """Example tool demonstrating the required interface."""

    @property
    def name(self) -> str:
        return "example"

    @property
    def description(self) -> str:
        return "An example tool that demonstrates the interface"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "A message to process",
                }
            },
            "required": ["message"],
        }

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> ToolResult:
        message = input.get("message", "")
        if not message:
            return ToolResult(
                success=False,
                output="",
                error="message is required",
            )
        return ToolResult(
            success=True,
            output=f"Processed: {message}",
        )
```

## Required Interface

Your tool class **must** be named `Tool` and implement these members:

### Properties (Required)

#### `name` → `str`

The tool's identifier. This is used in API calls and must be unique.

```python
@property
def name(self) -> str:
    return "my_tool"
```

**Guidelines:**
- Use lowercase with underscores: `my_tool`, `calculate`, `fetch_data`
- Keep it short but descriptive
- Avoid conflicts with built-in tools: `Bash`, `Read`, `Write`, `Edit`, `Grep`, `Glob`, `Inspect`, `LearnSkill`

#### `description` → `str`

Human-readable description shown to the LLM. This helps the model understand when to use your tool.

```python
@property
def description(self) -> str:
    return "Performs mathematical calculations safely"
```

**Guidelines:**
- Be specific about what the tool does
- Mention any constraints or limitations
- Include examples of typical use cases if helpful

#### `input_schema` → `dict`

A property returning a JSON Schema describing the tool's input parameters.

```python
@property
def input_schema(self) -> dict[str, typing.Any]:
    return {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate",
            },
            "precision": {
                "type": "integer",
                "description": "Decimal places for result",
                "default": 2,
            },
        },
        "required": ["expression"],
    }
```

**Guidelines:**
- Always include `"type": "object"` at the top level
- Provide clear descriptions for each property
- Mark required fields in the `"required"` array
- Use standard JSON Schema types: `string`, `number`, `integer`, `boolean`, `array`, `object`

### Methods (Required)

#### `execute(input: dict) → ToolResult`

Executes the tool with the given input. This method is `async`.

```python
async def execute(
    self,
    input: dict[str, typing.Any],
) -> ToolResult:
    expression = input.get("expression", "")
    
    if not expression:
        return ToolResult(
            success=False,
            output="",
            error="expression is required",
        )
    
    try:
        result = evaluate(expression)  # Your logic here
        return ToolResult(
            success=True,
            output=f"Result: {result}",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Calculation failed: {e}",
        )
```

**Signature:**
- Takes a single `input` parameter (dictionary matching your schema)
- Returns a `ToolResult` object
- Must be `async` (use `async def`)

### Properties (Optional)

#### `requires_permission` → `bool`

Whether to prompt the user for permission before executing. Defaults to `True`.

```python
@property
def requires_permission(self) -> bool:
    return False  # Safe read-only tool
```

**Guidelines:**
- Return `True` (default) for tools that: modify files, execute commands, access network
- Return `False` for tools that: only read data, perform calculations, are provably safe

## The ToolResult Class

All tools return a `ToolResult` with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the operation succeeded |
| `output` | `str` | The tool's output (shown to the LLM) |
| `error` | `str \| None` | Error message if `success=False` |

**Examples:**

```python
# Success
ToolResult(success=True, output="File created: /path/to/file")

# Validation error
ToolResult(success=False, output="", error="Missing required field: path")

# Runtime error
ToolResult(success=False, output="", error="File not found: /nonexistent")
```

## Inherited Methods (Free)

When you inherit from `brynhild.tools.base.Tool`, you get these for free:

| Method | Description |
|--------|-------------|
| `to_api_format()` | Converts to Anthropic API format |
| `to_openai_format()` | Converts to OpenAI/OpenRouter format |
| `_require_input(input, key)` | Helper for required field validation |
| `__repr__()` | String representation |

**You don't need to implement these unless you have special requirements.**

## Plugin Declaration

Don't forget to declare your tool in `plugin.yaml`:

```yaml
name: my-plugin
version: 1.0.0
description: My awesome plugin

tools:
  - my_tool  # Filename without .py extension
```

The tool file should be at: `plugins/my-plugin/tools/my_tool.py`

## Testing

### Standalone Testing (Without Brynhild Installed)

Use the try/except import pattern at the top of your tool file:

```python
try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    # Stubs for standalone testing
    from dataclasses import dataclass

    @dataclass
    class ToolResult:
        success: bool
        output: str
        error: str | None = None

    class ToolBase:
        pass
```

Then write a simple test:

```python
# test_my_tool.py
import asyncio
from tools.my_tool import Tool

async def test():
    tool = Tool()
    result = await tool.execute({"message": "hello"})
    print(f"Success: {result.success}")
    print(f"Output: {result.output}")
    if result.error:
        print(f"Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(test())
```

Run it without Brynhild installed:

```bash
python test_my_tool.py
```

### Integration Testing (With Brynhild)

Once Brynhild is installed, your tool will inherit from the real base class and work with the full system.

## Common Mistakes

### ❌ Using class attributes instead of properties

```python
# WRONG
class Tool:
    name = "my_tool"  # This won't work!
```

```python
# CORRECT
class Tool:
    @property
    def name(self) -> str:
        return "my_tool"
```

### ❌ Using `input_schema` class attribute instead of property

```python
# WRONG
class Tool:
    input_schema = {"type": "object", ...}  # This won't work!
```

```python
# CORRECT
class Tool:
    @property
    def input_schema(self) -> dict:
        return {"type": "object", ...}
```

### ❌ Wrong `execute()` signature

```python
# WRONG - keyword arguments
async def execute(self, message: str, **kwargs) -> dict:
    ...
```

```python
# CORRECT - single input dict, returns ToolResult
async def execute(self, input: dict) -> ToolResult:
    message = input.get("message", "")
    ...
```

### ❌ Returning dict instead of ToolResult

```python
# WRONG
return {"success": True, "output": "Done"}
```

```python
# CORRECT
return ToolResult(success=True, output="Done")
```

## Complete Example

See `examples/plugins/calculator/` for a complete working plugin with:
- Proper interface implementation
- Error handling
- Standalone testing
- Documentation

## Reference

### File Structure

```
my-plugin/
├── plugin.yaml           # Plugin manifest
├── tools/
│   ├── __init__.py       # Can be empty
│   └── my_tool.py        # Tool implementation (class must be named Tool)
├── providers/            # Optional: LLM providers
├── commands/             # Optional: Slash commands
├── hooks.yaml            # Optional: Hook definitions
└── README.md             # Plugin documentation
```

### Built-in Tool Names (Avoid Conflicts)

These names are reserved for built-in tools:
- `Bash` - Execute shell commands
- `Read` - Read file contents
- `Write` - Write/create files
- `Edit` - Edit existing files
- `Grep` - Search file contents
- `Glob` - Find files by pattern
- `Inspect` - Inspect filesystem entries
- `LearnSkill` - Load and manage skills

### See Also

- [Plugin Development Guide](plugin-development-guide.md)
- [Tool Error Handling](tool-error-handling.md)
- [Tool Permissions](tool-permissions.md)
- [Tool Testing](tool-testing.md)

