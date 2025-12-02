# Plugin Development Guide

This guide covers how to develop plugins for Brynhild, from initial setup to testing and deployment.

## Overview

Brynhild plugins can extend the system with:
- **Tools** - New capabilities for the LLM (e.g., API calls, calculations)
- **Providers** - Alternative LLM backends (e.g., local models, custom endpoints)
- **Commands** - Custom slash commands (e.g., `/deploy`, `/summarize`)
- **Skills** - Behavioral guidance for the LLM (e.g., coding standards, personas)
- **Hooks** - Event handlers (e.g., pre/post tool execution)

## Quick Start

### 1. Create Plugin Structure

```bash
mkdir -p my-plugin/tools
touch my-plugin/plugin.yaml
touch my-plugin/tools/my_tool.py
```

### 2. Create Plugin Manifest

```yaml
# my-plugin/plugin.yaml
name: my-plugin
version: 1.0.0
description: My awesome plugin

tools:
  - my_tool
```

### 3. Implement a Tool

```python
# my-plugin/tools/my_tool.py
from __future__ import annotations
import typing as _typing

try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    from dataclasses import dataclass
    @dataclass
    class ToolResult:
        success: bool
        output: str
        error: str | None = None
    class ToolBase:
        pass

class Tool(ToolBase):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input value"},
            },
            "required": ["input"],
        }

    async def execute(self, input: dict[str, _typing.Any]) -> ToolResult:
        value = input.get("input", "")
        return ToolResult(success=True, output=f"Processed: {value}")
```

### 4. Install Plugin

```bash
# Option A: Environment variable
export BRYNHILD_PLUGIN_PATH="/path/to/my-plugin"

# Option B: Symlink to global plugins directory
mkdir -p ~/.config/brynhild/plugins
ln -s /path/to/my-plugin ~/.config/brynhild/plugins/my-plugin
```

### 5. Test It

```bash
brynhild chat "Use my_tool with input 'hello'"
```

## Plugin Structure

```
my-plugin/
├── plugin.yaml           # Required: Plugin manifest
├── README.md             # Recommended: Plugin documentation
├── tools/                # Optional: Tool implementations
│   ├── __init__.py
│   └── my_tool.py
├── providers/            # Optional: LLM providers
│   └── my_provider.py
├── commands/             # Optional: Slash commands
│   └── my_command.md
├── skills/               # Optional: Skill definitions
│   └── my-skill/
│       └── SKILL.md
└── hooks.yaml            # Optional: Hook definitions
```

## Plugin Manifest

The `plugin.yaml` file describes your plugin:

```yaml
name: my-plugin           # Required: Unique identifier
version: 1.0.0            # Required: Semantic version
description: ...          # Required: Human-readable description

# Optional: List component files (without extensions)
tools:
  - calculator
  - api_client

providers:
  - my_provider

commands:
  - deploy
  - status

skills:
  - coding-standards
  - debugging
```

## Plugin Discovery

Brynhild discovers plugins from these locations (in order):

1. **Environment Variable**: `BRYNHILD_PLUGIN_PATH`
   - Colon-separated list of plugin paths
   - Example: `/path/to/plugin1:/path/to/plugin2`

2. **Project Plugins**: `<project>/.brynhild/plugins/`
   - Plugins in the current project's plugins directory

3. **Global Plugins**: `~/.config/brynhild/plugins/`
   - User-wide plugins

### Checking Plugin Discovery

```bash
# List discovered plugins
brynhild plugins list

# Show search paths
brynhild plugins paths
```

## Implementing Components

### Tools

See [Plugin Tool Interface](plugin-tool-interface.md) for the complete specification.

Key points:
- Class must be named `Tool`
- Use `@property` for `name`, `description`, and `input_schema`
- Use `execute(input: dict) -> ToolResult` for execution

### Providers

Providers implement the `LLMProvider` interface:

