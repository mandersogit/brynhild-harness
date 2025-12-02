# Tool Error Handling

This guide covers best practices for handling errors in Brynhild plugin tools.

## The ToolResult Class

All tools return a `ToolResult` object with three fields:

```python
@dataclass
class ToolResult:
    success: bool       # Whether the operation succeeded
    output: str         # The tool's output (shown to the LLM)
    error: str | None   # Error message if success=False
```

## Error Handling Patterns

### Pattern 1: Validation Errors

Return a `ToolResult` with `success=False` for input validation failures:

```python
async def execute(self, input: dict) -> ToolResult:
    path = input.get("path", "")
    
    # Validate required fields
    if not path:
        return ToolResult(
            success=False,
            output="",
            error="path is required",
        )
    
    # Validate field format
    if not path.startswith("/"):
        return ToolResult(
            success=False,
            output="",
            error="path must be absolute (start with /)",
        )
    
    # Continue with operation...
```

### Pattern 2: Expected Errors

Catch and convert expected errors to `ToolResult`:

```python
async def execute(self, input: dict) -> ToolResult:
    url = input.get("url", "")
    
    try:
        response = await fetch(url)
        return ToolResult(
            success=True,
            output=f"Status: {response.status}\n{response.body}",
        )
    except ConnectionError as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Failed to connect: {e}",
        )
    except TimeoutError:
        return ToolResult(
            success=False,
            output="",
            error="Request timed out",
        )
```

### Pattern 3: Unexpected Errors

Let unexpected errors bubble up to the framework:

```python
async def execute(self, input: dict) -> ToolResult:
    # DON'T do this:
    try:
        result = do_something()
        return ToolResult(success=True, output=result)
    except Exception as e:  # Too broad!
        return ToolResult(success=False, output="", error=str(e))
    
    # DO this instead:
    try:
        result = do_something()
        return ToolResult(success=True, output=result)
    except ValueError as e:
        # Expected error - handle it
        return ToolResult(success=False, output="", error=f"Invalid value: {e}")
    # Unexpected errors will raise and be handled by the framework
```

### Pattern 4: Partial Success

Sometimes an operation partially succeeds. Include both output and error:

```python
async def execute(self, input: dict) -> ToolResult:
    files = input.get("files", [])
    results = []
    errors = []
    
    for file in files:
        try:
            content = read_file(file)
            results.append(f"{file}: {len(content)} bytes")
        except FileNotFoundError:
            errors.append(f"{file}: not found")
    
    output = "\n".join(results)
    error = "\n".join(errors) if errors else None
    
    return ToolResult(
        success=len(errors) == 0,
        output=output,
        error=error,
    )
```

## Using the _require_input Helper

The base `Tool` class provides a helper for required field validation:

```python
async def execute(self, input: dict) -> ToolResult:
    # Returns string value or ToolResult error
    path_or_error = self._require_input(input, "path")
    if isinstance(path_or_error, ToolResult):
        return path_or_error
    path = path_or_error
    
    # Can also provide a custom label for error messages
    cmd_or_error = self._require_input(input, "command", label="shell command")
    if isinstance(cmd_or_error, ToolResult):
        return cmd_or_error
    command = cmd_or_error
    
    # Continue with operation...
```

## Error Message Guidelines

### Be Specific

```python
# Bad
error="Error"
error="Something went wrong"

# Good
error="File not found: /path/to/file.txt"
error="API returned status 403: Forbidden"
```

### Include Context

```python
# Bad
error="Permission denied"

# Good
error="Permission denied writing to /etc/passwd (not allowed by sandbox)"
```

### Suggest Solutions

```python
# Bad
error="Invalid format"

# Good
error="Invalid date format. Expected YYYY-MM-DD, got '12/25/2023'"
```

### Don't Expose Sensitive Data

```python
# Bad
error=f"Authentication failed with API key: {api_key}"

# Good
error="Authentication failed. Check your API key in BRYNHILD_API_KEY"
```

## How Errors Are Presented

When a tool returns `success=False`:

1. The error is logged
2. The LLM receives the error message
3. The LLM can decide to:
   - Retry with different input
   - Report the error to the user
   - Try a different approach

Example LLM behavior:

```
User: Delete /etc/passwd
Assistant: I'll try to delete that file.
[Tool: Write, path=/etc/passwd] → Error: Permission denied (blocked by sandbox)
Assistant: I cannot delete /etc/passwd. It's a protected system file and the sandbox blocks write access to system directories.
```

## Error Categories

### Validation Errors

- Missing required fields
- Invalid field format
- Out-of-range values

**Action**: Return `ToolResult(success=False, ...)` immediately.

### Operational Errors

- File not found
- Network timeout
- API rate limit

**Action**: Return `ToolResult(success=False, ...)` with specific error.

### Permission Errors

- Sandbox blocking access
- Authentication required

**Action**: Return `ToolResult(success=False, ...)` with guidance.

### System Errors

- Out of memory
- Disk full
- Unexpected crashes

**Action**: Let these raise. The framework will handle them.

## Complete Example

```python
async def execute(self, input: dict) -> ToolResult:
    """Execute an API call."""
    # 1. Validate required inputs
    url_or_error = self._require_input(input, "url")
    if isinstance(url_or_error, ToolResult):
        return url_or_error
    url = url_or_error
    
    # 2. Validate format
    if not url.startswith(("http://", "https://")):
        return ToolResult(
            success=False,
            output="",
            error=f"Invalid URL: must start with http:// or https://",
        )
    
    # 3. Handle expected errors
    try:
        response = await self._client.get(url, timeout=30)
    except httpx.TimeoutException:
        return ToolResult(
            success=False,
            output="",
            error=f"Request timed out after 30 seconds",
        )
    except httpx.ConnectError as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Connection failed: {e}",
        )
    
    # 4. Handle response errors
    if response.status_code >= 400:
        return ToolResult(
            success=False,
            output="",
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )
    
    # 5. Success!
    return ToolResult(
        success=True,
        output=f"Status: {response.status_code}\n\n{response.text}",
    )
```

## See Also

- [Plugin Tool Interface](plugin-tool-interface.md)
- [Plugin Development Guide](plugin-development-guide.md)
- [Tool Testing](tool-testing.md)

