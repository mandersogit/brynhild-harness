# Tool Registry

This guide explains how Brynhild's tool registry works and how tools are discovered, registered, and made available to the LLM.

## Overview

The Tool Registry is the central manager for all tools available during a Brynhild session. It:

1. **Registers** tools from built-in and plugin sources
2. **Provides** tool definitions to the LLM
3. **Dispatches** tool calls to the correct implementation

## How Tools Are Registered

### 1. Built-in Tools

Brynhild includes these built-in tools:

| Tool | Description |
|------|-------------|
| `Bash` | Execute shell commands |
| `Read` | Read file contents |
| `Write` | Write/create files |
| `Edit` | Edit existing files |
| `Grep` | Search file contents |
| `Glob` | Find files by pattern |
| `Inspect` | Inspect filesystem entries |
| `LearnSkill` | Load and manage skills |

Built-in tools are registered automatically unless disabled via settings.

### 2. Plugin Tools

Plugin tools are discovered and registered from:

1. **Environment Variable**: `BRYNHILD_PLUGIN_PATH`
2. **Project Plugins**: `<project>/plugins/`
3. **Global Plugins**: `~/.brynhild/plugins/`

Each plugin's `plugin.yaml` declares which tools it provides:

```yaml
name: my-plugin
tools:
  - calculator
  - api_client
```

## Registry API

### Building the Registry

The registry is built from settings at startup:

```python
import brynhild.tools.registry as registry
import brynhild.config as config

settings = config.Settings()
tool_registry = registry.build_registry_from_settings(settings)
```

### Getting a Tool

```python
# Get a specific tool
tool = tool_registry.get("Bash")
if tool:
    result = await tool.execute({"command": "ls -la"})

# Check if tool exists
if "Bash" in tool_registry:
    ...
```

### Listing Tools

```python
# Get all tool names
names = tool_registry.list_tools()
# ['Bash', 'Read', 'Write', 'Edit', 'Grep', 'Glob', 'Inspect', 'LearnSkill', 'calculator']

# Get all tool instances
for tool in tool_registry.values():
    print(f"{tool.name}: {tool.description}")
```

### API Format

Tools are converted to API format for the LLM:

```python
# Anthropic format
tools_for_anthropic = tool_registry.to_api_format()
# [{"name": "Bash", "description": "...", "input_schema": {...}}, ...]

# OpenAI/OpenRouter format
tools_for_openai = tool_registry.to_openai_format()
# [{"type": "function", "function": {"name": "Bash", ...}}, ...]
```

## Tool Lifecycle

### 1. Discovery

At startup, the registry discovers tools:

```
Settings → PluginRegistry → ToolLoader → ToolRegistry
```

```python
def build_registry_from_settings(settings):
    registry = ToolRegistry()
    
    # 1. Register built-in tools (unless disabled)
    if not settings.disable_builtin_tools:
        registry.register(BashTool(...))
        registry.register(ReadTool(...))
        # ...
    
    # 2. Load plugin tools
    _load_plugin_tools(registry, settings)
    
    return registry
```

### 2. Registration

Tools are registered by name:

```python
registry.register(tool_instance)
# Internally: self._tools[tool.name] = tool_instance
```

If a tool with the same name already exists, it is **replaced** (plugin tools can override built-ins).

### 3. Dispatch

When the LLM calls a tool:

```python
# LLM returns: tool_use(name="Bash", input={"command": "ls"})

tool = registry.get("Bash")
if tool:
    if tool.requires_permission:
        approved = await prompt_user_for_permission(tool_call)
        if not approved:
            return ToolResult(success=False, error="User denied")
    
    result = await tool.execute({"command": "ls"})
```

## Disabling Tools

### Disable All Built-ins

```bash
export BRYNHILD_DISABLE_BUILTIN_TOOLS=true
```

Only plugin tools will be available.

### Disable Specific Tools

```bash
export BRYNHILD_DISABLED_TOOLS="Bash,Write"
```

The specified tools won't be registered.

### Check if Disabled

```python
if settings.is_tool_disabled("Bash"):
    # Tool was disabled by configuration
```

## Tool Loading Internals

### The ToolLoader

```python
import brynhild.plugins.tools as tools

loader = tools.ToolLoader()

# Load from a specific plugin
tool_classes = loader.load_from_plugin(
    plugin_path=Path("/path/to/my-plugin"),
    plugin_name="my-plugin",
)
# {"calculator": <class Tool>, "api_client": <class Tool>}

# Instantiate and register
for name, cls in tool_classes.items():
    instance = cls()
    registry.register(instance)
```

### Tool Class Discovery

The loader looks for:

1. A class named `Tool` in the module
2. Any class with a `name` attribute and `execute` method

```python
# my_tool.py
class Tool:  # Preferred: class named "Tool"
    @property
    def name(self) -> str:
        return "my_tool"
    
    async def execute(self, input: dict) -> ToolResult:
        ...
```

### Handling Property-Based Names

The loader handles both class attributes and properties:

```python
# Class attribute (legacy)
class Tool:
    name = "my_tool"

# Property (preferred)
class Tool:
    @property
    def name(self) -> str:
        return "my_tool"
```

Both work, but properties are instantiated to get the value.

## Error Handling

### Tool Not Found

```python
tool = registry.get("nonexistent")
if tool is None:
    print("Tool not found")
```

### Plugin Load Failures

Plugin loading uses fail-soft behavior:

- If a plugin fails to load, others continue
- If a tool fails to load, other tools continue
- Built-in tools always work even if plugins fail

```python
# In registry.py
try:
    tool_classes = loader.load_from_plugin(...)
except Exception as e:
    logger.warning("Failed to load plugin: %s", e)
    # Continue with other plugins
```

### Duplicate Tool Names

If two plugins provide tools with the same name, the later one wins:

```python
# Plugin A: calculator tool loaded first
# Plugin B: calculator tool loaded second
# Result: Plugin B's calculator is used
```

## Advanced Usage

### Custom Registry

```python
registry = ToolRegistry()

# Add only specific tools
registry.register(ReadTool(...))
registry.register(GrepTool(...))

# Use custom registry
result = await process_with_tools(provider, messages, registry)
```

### Tool Introspection

```python
for tool in registry.values():
    print(f"Tool: {tool.name}")
    print(f"  Description: {tool.description}")
    print(f"  Requires Permission: {tool.requires_permission}")
    print(f"  Schema: {tool.input_schema}")
```

### Dynamic Tool Registration

```python
# Add a tool at runtime
registry.register(MyCustomTool())

# Remove a tool (not recommended, but possible)
del registry._tools["my_tool"]
```

## See Also

- [Plugin Tool Interface](plugin-tool-interface.md)
- [Plugin Development Guide](plugin-development-guide.md)
- [Tool Permissions](tool-permissions.md)