```python
# providers/my_provider.py
from __future__ import annotations
import typing as _typing

try:
    import brynhild.api.base as _base
    ProviderBase = _base.LLMProvider
except ImportError:
    class ProviderBase:
        pass

class Provider(ProviderBase):
    PROVIDER_NAME = "my-provider"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "default-model",
        **kwargs: _typing.Any,
    ) -> None:
        self._api_key = api_key
        self._model = model

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
        **kwargs: _typing.Any,
    ) -> _typing.Any:
        # Implement completion logic
        ...

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        **kwargs: _typing.Any,
    ) -> _typing.AsyncIterator[_typing.Any]:
        # Implement streaming logic
        ...

    async def close(self) -> None:
        # Cleanup resources
        pass
```

### Commands

Commands are Markdown files with YAML frontmatter:

```markdown
<!-- commands/deploy.md -->
---
name: deploy
aliases: [d, ship]
description: Deploy the current project
---

# Deploy Command

This command deploys your project to production.

## Usage

/deploy [environment]

## Arguments

- **environment** (optional): Target environment (default: staging)
```

### Skills

Skills are Markdown files with guidance for the LLM:

```markdown
<!-- skills/coding-standards/SKILL.md -->
---
name: coding-standards
description: Project coding standards and conventions
---

# Coding Standards

Follow these conventions when writing code for this project:

1. Use descriptive variable names
2. Write tests for all new features
3. Follow the existing code style
...
```

### Hooks

Hooks are defined in YAML and can trigger on specific events:

```yaml
# hooks.yaml
version: 1

hooks:
  # Plugin lifecycle hooks
  plugin_init:
    - name: initialize_resources
      type: command
      command: "./scripts/init.sh"

  plugin_shutdown:
    - name: cleanup_resources
      type: command
      command: "./scripts/cleanup.sh"

  # Tool hooks
  pre_tool_use:
    - name: block-dangerous
      type: script
      script: "./scripts/block_dangerous.py"  # Must be a file path, not inline code

  post_tool_use:
    - name: log-tool-usage
      type: command
      command: "echo 'Tool used: $BRYNHILD_TOOL_NAME' >> /tmp/tool-log.txt"
```

#### Available Hook Events

| Event | Description | Can Block | Can Modify |
|-------|-------------|-----------|------------|
| `plugin_init` | Plugin loaded and initialized | No | No |
| `plugin_shutdown` | Brynhild is exiting | No | No |
| `pre_tool_use` | Before tool execution | Yes | Yes (input) |
| `post_tool_use` | After tool execution | No | Yes (output) |
| `pre_message` | Before sending to LLM | Yes | Yes (message) |
| `post_message` | After receiving from LLM | No | Yes (response) |

#### Plugin Lifecycle Hooks

Use `plugin_init` and `plugin_shutdown` for resource management:

```yaml
hooks:
  plugin_init:
    - name: connect_database
      type: command
      command: |
        echo "Initializing plugin: $BRYNHILD_PLUGIN_NAME"
        ./scripts/connect.sh

  plugin_shutdown:
    - name: disconnect_database
      type: command
      command: |
        echo "Shutting down plugin: $BRYNHILD_PLUGIN_NAME"
        ./scripts/disconnect.sh
```

Environment variables available in plugin hooks:
- `BRYNHILD_PLUGIN_NAME` - Plugin name
- `BRYNHILD_PLUGIN_PATH` - Plugin directory path
- `BRYNHILD_EVENT` - Event name
- `BRYNHILD_CWD` - Current working directory

#### Hook Types

**`type: command`** - Run a shell command. Can be inline or call a script:

```yaml
hooks:
  plugin_init:
    - name: simple_command
      type: command
      command: "echo 'Hello from $BRYNHILD_PLUGIN_NAME'"

    - name: call_script
      type: command
      command: "./scripts/init.sh"
```

**`type: script`** - Run an external Python script file. **The value must be a file path, not inline code.**

```yaml
hooks:
  pre_tool_use:
    - name: validate_input
      type: script
      script: "./scripts/validate.py"  # File path, NOT inline Python
```

The script receives context as JSON on stdin and outputs result as JSON on stdout:

