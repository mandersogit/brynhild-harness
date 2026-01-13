# Plugin Development Guide

This guide covers how to develop plugins for Brynhild, from initial setup to testing and deployment.

> **⚠️ Deprecation Notice**: Directory-based plugins (using `plugin.yaml` and filesystem directories) are **deprecated** in favor of entry-point plugins (pip-installable packages). Directory-based plugins will be removed in a future major version. For new plugins, use the [Packaged Plugins](#packaged-plugins-entry-points) approach.

## Overview

Brynhild plugins can extend the system with:
- **Tools** - New capabilities for the LLM (e.g., API calls, calculations)
- **Providers** - Alternative LLM backends (e.g., local models, custom endpoints)
- **Commands** - Custom slash commands (e.g., `/deploy`, `/summarize`)
- **Skills** - Behavioral guidance for the LLM (e.g., coding standards, personas)
- **Hooks** - Event handlers (e.g., pre/post tool execution)
- **Rules** - Project-specific instructions and guidelines

## Quick Start

**For new plugins, skip to [Packaged Plugins (Entry Points)](#packaged-plugins-entry-points).**

The following directory-based approach is deprecated but still supported:

### 1. Create Plugin Structure (Deprecated)

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

Brynhild discovers plugins from these locations (highest priority first):

1. **Entry Points** (pip-installed packages)
   - Plugins registered via `pyproject.toml` entry points
   - Highest priority — override directory plugins with same name

2. **Project Plugins**: `<project>/.brynhild/plugins/`
   - Plugins in the current project's plugins directory

3. **Environment Variable**: `BRYNHILD_PLUGIN_PATH`
   - Colon-separated list of plugin paths
   - Example: `/path/to/plugin1:/path/to/plugin2`

4. **Global Plugins**: `~/.config/brynhild/plugins/`
   - User-wide plugins (lowest priority)

### Checking Plugin Discovery

```bash
# List discovered plugins
brynhild plugins list

# Show search paths
brynhild plugins paths
```

---

## Packaged Plugins (Entry Points)

For distributable plugins, you can create a pip-installable package that registers via Python entry points. This enables users to install your plugin with a simple `pip install`.

### Benefits

- **One-command installation**: `pip install brynhild-my-plugin`
- **Dependency management**: pip handles transitive dependencies
- **Version management**: semantic versioning, upgrade paths
- **No path configuration**: entry points are discovered automatically

### Creating a Packaged Plugin

#### 1. Project Structure

```
brynhild-my-plugin/
├── pyproject.toml
├── README.md
└── src/
    └── brynhild_my_plugin/
        ├── __init__.py
        ├── tools/
        │   └── my_tool.py
        └── providers/
            └── my_provider.py
```

#### 2. pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "brynhild-my-plugin"
version = "1.0.0"
description = "My awesome Brynhild plugin"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
dependencies = [
    "brynhild>=0.2.0",
    # Add your plugin's dependencies here
]

# Register the plugin manifest (metadata, lifecycle)
[project.entry-points."brynhild.plugins"]
my-plugin = "brynhild_my_plugin:register"

# REQUIRED for tools: Register each tool class directly
# Packaged plugins don't have a tools/ directory, so this is how
# Brynhild discovers your tools. Without this, your tools won't load!
[project.entry-points."brynhild.tools"]
MyTool = "brynhild_my_plugin.tools.my_tool:Tool"

# Register providers (if your plugin provides any)
[project.entry-points."brynhild.providers"]
my-provider = "brynhild_my_plugin.providers.my_provider:Provider"

[tool.hatch.build.targets.wheel]
packages = ["src/brynhild_my_plugin"]
```

> **⚠️ Important**: For packaged plugins, the `brynhild.tools` entry point is **required** for each tool you want to expose. Unlike directory-based plugins (which load tools from `tools/*.py` files), packaged plugins have no filesystem path for Brynhild to scan. The entry point IS how your tools get discovered.

#### 3. Register Function

```python
# src/brynhild_my_plugin/__init__.py
import brynhild.plugins.manifest as manifest

def register() -> manifest.PluginManifest:
    """Register this plugin with Brynhild."""
    return manifest.PluginManifest(
        name="my-plugin",
        version="1.0.0",
        description="My awesome Brynhild plugin",
        tools=["MyTool"],
        providers=["my-provider"],
    )
```

#### 4. Install and Test

```bash
# Install in development mode
cd brynhild-my-plugin/
pip install -e .

# Verify it's discovered
brynhild plugins list
# Should show: my-plugin  1.0.0  entry_point  brynhild-my-plugin  enabled

# Test the plugin
brynhild chat "Use MyTool to do something"
```

### Entry Point Groups

| Group | Purpose | Value Format | Returns |
|-------|---------|--------------|---------|
| `brynhild.plugins` | Plugin manifest/metadata | `module:register_function` | `PluginManifest` or `Plugin` |
| `brynhild.tools` | Tool class registration | `module.path:ToolClass` | Tool class |
| `brynhild.providers` | Provider class registration | `module.path:ProviderClass` | Provider class |
| `brynhild.hooks` | Hook configuration | `module:get_hooks` | `HooksConfig` or dict |
| `brynhild.skills` | Skill definition | `module:get_skill` | `Skill` or dict |
| `brynhild.commands` | Slash command | `module:get_command` | `Command` or dict |
| `brynhild.rules` | Project rules | `module:get_rules` | string, list, or dict |
| `brynhild.profiles` | Model profiles | `module:get_profiles` | `ModelProfile`, dict, or list |

### Understanding Entry Points for Packaged Plugins

**Why do packaged plugins need explicit entry points?**

Directory-based plugins (in `~/.config/brynhild/plugins/` or `BRYNHILD_PLUGIN_PATH`) have a `tools/` folder that Brynhild scans at runtime. But packaged plugins installed via pip don't have a predictable filesystem location — they're inside a wheel/egg in `site-packages`.

**Entry points solve this**: They tell Python "this package provides X at import path Y", letting Brynhild discover your components without knowing where files are.

### What You Need

| Plugin Type | `plugins` | `tools` | `providers` | `hooks` | `skills` | `commands` | `rules` | `profiles` |
|-------------|-----------|---------|-------------|---------|----------|------------|---------|------------|
| **Single tool** | Optional | ✅ | — | — | — | — | — | — |
| **Single provider** | Optional | — | ✅ | — | — | — | — | If has profiles |
| **Full plugin** | ✅ Recommended | If has tools | If has providers | If has hooks | If has skills | If has commands | If has rules | If has profiles |

**Note**: Each component type needs its own entry point. A plugin with tools AND hooks needs BOTH `brynhild.tools` AND `brynhild.hooks` entry points.

### Full Plugin Entry Points

For a complete plugin with tools, you need BOTH entry point types:

```toml
# Plugin manifest — provides name, version, description, lifecycle hooks
[project.entry-points."brynhild.plugins"]
my-plugin = "brynhild_my_plugin:register"

# Tool registration — makes each tool discoverable
# Without these, your tools WON'T be loaded even if declared in the manifest!
[project.entry-points."brynhild.tools"]
MyTool = "brynhild_my_plugin.tools.my_tool:Tool"
AnotherTool = "brynhild_my_plugin.tools.another:Tool"
```

The manifest's `tools=["MyTool", "AnotherTool"]` declares what the plugin provides. The `brynhild.tools` entry points tell Python where to find them.

### Registering Hooks via Entry Points

```toml
[project.entry-points."brynhild.hooks"]
my-hooks = "my_package:get_hooks"
```

```python
# my_package/__init__.py
import brynhild.hooks.config as hooks_config

def get_hooks() -> hooks_config.HooksConfig:
    """Return hooks configuration."""
    return hooks_config.HooksConfig(
        hooks={
            "pre_tool_use": [
                hooks_config.HookDefinition(
                    name="log-tool",
                    type="command",  # REQUIRED: "command", "script", or "prompt"
                    command="echo 'Using tool: $BRYNHILD_TOOL_NAME'",
                    enabled=True,
                    timeout=hooks_config.HookTimeoutConfig(seconds=30),
                ),
            ],
        }
    )
```

**HookDefinition required fields:**
- `name` - Unique identifier for the hook
- `type` - One of: `"command"`, `"script"`, `"prompt"`
- For `type="command"`: provide `command`
- For `type="script"`: provide `script` (path to Python file)
- For `type="prompt"`: provide `prompt` (LLM prompt template)

**Optional fields:**
- `enabled` - Whether the hook is active (default: True)
- `timeout` - `HookTimeoutConfig(seconds=N, on_timeout="block"|"continue")`
- `match` - Dict of conditions for when to trigger

Or return a dict:

```python
def get_hooks() -> dict:
    return {
        "hooks": {
            "pre_tool_use": [
                {
                    "name": "log-tool",
                    "type": "command",  # REQUIRED
                    "command": "echo 'Tool used'",
                    "timeout": {"seconds": 30},  # Dict format for timeout
                }
            ]
        }
    }
```

### Registering Skills via Entry Points

```toml
[project.entry-points."brynhild.skills"]
my-skill = "my_package.skills:get_skill"
```

```python
# my_package/skills.py
def get_skill() -> dict:
    """Return skill definition."""
    return {
        "name": "my-skill",  # REQUIRED: lowercase, hyphens allowed
        "description": "Helps with X when the user asks about Y",  # REQUIRED
        "body": """
# My Skill

Instructions for the LLM when this skill is activated...
""",
        "allowed_tools": ["Read", "Write"],  # Optional: pre-approved tools
    }
```

**Skill name requirements:**
- Must be lowercase
- Can contain hyphens (not underscores)
- Pattern: `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (or single character)

Or return a `Skill` instance directly:

```python
import pathlib
import brynhild.skills.skill as skill_module

def get_skill() -> skill_module.Skill:
    return skill_module.Skill(
        frontmatter=skill_module.SkillFrontmatter(
            name="my-skill",
            description="Helps with X when user asks about Y",
        ),
        body="# My Skill\n\nInstructions for the LLM...",
        path=pathlib.Path("<entry-point>"),
        source="entry_point",
    )
```

### Registering Commands via Entry Points

```toml
[project.entry-points."brynhild.commands"]
my-command = "my_package.commands:get_command"
```

```python
# my_package/commands.py
def get_command() -> dict:
    """Return slash command definition."""
    return {
        "name": "deploy",  # REQUIRED: command name (user types /deploy)
        "description": "Deploy the current project",  # Shown in /help
        "aliases": ["d", "ship"],  # Alternative names
        "args": "[environment]",  # Argument syntax shown to user
        "body": """
Deploy the project to {{args}} environment.

Current directory: {{cwd}}
""",
    }
```

**Template variables in `body`:**
- `{{args}}` - Arguments passed to the command
- `{{cwd}}` - Current working directory
- `{{env.VAR_NAME}}` - Environment variables

Or return a `Command` instance directly:

```python
import pathlib
import brynhild.plugins.commands as commands_module

def get_command() -> commands_module.Command:
    return commands_module.Command(
        frontmatter=commands_module.CommandFrontmatter(
            name="deploy",
            description="Deploy the current project",
            aliases=["d", "ship"],
            args="[environment]",
        ),
        body="Deploy to {{args}}...",
        path=pathlib.Path("<entry-point>"),
        plugin_name="my-plugin",
    )
```

### Registering Rules via Entry Points

```toml
[project.entry-points."brynhild.rules"]
my-rules = "my_package.rules:get_rules"
```

```python
# my_package/rules.py
def get_rules() -> str:
    """Return project rules."""
    return """
# Coding Standards

1. Use type hints for all functions
2. Write tests for new features
3. Follow PEP 8
"""
```

Or return multiple rules:

```python
def get_rules() -> list[str]:
    return [
        "# Rule 1\n...",
        "# Rule 2\n...",
    ]
```

### Registering Profiles via Entry Points

```toml
[project.entry-points."brynhild.profiles"]
my-profiles = "my_package.profiles:get_profiles"
```

```python
# my_package/profiles.py
import brynhild.profiles.types as profile_types

def get_profiles() -> profile_types.ModelProfile:
    """Return a model profile."""
    return profile_types.ModelProfile(
        name="my-custom-model",
        family="custom",
        description="Custom model profile for my provider",
        default_temperature=0.7,
        supports_tools=True,
    )
```

Or return multiple profiles:

```python
def get_profiles() -> list[dict]:
    """Return multiple profiles as dicts."""
    return [
        {
            "name": "my-model-fast",
            "family": "custom",
            "description": "Fast variant",
            "default_temperature": 0.5,
        },
        {
            "name": "my-model-quality",
            "family": "custom",
            "description": "High quality variant",
            "default_temperature": 0.8,
        },
    ]
```

### Example: Minimal Tool-Only Package

For a simple single-tool package, you only need the `brynhild.tools` entry point — no manifest required:

```toml
# pyproject.toml for a single-tool package
[project]
name = "brynhild-calculator"
version = "1.0.0"
dependencies = ["brynhild>=0.2.0"]

# Just the tool entry point — no brynhild.plugins needed for tool-only packages
[project.entry-points."brynhild.tools"]
Calculator = "brynhild_calculator:Calculator"
```

```python
# brynhild_calculator.py
class Calculator:
    name = "Calculator"
    description = "Evaluates mathematical expressions"
    
    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression"}
            },
            "required": ["expression"]
        }
    
    async def execute(self, input):
        from brynhild.tools.base import ToolResult
        try:
            result = eval(input["expression"])  # Use a safe evaluator in production!
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
```

### Verifying Your Plugin Works

**Always test that Brynhild can actually discover your tools:**

```bash
# After pip install -e . or pip install your-package

# Check if your tools are listed
brynhild tools list

# Check plugin registration (if using brynhild.plugins)
brynhild plugins list

# Try using the tool
brynhild chat "Use Calculator to evaluate 2 + 2"
```

If your tool doesn't appear in `brynhild tools list`, check:
1. Is the `brynhild.tools` entry point in your `pyproject.toml`?
2. Is the import path correct? Test it manually: `python -c "from your_package.tools:Tool"`
3. Does the class have `name`, `description`, `input_schema`, and `execute()`?

### Publishing to PyPI

```bash
# Build the package
pip install build
python -m build

# Upload to PyPI (requires account)
pip install twine
twine upload dist/*

# Users can now install with:
pip install brynhild-my-plugin
```

## Implementing Components

### Tools

See [Plugin Tool Interface](plugin-tool-interface.md) for the complete specification.

Key points:
- Class must be named `Tool`
- Use `@property` for `name`, `description`, and `input_schema`
- Use `execute(input: dict) -> ToolResult` for execution

### Providers

Providers implement the `LLMProvider` interface. The base class has abstract methods you must implement:

```python
# providers/my_provider.py
from __future__ import annotations
import typing as _typing

import brynhild.api.base as _base
import brynhild.api.types as _types


class Provider(_base.LLMProvider):
    """Custom LLM provider."""

    # Class attribute for provider identification (used in entry point discovery)
    PROVIDER_NAME = "my-provider"

    def __init__(
        self,
        *,
        model: str = "default-model",
        api_key: str | None = None,
        **kwargs: _typing.Any,
    ) -> None:
        self._model = model
        self._api_key = api_key

    # REQUIRED: Abstract property - must implement
    @property
    def name(self) -> str:
        return "my-provider"

    # REQUIRED: Abstract property - must implement
    @property
    def model(self) -> str:
        return self._model

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True

    # REQUIRED: Abstract method
    async def complete(
        self,
        messages: list[_types.Message],
        *,
        tools: list[_types.Tool] | None = None,
        **kwargs: _typing.Any,
    ) -> _types.CompletionResponse:
        """Return a completion response."""
        # Your API call logic here
        return _types.CompletionResponse(
            id="response-id",
            content="Response text",
            tool_uses=[],  # List of ToolUse if the LLM wants to call tools
            stop_reason="stop",
            usage=_types.Usage(input_tokens=100, output_tokens=50),
        )

    # REQUIRED: Abstract method
    async def stream(
        self,
        messages: list[_types.Message],
        *,
        tools: list[_types.Tool] | None = None,
        **kwargs: _typing.Any,
    ) -> _typing.AsyncIterator[_types.StreamEvent]:
        """Yield streaming events."""
        yield _types.StreamEvent(type="text_delta", text="Response")
        yield _types.StreamEvent(
            type="message_stop",
            stop_reason="stop",
            usage=_types.Usage(input_tokens=100, output_tokens=50),
        )
```

**Required implementations:**
- `name` property - Provider identifier
- `model` property - Current model being used
- `complete()` method - Non-streaming completion
- `stream()` method - Streaming completion

#### Provider Credentials Path

Providers can receive credentials from a file via the `credentials_path` config option. The factory automatically expands `~` and `$VAR` in the path before passing it to your provider.

**Config example:**
```yaml
providers:
  instances:
    my-provider-prod:
      type: my-provider
      credentials_path: ~/.config/brynhild/credentials/my-provider.json
```

**In your provider:**
```python
class Provider(_base.LLMProvider):
    def __init__(
        self,
        *,
        model: str = "default",
        api_key: str | None = None,
        credentials_path: str | None = None,  # Factory passes expanded path
        **kwargs: _typing.Any,
    ) -> None:
        # Load credentials from file if provided
        if credentials_path:
            import brynhild.api.credentials as _credentials
            creds = _credentials.load_credentials_from_path(credentials_path)
            api_key = creds.get("api_key", api_key)
        
        self._api_key = api_key
        self._model = model
```

The `load_credentials_from_path()` utility:
- Loads a JSON file from the given path
- Returns a dict with the file contents
- Raises `ValueError` on missing file, invalid JSON, or permission errors

**Opting out of path expansion:**

If your provider needs the raw unexpanded path (e.g., to pass to an external library that handles expansion itself), set the class variable:

```python
class Provider(_base.LLMProvider):
    expand_credentials_path = False  # Don't expand ~ and $VAR
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

#### Tool Not Loading (Directory Plugin)

```
Failed to load tool 'my_tool' from plugin 'my-plugin'
```

**Solutions:**
- Ensure class is named `Tool`
- Verify interface methods are correct (properties vs attributes)
- Check import errors with `python -c "from tools.my_tool import Tool"`

#### Tool Not Loading (Packaged Plugin)

```
Entry point plugin 'my-plugin' declares tools that were NOT loaded: ['MyTool']
```

**This error means you're missing `brynhild.tools` entry points.**

Packaged plugins (installed via pip) cannot load tools from a `tools/` directory — they have no filesystem path for Brynhild to scan. You **must** register each tool via an entry point:

```toml
# Add this to your pyproject.toml
[project.entry-points."brynhild.tools"]
MyTool = "your_package.tools.my_tool:Tool"
```

**Solutions:**
1. Add `brynhild.tools` entry point for each tool in `pyproject.toml`
2. Verify the import path is correct: `python -c "from your_package.tools.my_tool import Tool"`
3. Re-install the package: `pip install -e .` (entry points are only read at install time)
4. Check `brynhild tools list` to verify the tool appears

#### Tool Appears in Manifest But Not in `brynhild tools list`

This usually means the entry point is missing or has the wrong import path.

**Diagnosis:**
```bash
# Check what entry points Python sees from your package
python -c "import importlib.metadata; print(list(importlib.metadata.entry_points(group='brynhild.tools')))"
```

If your tool doesn't appear, either:
- The entry point isn't in `pyproject.toml`, or
- You need to reinstall after editing `pyproject.toml`: `pip install -e .`

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

