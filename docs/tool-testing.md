# Tool Testing Guide

This guide covers strategies for testing Brynhild plugin tools.

## Testing Approaches

There are two main approaches:

1. **Standalone Testing** - Test your tool without Brynhild installed
2. **Integration Testing** - Test your tool within the full Brynhild system

## Standalone Testing

### The Try/Except Import Pattern

Use this pattern to enable standalone testing:

```python
# my_tool.py
from __future__ import annotations
import typing as _typing

try:
    import brynhild.tools.base as _base
    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    # Stubs for standalone testing
    import dataclasses as _dataclasses

    @_dataclasses.dataclass
    class ToolResult:  # type: ignore[no-redef]
        success: bool
        output: str
        error: str | None = None

    class ToolBase:  # type: ignore[no-redef]
        pass


class Tool(ToolBase):
    # Your implementation...
```

### Writing Standalone Tests

```python
# test_my_tool.py
import asyncio
import pytest
from tools.my_tool import Tool, ToolResult

class TestMyTool:
    """Tests for MyTool."""

    def test_name_and_description(self):
        """Tool has correct metadata."""
        tool = Tool()
        assert tool.name == "my_tool"
        assert "description" in tool.description.lower()

    def test_input_schema_valid(self):
        """Input schema is valid JSON Schema."""
        tool = Tool()
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Tool executes successfully with valid input."""
        tool = Tool()
        result = await tool.execute({"input": "hello"})
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_missing_input(self):
        """Tool returns error for missing required input."""
        tool = Tool()
        result = await tool.execute({})
        assert result.success is False
        assert result.error is not None
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_input(self):
        """Tool returns error for invalid input."""
        tool = Tool()
        result = await tool.execute({"input": ""})
        assert result.success is False
```

### Running Standalone Tests

```bash
# From your plugin directory
cd my-plugin
pytest tests/ -v
```

## Integration Testing

### Setting Up Integration Tests

```python
# test_integration.py
import pathlib
import pytest
import brynhild.plugins.tools as tools
import brynhild.plugins.manifest as manifest

PLUGIN_PATH = pathlib.Path(__file__).parent.parent

class TestMyToolIntegration:
    """Integration tests with Brynhild."""

    def test_tool_loads_via_loader(self):
        """Tool loads correctly via ToolLoader."""
        loader = tools.ToolLoader()
        loaded = loader.load_from_plugin(PLUGIN_PATH, "my-plugin")
        
        assert "my_tool" in loaded
        tool_cls = loaded["my_tool"]
        
        # Instantiate and check
        tool = tool_cls()
        assert tool.name == "my_tool"

    def test_tool_appears_in_registry(self):
        """Tool is registered when plugin is enabled."""
        import brynhild.tools.registry as registry
        import brynhild.config as config
        
        settings = config.Settings.construct_without_dotenv(
            plugin_paths=str(PLUGIN_PATH.parent),
            enabled_plugins="my-plugin",
        )
        
        tool_registry = registry.build_registry_from_settings(settings)
        tool = tool_registry.get("my_tool")
        
        assert tool is not None
        assert tool.name == "my_tool"

    @pytest.mark.asyncio
    async def test_tool_executes_via_registry(self):
        """Tool executes correctly when loaded via registry."""
        import brynhild.tools.registry as registry
        import brynhild.config as config
        
        settings = config.Settings.construct_without_dotenv(
            plugin_paths=str(PLUGIN_PATH.parent),
            enabled_plugins="my-plugin",
        )
        
        tool_registry = registry.build_registry_from_settings(settings)
        tool = tool_registry.get("my_tool")
        
        result = await tool.execute({"input": "test"})
        assert result.success is True
```

### Testing with Mock LLM

```python
# test_with_llm.py
import pytest
from unittest import mock
import brynhild.core.conversation as conversation

@pytest.mark.asyncio
async def test_llm_uses_tool():
    """LLM correctly uses the tool when appropriate."""
    # Mock provider that returns a tool call
    mock_provider = mock.MagicMock()
    mock_provider.complete.return_value = mock.MagicMock(
        content="",
        tool_uses=[
            mock.MagicMock(
                id="tool_1",
                name="my_tool",
                input={"input": "test"},
            )
        ],
    )
    
    # Set up registry with your tool
    # ... (registry setup)
    
    # Run conversation and verify tool was called
    # ... (conversation processing)
```