```python
# scripts/validate.py
import json
import sys

context = json.load(sys.stdin)
tool_name = context.get("tool")
tool_input = context.get("tool_input", {})

# Check for dangerous commands
if tool_name == "Bash" and "rm -rf" in tool_input.get("command", ""):
    json.dump({"action": "block", "message": "Dangerous command blocked"}, sys.stdout)
else:
    json.dump({"action": "continue"}, sys.stdout)
```

**`type: prompt`** - LLM-based hook (uses an LLM to decide):

```yaml
hooks:
  pre_message:
    - name: classify_intent
      type: prompt
      prompt: "Classify the user's intent: {{message}}"
```

> **Note**: Inline Python code in YAML is NOT supported. For Python logic, create a separate `.py` file and reference it with `type: script`.

## Testing Plugins

### Standalone Testing

Test your tools without Brynhild installed:

```python
# test_my_tool.py
import asyncio
from tools.my_tool import Tool

async def test():
    tool = Tool()
    result = await tool.execute({"input": "hello"})
    assert result.success
    print(result.output)

if __name__ == "__main__":
    asyncio.run(test())
```

Run:
```bash
python test_my_tool.py
```

### Integration Testing

Test with Brynhild:

```bash
# Set plugin path
export BRYNHILD_PLUGIN_PATH="/path/to/my-plugin"

# Run brynhild and test
brynhild chat "Use my_tool with input 'test'"
```

## Debugging

### Common Issues

#### Plugin Not Found

```
Plugin 'my-plugin' not found
```

**Solutions:**
- Check `BRYNHILD_PLUGIN_PATH` is set correctly
- Verify `plugin.yaml` exists and is valid YAML
- Run `brynhild plugins paths` to see search paths

#### Tool Not Loading

```
Failed to load tool 'my_tool' from plugin 'my-plugin'
```

**Solutions:**
- Ensure class is named `Tool`
- Verify interface methods are correct (properties vs attributes)
- Check import errors with `python -c "from tools.my_tool import Tool"`

#### Interface Mismatch

```
'Tool' object has no attribute 'input_schema'
```

**Solutions:**
- Use `@property` for `name`, `description`, and `input_schema`
- Ensure `input_schema` returns a dict, not a class attribute
- See [Plugin Tool Interface](plugin-tool-interface.md)

### Enabling Debug Logging

```bash
export BRYNHILD_LOG_LEVEL=DEBUG
brynhild chat "test"
```

## Best Practices

### 1. Use Descriptive Names

```python
# Good
name = "api_client"
description = "Makes authenticated API calls to external services"

# Bad
name = "tool1"
description = "Does stuff"
```

### 2. Validate Inputs

```python
async def execute(self, input: dict) -> ToolResult:
    url = input.get("url", "")
    if not url:
        return ToolResult(success=False, output="", error="URL is required")
    if not url.startswith(("http://", "https://")):
        return ToolResult(success=False, output="", error="Invalid URL format")
    ...
```

### 3. Handle Errors Gracefully

```python
async def execute(self, input: dict) -> ToolResult:
    try:
        result = await self._do_operation(input)
        return ToolResult(success=True, output=result)
    except ValidationError as e:
        return ToolResult(success=False, output="", error=f"Invalid input: {e}")
    except ConnectionError as e:
        return ToolResult(success=False, output="", error=f"Connection failed: {e}")
    # Let unexpected errors bubble up to the framework
```

### 4. Document Everything

- Add docstrings to all classes and methods
- Include usage examples in descriptions
- Create a README.md for your plugin

### 5. Test Thoroughly

- Write standalone tests for each tool
- Test edge cases and error conditions
- Test with the full Brynhild system

## Example Plugins

See `examples/plugins/` for complete working examples:
- `calculator/` - Safe math expression evaluator with comprehensive tests

## See Also

- [Plugin Tool Interface](plugin-tool-interface.md)
- [Tool Error Handling](tool-error-handling.md)
- [Tool Permissions](tool-permissions.md)
- [Tool Testing](tool-testing.md)

