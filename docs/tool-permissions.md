# Tool Permissions

This guide explains how the permission system works for Brynhild tools.

## Overview

When a tool executes, Brynhild may prompt the user for permission before proceeding. This is controlled by the `requires_permission` property.

## The Permission Prompt

When `requires_permission` returns `True`, users see a prompt:

```
┌──────────────────────────────────────────────────────┐
│ Tool: Bash                                           │
│ Command: rm -rf /tmp/test                            │
│                                                      │
│ [a] Allow  |  [d] Deny  |  [c] Cancel All            │
└──────────────────────────────────────────────────────┘
```

Users can:
- **Allow (a/y/Enter)**: Execute the tool
- **Deny (d/n/Esc)**: Skip this tool call
- **Cancel All (c/q/Ctrl+C)**: Abort the entire generation

## Setting requires_permission

Override the property to control permission behavior:

```python
class Tool(ToolBase):
    @property
    def requires_permission(self) -> bool:
        """Safe read-only tool - no permission needed."""
        return False
```

The default is `True` (require permission).

## When to Require Permission

### Require Permission (True)

Tools that:
- **Modify files** (write, delete, move)
- **Execute commands** (shell commands, scripts)
- **Access network** (API calls, downloads)
- **Access sensitive data** (credentials, private keys)
- **Have side effects** (send emails, deploy code)

```python
@property
def requires_permission(self) -> bool:
    return True  # This is the default
```

### Skip Permission (False)

Tools that:
- **Only read data** (file contents, system info)
- **Perform calculations** (math, parsing)
- **Are provably safe** (no side effects possible)

```python
@property
def requires_permission(self) -> bool:
    return False  # Safe read-only tool
```

## Dynamic Permissions

You can make permission conditional:

```python
class Tool(ToolBase):
    def __init__(self, allow_writes: bool = False):
        self._allow_writes = allow_writes
    
    @property
    def requires_permission(self) -> bool:
        # Only require permission if writes are allowed
        return self._allow_writes
```

## Interaction with Sandbox

The permission system is **separate from** the sandbox:

| System | Purpose | Enforcement |
|--------|---------|-------------|
| **Permissions** | User approval before execution | User prompt |
| **Sandbox** | Path/operation restrictions | OS-level enforcement |

A tool can:
- Require permission but be allowed by sandbox
- Not require permission but be blocked by sandbox
- Both require permission AND be sandboxed

Example:

```python
# This tool requires permission (user must approve)
# but the sandbox will also block writes outside project
class WriteFileTool(Tool):
    @property
    def requires_permission(self) -> bool:
        return True  # User must approve

    async def execute(self, input: dict) -> ToolResult:
        path = input.get("path")
        # Sandbox will validate path before write
        resolved = self._resolve_and_validate(path, "write")
        ...
```

## Auto-Approve Mode

For automated workflows, permissions can be auto-approved:

```bash
# CLI flag
brynhild chat --auto-approve "Do something"

# Environment variable
export BRYNHILD_DANGEROUSLY_SKIP_PERMISSIONS=true
```

⚠️ **Warning**: Auto-approve mode skips ALL permission prompts. Use with caution.

## Built-in Tool Permissions

| Tool | requires_permission | Reason |
|------|---------------------|--------|
| `Bash` | `True` | Executes arbitrary commands |
| `Read` | `False` | Read-only file access |
| `Write` | `True` | Modifies filesystem |
| `Edit` | `True` | Modifies files |
| `Grep` | `False` | Read-only search |
| `Glob` | `False` | Read-only listing |
| `Inspect` | `False` | Read-only inspection |
| `LearnSkill` | `False` | Reads skill files |

## Best Practices

### 1. Default to True

When in doubt, require permission:

```python
@property
def requires_permission(self) -> bool:
    return True  # When in doubt, be safe
```

### 2. Consider Side Effects

Even "harmless" operations may warrant permission:

```python
# This logs to an external service - require permission
@property
def requires_permission(self) -> bool:
    return True  # Network access
```

### 3. Document Your Choice

Add a docstring explaining the permission decision:

```python
@property
def requires_permission(self) -> bool:
    """
    No permission required.
    
    This tool only performs local calculations with no
    side effects, network access, or file modifications.
    """
    return False
```

### 4. Test Both Modes

Test your tool with and without auto-approve:

```python
def test_tool_with_permission():
    """Test that tool respects permission checks."""
    tool = MyTool()
    assert tool.requires_permission == True
    
def test_tool_execution():
    """Test tool execution (assumes permission granted)."""
    tool = MyTool()
    result = await tool.execute({"input": "test"})
    assert result.success
```

## See Also

- [Plugin Tool Interface](plugin-tool-interface.md)
- [Plugin Development Guide](plugin-development-guide.md)
- [Tool Error Handling](tool-error-handling.md)