## Testing Error Conditions

### Test Input Validation

```python
@pytest.mark.asyncio
async def test_missing_required_field(self):
    """Tool handles missing required field."""
    tool = Tool()
    result = await tool.execute({})
    
    assert result.success is False
    assert result.error is not None

@pytest.mark.asyncio
async def test_invalid_field_type(self):
    """Tool handles wrong field type."""
    tool = Tool()
    result = await tool.execute({"count": "not-a-number"})
    
    assert result.success is False
    assert "invalid" in result.error.lower()
```

### Test Error Messages

```python
@pytest.mark.asyncio
async def test_error_message_is_helpful(self):
    """Error messages provide useful guidance."""
    tool = Tool()
    result = await tool.execute({"url": "invalid"})
    
    assert result.success is False
    # Error should mention what's wrong
    assert "url" in result.error.lower()
    # Error should mention expected format
    assert "http" in result.error.lower()
```

### Test Edge Cases

```python
@pytest.mark.asyncio
async def test_empty_string_input(self):
    """Tool handles empty string input."""
    tool = Tool()
    result = await tool.execute({"input": ""})
    assert result.success is False

@pytest.mark.asyncio
async def test_very_long_input(self):
    """Tool handles very long input."""
    tool = Tool()
    long_input = "x" * 100000
    result = await tool.execute({"input": long_input})
    # Should either succeed or fail gracefully
    assert isinstance(result.success, bool)

@pytest.mark.asyncio
async def test_unicode_input(self):
    """Tool handles unicode input."""
    tool = Tool()
    result = await tool.execute({"input": "Hello 世界 🌍"})
    assert result.success is True
```

## Testing Async Behavior

### Test Concurrent Execution

```python
@pytest.mark.asyncio
async def test_concurrent_execution(self):
    """Tool handles concurrent execution."""
    tool = Tool()
    
    # Run multiple executions concurrently
    results = await asyncio.gather(
        tool.execute({"input": "one"}),
        tool.execute({"input": "two"}),
        tool.execute({"input": "three"}),
    )
    
    # All should succeed independently
    for result in results:
        assert result.success is True
```

### Test Timeout Handling

```python
@pytest.mark.asyncio
async def test_timeout_handling(self):
    """Tool handles timeouts gracefully."""
    tool = Tool()
    
    # Mock a slow operation
    with mock.patch.object(tool, "_slow_operation") as mock_op:
        mock_op.side_effect = asyncio.TimeoutError()
        
        result = await tool.execute({"input": "test"})
        
        assert result.success is False
        assert "timeout" in result.error.lower()
```

## Test Fixtures

### Create Reusable Fixtures

```python
# conftest.py
import pytest
import pathlib

@pytest.fixture
def tool():
    """Create a Tool instance."""
    from tools.my_tool import Tool
    return Tool()

@pytest.fixture
def valid_input():
    """Valid input for the tool."""
    return {"input": "hello", "count": 5}

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory with test files."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")
    return tmp_path
```

### Use Fixtures in Tests

```python
@pytest.mark.asyncio
async def test_with_fixtures(self, tool, valid_input):
    """Use fixtures for cleaner tests."""
    result = await tool.execute(valid_input)
    assert result.success is True
```

## Test Organization

### Recommended Structure

```
my-plugin/
├── tools/
│   └── my_tool.py
├── tests/
│   ├── conftest.py           # Shared fixtures
│   ├── test_my_tool.py       # Standalone tests
│   └── test_integration.py   # Integration tests
└── pytest.ini                # pytest configuration
```

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

## Coverage

### Check Test Coverage

```bash
pytest tests/ --cov=tools --cov-report=html
open htmlcov/index.html
```

### Aim for High Coverage

Focus on covering:
- All code paths in `execute()`
- All validation branches
- All error handling paths
- Edge cases and boundary conditions

## See Also

- [Plugin Tool Interface](plugin-tool-interface.md)
- [Tool Error Handling](tool-error-handling.md)
- [Plugin Development Guide](plugin-development-guide.md)

