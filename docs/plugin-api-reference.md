# Plugin API Reference

> **Version**: 0.1.0  
> **Last Updated**: 2024-12-03

This document provides the complete API reference for plugin authors extending Brynhild. For a tutorial-style guide, see [Plugin Development Guide](plugin-development-guide.md).

## Table of Contents

1. [Extension Points Overview](#extension-points-overview)
2. [Tools API](#tools-api)
3. [Providers API](#providers-api)
4. [Hooks API](#hooks-api)
5. [Commands API](#commands-api)
6. [Skills API](#skills-api)
7. [Plugin Lifecycle](#plugin-lifecycle)
8. [Stubs for Standalone Testing](#stubs-for-standalone-testing)

---

## Extension Points Overview

Plugins can extend Brynhild through five extension points:

| Extension | Files Location      | Interface                | Loading              |
|-----------|---------------------|--------------------------|----------------------|
| Tools     | `tools/*.py`        | `Tool` class             | Dynamic import       |
| Providers | `providers/*.py`    | `LLMProvider` class      | Dynamic import       |
| Hooks     | `hooks.yaml`        | YAML config              | Config merge         |
| Commands  | `commands/*.md`     | Markdown with frontmatter | Template loading    |
| Skills    | `skills/*/SKILL.md` | Markdown with frontmatter | Metadata + body     |

---

## Tools API

### Required Interface

Your tool must be a class named `Tool` (exactly) with these members:

```python
class Tool:
    @property
    def name(self) -> str:
        """Unique tool identifier (e.g., "MyTool")."""
        ...

    @property
    def description(self) -> str:
        """Description for the LLM. Include when/why to use this tool."""
        ...

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema defining accepted inputs."""
        ...

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        """Execute the tool with validated input."""
        ...
```

### ToolResult

```python
@dataclass
class ToolResult:
    success: bool           # Whether operation succeeded
    output: str             # Output text (shown to LLM)
    error: str | None = None  # Error message if success=False
```

**Usage:**

```python
# Success
return ToolResult(success=True, output="Operation completed: 42")

# Failure
return ToolResult(success=False, output="", error="File not found: foo.txt")
```

### Optional Properties

Override these for richer tool metadata:

```python
@property
def requires_permission(self) -> bool:
    """If True, user must approve before execution. Default: True."""
    return True  # Safe read-only tools can return False

@property
def version(self) -> str:
    """Tool version string. Default: "0.0.0"."""
    return "1.0.0"

@property
def categories(self) -> list[str]:
    """Category tags for organization. Default: []."""
    return ["network", "api"]

@property
def examples(self) -> list[dict[str, Any]]:
    """Usage examples for the LLM. Default: []."""
    return [
        {
            "description": "Fetch user profile",
            "input": {"user_id": "123"},
        }
    ]

@property
def risk_level(self) -> str:
    """Risk classification for recovery decisions. Default: "read_only".
    
    Values:
    - "read_only": Safe, no side effects (default)
    - "mutating": Modifies state (files, databases)
    - "high_impact": Irreversible effects (deployments, deletions)
    """
    return "read_only"

@property
def recovery_policy(self) -> str:
    """How to handle recovered tool calls. Default: based on risk_level.
    
    Values:
    - "allow": Auto-execute recovered calls
    - "confirm": Require user confirmation
    - "deny": Never execute recovered calls
    
    Defaults by risk_level:
    - read_only → "allow"
    - mutating → "confirm"
    - high_impact → "deny"
    """
    return "allow"  # Override based on your tool's risk
```

### Input Schema Format

The `input_schema` must be a valid JSON Schema:

```python
@property
def input_schema(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method",
                "default": "GET",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
        },
        "required": ["url"],
    }
```

### Complete Tool Example

```python
# tools/http_client.py
from __future__ import annotations
import typing as _typing

# Import with fallback for standalone testing
try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    from brynhild.plugins.stubs import ToolResult, ToolBase


class Tool(ToolBase):
    """HTTP client tool for making web requests."""

    @property
    def name(self) -> str:
        return "HttpClient"

    @property
    def description(self) -> str:
        return """Make HTTP requests to APIs and web servers.
        
Use this tool when you need to:
- Fetch data from a REST API
- Check if a URL is accessible
- Download content from the web"""

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to request",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers",
                },
                "body": {
                    "type": "string",
                    "description": "Request body (for POST/PUT)",
                },
            },
            "required": ["url"],
        }

    @property
    def requires_permission(self) -> bool:
        return True  # Network access requires approval

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def categories(self) -> list[str]:
        return ["network", "api"]

    async def execute(self, input: dict[str, _typing.Any]) -> ToolResult:
        import httpx as _httpx

        url = input.get("url")
        if not url:
            return ToolResult(success=False, output="", error="URL is required")

        method = input.get("method", "GET")
        headers = input.get("headers", {})
        body = input.get("body")

        try:
            async with _httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                    timeout=30.0,
                )
                
                return ToolResult(
                    success=True,
                    output=f"Status: {response.status_code}\n\n{response.text[:2000]}",
                )
        except _httpx.TimeoutException:
            return ToolResult(success=False, output="", error="Request timed out")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
```

---

## Providers API

### Required Interface

Your provider must implement the `LLMProvider` abstract base class:

```python
class Provider(LLMProvider):
    PROVIDER_NAME = "my-provider"  # Optional: explicit name

    @property
    def name(self) -> str:
        """Provider identifier (e.g., "openrouter", "ollama")."""
        ...

    @property
    def model(self) -> str:
        """Current model being used."""
        ...

    def supports_tools(self) -> bool:
        """Whether this provider/model supports tool calling."""
        ...

    @property
    def default_reasoning_format(self) -> str:
        """How reasoning should be formatted. Optional.
        
        Values:
        - "reasoning_field": Use `reasoning` field on message (OpenRouter style)
        - "thinking_tags": Wrap in <thinking></thinking> tags
        - "none": Don't include reasoning
        
        Default: "none"
        """
        return "none"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[Tool] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> CompletionResponse:
        """Non-streaming completion."""
        ...

    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[Tool] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming completion (async generator)."""
        ...
```

### Message Format

Messages follow this structure:

```python
# User message
{"role": "user", "content": "Hello!"}

# Assistant message (text only)
{"role": "assistant", "content": "Hi there!"}

# Assistant message with reasoning (chain-of-thought)
{
    "role": "assistant",
    "content": "The answer is 42.",
    "reasoning": "Let me think step by step..."  # Optional - present if model has CoT
}

# Assistant message with tool use
{
    "role": "assistant",
    "content": [
        {"type": "text", "text": "Let me check that file."},
        {
            "type": "tool_use",
            "id": "call_123",
            "name": "Read",
            "input": {"path": "foo.txt"},
        },
    ],
}

# Tool result (as user message)
{
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": "call_123",
            "content": "File contents here...",
        },
    ],
}
```

### Return Types

**CompletionResponse:**

```python
@dataclass
class CompletionResponse:
    id: str                         # Unique response ID
    content: str                    # Response text
    stop_reason: str | None         # "end_turn", "tool_use", "max_tokens"
    usage: Usage                    # Token counts
    tool_uses: list[ToolUse] = []   # Tool calls requested
    thinking: str | None = None     # Reasoning trace (if supported)
```

**StreamEvent:**

```python
@dataclass
class StreamEvent:
    type: Literal[
        "message_start",    # Stream beginning
        "content_start",    # Content block starting
        "text_delta",       # Text chunk
        "thinking_delta",   # Reasoning chunk
        "tool_use_start",   # Tool call starting
        "tool_use_delta",   # Tool input chunk
        "content_stop",     # Content block complete
        "message_delta",    # Message metadata update
        "message_stop",     # Stream complete
        "error",            # Error occurred
    ]
    text: str | None = None
    thinking: str | None = None
    tool_use: ToolUse | None = None
    tool_input_delta: str | None = None
    usage: Usage | None = None
    error: str | None = None
    stop_reason: str | None = None
```

**Usage:**

```python
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
```

**ToolUse:**

```python
@dataclass
class ToolUse:
    id: str                   # Unique call ID
    name: str                 # Tool name
    input: dict[str, Any]     # Tool arguments
```

### Complete Provider Example

```python
# providers/my_provider.py
from __future__ import annotations
import typing as _typing

try:
    import brynhild.api.base as _base
    import brynhild.api.types as _types
    LLMProvider = _base.LLMProvider
    CompletionResponse = _types.CompletionResponse
    StreamEvent = _types.StreamEvent
    Usage = _types.Usage
    ToolUse = _types.ToolUse
except ImportError:
    # Stub for standalone testing
    class LLMProvider:
        pass
    from dataclasses import dataclass
    @dataclass
    class CompletionResponse:
        id: str
        content: str
        stop_reason: str | None
        usage: _typing.Any
        tool_uses: list = None
    @dataclass
    class StreamEvent:
        type: str
        text: str | None = None
    @dataclass
    class Usage:
        input_tokens: int = 0
        output_tokens: int = 0
    @dataclass
    class ToolUse:
        id: str
        name: str
        input: dict


class Provider(LLMProvider):
    """Custom LLM provider implementation."""

    PROVIDER_NAME = "my-provider"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "default-model",
        base_url: str = "https://api.example.com",
        **kwargs: _typing.Any,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "my-provider"

    @property
    def model(self) -> str:
        return self._model

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[_typing.Any] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> CompletionResponse:
        import httpx as _httpx

        # Apply profile if set
        if use_profile and hasattr(self, "_profile") and self._profile:
            system = self.apply_profile_to_system(system)
            max_tokens = self.apply_profile_to_max_tokens(max_tokens)

        # Build request
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]

        # Make request
        async with _httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/v1/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        return CompletionResponse(
            id=data.get("id", ""),
            content=data.get("content", ""),
            stop_reason=data.get("stop_reason"),
            usage=Usage(
                input_tokens=data.get("usage", {}).get("input_tokens", 0),
                output_tokens=data.get("usage", {}).get("output_tokens", 0),
            ),
            tool_uses=[
                ToolUse(id=t["id"], name=t["name"], input=t["input"])
                for t in data.get("tool_uses", [])
            ],
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[_typing.Any] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[StreamEvent]:
        # Implement streaming logic
        # Yield StreamEvent objects as data arrives
        yield StreamEvent(type="message_start")
        yield StreamEvent(type="text_delta", text="Hello from my provider!")
        yield StreamEvent(type="message_stop", stop_reason="end_turn")
```

---

## Hooks API

### Configuration Format

Hooks are defined in `hooks.yaml`:

```yaml
version: 1

hooks:
  # Section name is the event type
  pre_tool_use:
    - name: my-hook          # Unique identifier
      type: command          # command, script, or prompt
      command: "echo $BRYNHILD_TOOL_NAME"
      match:                 # Optional: filter conditions
        tool: "Bash"
      enabled: true          # Default: true
      timeout:
        seconds: 30
        on_timeout: block    # block or continue

  post_tool_use:
    - name: log-results
      type: script
      script: "./scripts/log_tool.py"

  plugin_init:
    - name: setup
      type: command
      command: "./scripts/init.sh"
```

### Hook Events

| Event                | Fires When                | Can Block | Can Modify          |
|----------------------|---------------------------|-----------|---------------------|
| `plugin_init`        | Plugin loads              | No        | No                  |
| `plugin_shutdown`    | Brynhild exits            | No        | No                  |
| `session_start`      | Session begins            | No        | No                  |
| `session_end`        | Session ends              | No        | No                  |
| `pre_tool_use`       | Before tool execution     | Yes       | `input`             |
| `post_tool_use`      | After tool execution      | No        | `output`            |
| `pre_message`        | Before sending to LLM     | Yes       | `message`           |
| `post_message`       | After LLM response        | No        | `response`          |
| `user_prompt_submit` | User submits input        | Yes       | `message`           |
| `pre_compact`        | Before context compaction | No        | `strategy`          |
| `error`              | Error occurs              | No        | No                  |

### Hook Types

#### Command Hooks

Shell commands with environment variables:

```yaml
hooks:
  pre_tool_use:
    - name: log-tool
      type: command
      command: |
        echo "Tool: $BRYNHILD_TOOL_NAME"
        echo "Input: $BRYNHILD_TOOL_INPUT"
```

**Available Environment Variables:**

| Variable                  | Events           | Description              |
|---------------------------|------------------|--------------------------|
| `BRYNHILD_EVENT`          | All              | Event name               |
| `BRYNHILD_SESSION_ID`     | All              | Session identifier       |
| `BRYNHILD_CWD`            | All              | Working directory        |
| `BRYNHILD_PLUGIN_NAME`    | Plugin events    | Plugin name              |
| `BRYNHILD_PLUGIN_PATH`    | Plugin events    | Plugin directory         |
| `BRYNHILD_TOOL_NAME`      | Tool events      | Tool being used          |
| `BRYNHILD_TOOL_INPUT`     | `pre_tool_use`   | Tool input as JSON       |
| `BRYNHILD_TOOL_OUTPUT`    | `post_tool_use`  | Tool output              |
| `BRYNHILD_TOOL_SUCCESS`   | `post_tool_use`  | "true" or "false"        |
| `BRYNHILD_MESSAGE`        | Message events   | User message             |
| `BRYNHILD_RESPONSE`       | `post_message`   | LLM response             |
| `BRYNHILD_ERROR`          | `error`          | Error message            |
| `BRYNHILD_ERROR_TYPE`     | `error`          | Exception type           |

**Exit Codes:**

| Exit Code | Action   | Description            |
|-----------|----------|------------------------|
| 0         | Continue | Proceed normally       |
| 1         | Block    | Stop with error        |
| 2         | Skip     | Skip silently          |

#### Script Hooks

Python scripts receive JSON on stdin and output JSON on stdout:

```yaml
hooks:
  pre_tool_use:
    - name: validate
      type: script
      script: "./scripts/validate.py"
```

**Input (stdin):**

```json
{
  "event": "pre_tool_use",
  "session_id": "abc123",
  "cwd": "/path/to/project",
  "tool": "Bash",
  "tool_input": {
    "command": "rm -rf /tmp/test"
  }
}
```

**Output (stdout) - HookResult:**

```json
{
  "action": "continue",
  "modified_input": null,
  "modified_output": null,
  "modified_message": null,
  "modified_response": null,
  "message": null,
  "inject_system_message": null
}
```

**Complete Script Example:**

```python
#!/usr/bin/env python3
# scripts/validate.py
import json
import sys

def main():
    # Read context from stdin
    context = json.load(sys.stdin)

    tool = context.get("tool")
    tool_input = context.get("tool_input", {})

    # Example: Block dangerous commands
    if tool == "Bash":
        command = tool_input.get("command", "")
        if "rm -rf /" in command:
            result = {
                "action": "block",
                "message": "Dangerous command blocked: recursive delete of root",
            }
            json.dump(result, sys.stdout)
            return

    # Example: Modify input
    if tool == "Bash" and not tool_input.get("timeout"):
        result = {
            "action": "continue",
            "modified_input": {**tool_input, "timeout": 30},
        }
        json.dump(result, sys.stdout)
        return

    # Example: Inject guidance
    if tool == "Write":
        result = {
            "action": "continue",
            "inject_system_message": "Remember to use consistent indentation.",
        }
        json.dump(result, sys.stdout)
        return

    # Default: continue unchanged
    json.dump({"action": "continue"}, sys.stdout)

if __name__ == "__main__":
    main()
```

**HookResult Fields:**

| Field                   | Type           | Events                     | Description                |
|-------------------------|----------------|----------------------------|----------------------------|
| `action`                | `str`          | All                        | "continue", "block", "skip"|
| `message`               | `str \| null`  | When blocking              | Message to show user       |
| `modified_input`        | `dict \| null` | `pre_tool_use`             | Modified tool input        |
| `modified_output`       | `str \| null`  | `post_tool_use`            | Modified tool output       |
| `modified_message`      | `str \| null`  | `pre_message`, `user_prompt_submit` | Modified message |
| `modified_response`     | `str \| null`  | `post_message`             | Modified response          |
| `inject_system_message` | `str \| null`  | Any                        | Inject into context        |

#### Prompt Hooks

LLM-based hooks use another model to make decisions:

```yaml
hooks:
  pre_message:
    - name: classify-intent
      type: prompt
      prompt: |
        Classify this user message:
        {{message}}
        
        Categories: question, command, clarification, other
      model: "openai/gpt-4o-mini"  # Optional, uses default
```

### Match Patterns

Filter when hooks run:

```yaml
hooks:
  pre_tool_use:
    - name: bash-only
      type: command
      command: "echo 'Bash tool called'"
      match:
        tool: "Bash"

    - name: dangerous-commands
      type: script
      script: "./scripts/check_dangerous.py"
      match:
        tool: "Bash"
        tool_input:
          command: "*rm*"  # Glob pattern
```

**Match Fields by Event:**

| Event           | Available Fields                              |
|-----------------|-----------------------------------------------|
| `pre_tool_use`  | `tool`, `tool_input.*`                        |
| `post_tool_use` | `tool`, `tool_input.*`, `tool_result.*`       |
| `pre_message`   | `message`                                     |
| `post_message`  | `message`, `response`                         |
| Plugin events   | `plugin_name`, `plugin_path`                  |

---

## Commands API

### Format

Commands are Markdown files with YAML frontmatter:

```markdown
---
name: deploy
description: Deploy the project to production
aliases:
  - d
  - ship
args: "[environment]"
---

# Deploy Command

Deploy your project to the specified environment.

## Current Configuration

- Project: {{cwd}}
- Environment: {{args}}
- User: {{env.USER}}

## Instructions

1. Run the build process
2. Upload artifacts to {{args}} environment
3. Verify deployment
```

### Frontmatter Fields

| Field         | Type         | Required | Description                    |
|---------------|--------------|----------|--------------------------------|
| `name`        | `str`        | Yes      | Command name (after `/`)       |
| `description` | `str`        | No       | Help text                      |
| `aliases`     | `list[str]`  | No       | Alternative names              |
| `args`        | `str`        | No       | Argument specification         |

### Template Variables

| Variable       | Description                     |
|----------------|---------------------------------|
| `{{args}}`     | User-provided arguments         |
| `{{cwd}}`      | Current working directory       |
| `{{env.VAR}}`  | Environment variable VAR        |

### Command Dataclass

```python
@dataclass
class Command:
    frontmatter: CommandFrontmatter
    body: str                   # Template text
    path: Path                  # Source file
    plugin_name: str = ""

    @property
    def name(self) -> str
    @property
    def description(self) -> str
    @property
    def aliases(self) -> list[str]

    def render(self, args: str = "", **context: Any) -> str
        """Render template with variable substitution."""
```

---

## Skills API

### Format

Skills are Markdown files in `skills/<name>/SKILL.md`:

```markdown
---
name: api-design
description: Guidelines for designing REST APIs. Use when creating or reviewing API endpoints.
license: MIT
allowed-tools:
  - Read
  - Write
  - Bash
metadata:
  author: "Your Name"
  version: "1.0"
---

# API Design Guidelines

## URL Structure

Use nouns for resources:
- ✅ `/users`, `/orders`, `/products`
- ❌ `/getUsers`, `/createOrder`

## HTTP Methods

| Method | Purpose        | Idempotent |
|--------|----------------|------------|
| GET    | Read           | Yes        |
| POST   | Create         | No         |
| PUT    | Replace        | Yes        |
| PATCH  | Partial update | No         |
| DELETE | Remove         | Yes        |

## Response Codes

...
```

### Frontmatter Fields

| Field           | Type         | Required | Description                        |
|-----------------|--------------|----------|------------------------------------|
| `name`          | `str`        | Yes      | Skill identifier (lowercase, hyphens) |
| `description`   | `str`        | Yes      | What and when to use (max 1024)    |
| `license`       | `str`        | No       | License identifier                 |
| `allowed-tools` | `list[str]`  | No       | Pre-approved tools                 |
| `metadata`      | `dict`       | No       | Custom key-value pairs             |

### Directory Structure

```
skills/
└── api-design/
    ├── SKILL.md           # Required: Main skill file
    ├── references/        # Optional: Additional documents
    │   ├── openapi.md
    │   └── examples.md
    └── scripts/           # Optional: Helper scripts
        └── validate_api.py
```

### Skill Dataclass

```python
@dataclass
class Skill:
    frontmatter: SkillFrontmatter
    body: str               # Instructions after frontmatter
    path: Path              # Skill directory
    source: str = "project" # "builtin", "global", "plugin", "project"

    @property
    def name(self) -> str
    @property
    def description(self) -> str
    @property
    def allowed_tools(self) -> list[str]
    @property
    def body_line_count(self) -> int
    @property
    def exceeds_soft_limit(self) -> bool  # >500 lines

    def list_reference_files(self) -> list[Path]
    def list_scripts(self) -> list[Path]
    def get_metadata_for_prompt(self) -> str
    def get_full_content(self) -> str
```

---

## Plugin Lifecycle

### Discovery Order

Plugins are discovered in this order (later sources override earlier):

1. `~/.config/brynhild/plugins/` - Global plugins
2. `$BRYNHILD_PLUGIN_PATH` - Environment variable (colon-separated)
3. `<project>/.brynhild/plugins/` - Project plugins

### Initialization

When Brynhild loads, it:

1. Discovers all plugins
2. Validates manifests
3. Fires `PLUGIN_INIT` hooks
4. Loads tools and registers them
5. Loads providers and registers them
6. Loads commands
7. Loads skills

### Shutdown

When Brynhild exits:

1. Fires `PLUGIN_SHUTDOWN` hooks
2. Closes any open resources

### Lifecycle Hooks Example

```yaml
# hooks.yaml
version: 1

hooks:
  plugin_init:
    - name: setup-database
      type: command
      command: |
        echo "Initializing $BRYNHILD_PLUGIN_NAME"
        ./scripts/init_db.sh
      timeout:
        seconds: 60
        on_timeout: block

  plugin_shutdown:
    - name: cleanup-database
      type: command
      command: |
        echo "Cleaning up $BRYNHILD_PLUGIN_NAME"
        ./scripts/cleanup_db.sh
```

---

## Stubs for Standalone Testing

The `brynhild.plugins.stubs` module provides standalone-compatible base classes:

```python
# In your plugin tool:
try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    from brynhild.plugins.stubs import ToolResult, ToolBase

class Tool(ToolBase):
    ...
```

### Available Stubs

```python
from brynhild.plugins.stubs import (
    ToolResult,     # Dataclass for tool results
    ToolBase,       # Base class for tools
    Tool,           # Alias for ToolBase
    ToolMetrics,    # Usage statistics tracking
)
```

### ToolBase Stub

```python
class ToolBase:
    """Base class with default implementations."""

    @property
    def name(self) -> str:
        raise NotImplementedError()

    @property
    def description(self) -> str:
        raise NotImplementedError()

    @property
    def input_schema(self) -> dict[str, Any]:
        raise NotImplementedError()

    @property
    def requires_permission(self) -> bool:
        return True

    @property
    def version(self) -> str:
        return "0.0.0"

    @property
    def categories(self) -> list[str]:
        return []

    @property
    def examples(self) -> list[dict]:
        return []

    async def execute(self, input: dict) -> ToolResult:
        raise NotImplementedError()

    def to_api_format(self) -> dict:
        """Anthropic API format."""
        ...

    def to_openai_format(self) -> dict:
        """OpenAI API format."""
        ...
```

### Testing Without Brynhild

```python
# test_my_tool.py
import asyncio
from tools.my_tool import Tool

async def test_tool():
    tool = Tool()
    
    # Test properties
    assert tool.name == "MyTool"
    assert "object" in tool.input_schema.get("type", "")
    
    # Test execution
    result = await tool.execute({"input": "test"})
    assert result.success
    print(f"Output: {result.output}")

if __name__ == "__main__":
    asyncio.run(test_tool())
```

---

## See Also

- [Plugin Development Guide](plugin-development-guide.md) - Tutorial-style guide
- [Plugin Tool Interface](plugin-tool-interface.md) - Tool interface specification
- [API Reference](api-reference.md) - Complete API reference
- [Tool Testing Guide](tool-testing.md) - Testing tools

