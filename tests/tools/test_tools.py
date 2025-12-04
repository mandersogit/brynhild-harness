"""
Tests for the tool system.

These tests verify that tools work correctly in isolation.
"""

import pathlib as _pathlib
import tempfile as _tempfile

import pytest as _pytest

import brynhild.tools as tools

# =============================================================================
# Registry Tests
# =============================================================================


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_create_empty_registry(self) -> None:
        """New registry should be empty."""
        registry = tools.ToolRegistry()
        assert len(registry) == 0
        assert registry.list_names() == []

    def test_register_tool(self) -> None:
        """Should register a tool by name."""
        registry = tools.ToolRegistry()
        bash = tools.BashTool()
        registry.register(bash)

        assert "Bash" in registry
        assert len(registry) == 1
        assert registry.get("Bash") is bash

    def test_register_duplicate_raises(self) -> None:
        """Should raise when registering duplicate tool name."""
        registry = tools.ToolRegistry()
        registry.register(tools.BashTool())

        with _pytest.raises(ValueError, match="already registered"):
            registry.register(tools.BashTool())

    def test_get_nonexistent_returns_none(self) -> None:
        """get() should return None for unknown tool."""
        registry = tools.ToolRegistry()
        assert registry.get("NonExistent") is None

    def test_get_or_raise_raises_for_unknown(self) -> None:
        """get_or_raise() should raise KeyError for unknown tool."""
        registry = tools.ToolRegistry()
        with _pytest.raises(KeyError, match="not found"):
            registry.get_or_raise("NonExistent")

    def test_list_tools_sorted(self) -> None:
        """list_tools() should return tools sorted by name."""
        registry = tools.ToolRegistry()
        registry.register(tools.FileWriteTool())
        registry.register(tools.BashTool())
        registry.register(tools.FileReadTool())

        names = [t.name for t in registry.list_tools()]
        assert names == ["Bash", "Read", "Write"]

    def test_default_registry_has_tools(self) -> None:
        """Default registry should have built-in tools."""
        registry = tools.get_default_registry()
        assert len(registry) >= 6
        assert "Bash" in registry
        assert "Read" in registry
        assert "Write" in registry
        assert "Edit" in registry
        assert "Grep" in registry
        assert "Glob" in registry


# =============================================================================
# Bash Tool Tests
# =============================================================================


class TestBashTool:
    """Tests for BashTool."""

    @_pytest.mark.asyncio
    async def test_simple_command(self) -> None:
        """Should execute a simple command."""
        tool = tools.BashTool()
        result = await tool.execute({"command": "echo hello"})

        assert result.success is True
        assert "hello" in result.output
        assert result.error is None

    @_pytest.mark.asyncio
    async def test_command_with_exit_code(self) -> None:
        """Should report failure for non-zero exit code."""
        tool = tools.BashTool()
        result = await tool.execute({"command": "exit 1"})

        assert result.success is False

    @_pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Should timeout long-running commands."""
        tool = tools.BashTool()
        result = await tool.execute({"command": "sleep 10", "timeout": 100})

        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_empty_command(self) -> None:
        """Should fail for empty command."""
        tool = tools.BashTool()
        result = await tool.execute({"command": ""})

        assert result.success is False
        assert result.error is not None
        assert "no command" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_working_directory(self) -> None:
        """Should run command in working directory."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            tool = tools.BashTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"command": "pwd"})

            assert result.success is True
            assert tmpdir in result.output

    def test_schema(self) -> None:
        """Should have valid input schema."""
        tool = tools.BashTool()
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "command" in schema["required"]


# =============================================================================
# File Read Tool Tests
# =============================================================================


class TestFileReadTool:
    """Tests for FileReadTool."""

    @_pytest.mark.asyncio
    async def test_read_file(self, tmp_path: _pathlib.Path) -> None:
        """Should read file with line numbers."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = tools.FileReadTool(base_dir=tmp_path)
        result = await tool.execute({"file_path": "test.txt"})

        assert result.success is True
        assert "1|line1" in result.output
        assert "2|line2" in result.output
        assert "3|line3" in result.output

    @_pytest.mark.asyncio
    async def test_read_with_offset(self, tmp_path: _pathlib.Path) -> None:
        """Should respect offset parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = tools.FileReadTool(base_dir=tmp_path)
        result = await tool.execute({"file_path": "test.txt", "offset": 1})

        assert result.success is True
        assert "1|line1" not in result.output
        assert "2|line2" in result.output

    @_pytest.mark.asyncio
    async def test_read_with_limit(self, tmp_path: _pathlib.Path) -> None:
        """Should respect limit parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = tools.FileReadTool(base_dir=tmp_path)
        result = await tool.execute({"file_path": "test.txt", "limit": 2})

        assert result.success is True
        assert "1|line1" in result.output
        assert "2|line2" in result.output
        assert "3|line3" not in result.output

    @_pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path: _pathlib.Path) -> None:
        """Should fail for non-existent file."""
        tool = tools.FileReadTool(base_dir=tmp_path)
        result = await tool.execute({"file_path": "nonexistent.txt"})

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()


# =============================================================================
# File Write Tool Tests
# =============================================================================


class TestFileWriteTool:
    """Tests for FileWriteTool."""

    @_pytest.mark.asyncio
    async def test_write_file(self, tmp_path: _pathlib.Path) -> None:
        """Should write content to file."""
        tool = tools.FileWriteTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "content": "hello world",
        })

        assert result.success is True
        assert (tmp_path / "test.txt").read_text() == "hello world"

    @_pytest.mark.asyncio
    async def test_write_creates_directories(self, tmp_path: _pathlib.Path) -> None:
        """Should create parent directories."""
        tool = tools.FileWriteTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "subdir/nested/test.txt",
            "content": "content",
        })

        assert result.success is True
        assert (tmp_path / "subdir/nested/test.txt").exists()

    @_pytest.mark.asyncio
    async def test_write_overwrites(self, tmp_path: _pathlib.Path) -> None:
        """Should overwrite existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        tool = tools.FileWriteTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "content": "replaced",
        })

        assert result.success is True
        assert test_file.read_text() == "replaced"


# =============================================================================
# File Edit Tool Tests
# =============================================================================


class TestFileEditTool:
    """Tests for FileEditTool."""

    @_pytest.mark.asyncio
    async def test_edit_replace(self, tmp_path: _pathlib.Path) -> None:
        """Should replace text in file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        tool = tools.FileEditTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "old_string": "world",
            "new_string": "everyone",
        })

        assert result.success is True
        assert test_file.read_text() == "hello everyone"

    @_pytest.mark.asyncio
    async def test_edit_not_found(self, tmp_path: _pathlib.Path) -> None:
        """Should fail when old_string not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        tool = tools.FileEditTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "old_string": "missing",
            "new_string": "new",
        })

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_edit_requires_unique(self, tmp_path: _pathlib.Path) -> None:
        """Should fail when old_string appears multiple times."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo bar foo")

        tool = tools.FileEditTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "old_string": "foo",
            "new_string": "baz",
        })

        assert result.success is False
        assert result.error is not None
        assert "2 times" in result.error

    @_pytest.mark.asyncio
    async def test_edit_replace_all(self, tmp_path: _pathlib.Path) -> None:
        """Should replace all occurrences with replace_all."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo bar foo")

        tool = tools.FileEditTool(base_dir=tmp_path)
        result = await tool.execute({
            "file_path": "test.txt",
            "old_string": "foo",
            "new_string": "baz",
            "replace_all": True,
        })

        assert result.success is True
        assert test_file.read_text() == "baz bar baz"


# =============================================================================
# Grep Tool Tests
# =============================================================================


class TestGrepTool:
    """Tests for GrepTool."""

    @_pytest.mark.asyncio
    async def test_grep_pattern(self, tmp_path: _pathlib.Path) -> None:
        """Should find pattern in files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        tool = tools.GrepTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "def foo", "path": "."})

        assert result.success is True
        assert "def foo" in result.output

    @_pytest.mark.asyncio
    async def test_grep_no_matches(self, tmp_path: _pathlib.Path) -> None:
        """Should succeed with message when no matches."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        tool = tools.GrepTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "nonexistent"})

        assert result.success is True
        assert "no matches" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_grep_case_insensitive(self, tmp_path: _pathlib.Path) -> None:
        """Should support case-insensitive search."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        tool = tools.GrepTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "hello", "-i": True})

        assert result.success is True
        assert "Hello" in result.output

    def test_grep_limit_parameter_exists(self, tmp_path: _pathlib.Path) -> None:
        """Grep tool should use 'limit' parameter (not 'head_limit') for consistency."""
        tool = tools.GrepTool(base_dir=tmp_path)
        schema = tool.input_schema
        properties = schema.get("properties", {})

        # Should have 'limit', not 'head_limit'
        assert "limit" in properties, "Grep should have 'limit' parameter"
        assert "head_limit" not in properties, "Grep should not use 'head_limit'"


class TestInputValidation:
    """Tests for tool input validation."""

    def test_validate_unknown_params(self, tmp_path: _pathlib.Path) -> None:
        """Unknown parameters should generate warnings."""
        tool = tools.GrepTool(base_dir=tmp_path)

        # 'head_limit' is not a valid param (should be 'limit')
        validation = tool.validate_input({"pattern": "test", "head_limit": 10})

        assert validation.is_valid  # Unknown params are warnings, not errors
        assert validation.has_warnings
        assert "head_limit" in validation.warnings[0]
        assert "Unknown parameters" in validation.warnings[0]

    def test_validate_missing_required(self, tmp_path: _pathlib.Path) -> None:
        """Missing required parameters should generate errors."""
        tool = tools.GrepTool(base_dir=tmp_path)

        # 'pattern' is required
        validation = tool.validate_input({})

        assert not validation.is_valid
        assert "pattern" in validation.errors[0]

    def test_validate_valid_input(self, tmp_path: _pathlib.Path) -> None:
        """Valid input should pass validation."""
        tool = tools.GrepTool(base_dir=tmp_path)

        validation = tool.validate_input({"pattern": "test", "limit": 10})

        assert validation.is_valid
        assert not validation.has_warnings


# =============================================================================
# Glob Tool Tests
# =============================================================================


class TestGlobTool:
    """Tests for GlobTool."""

    @_pytest.mark.asyncio
    async def test_glob_pattern(self, tmp_path: _pathlib.Path) -> None:
        """Should find files matching pattern."""
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")

        tool = tools.GlobTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "*.py"})

        assert result.success is True
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    @_pytest.mark.asyncio
    async def test_glob_recursive(self, tmp_path: _pathlib.Path) -> None:
        """Should find files recursively."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (tmp_path / "a.py").write_text("")
        (subdir / "b.py").write_text("")

        tool = tools.GlobTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "*.py"})

        assert result.success is True
        assert "a.py" in result.output
        assert "b.py" in result.output

    @_pytest.mark.asyncio
    async def test_glob_with_limit(self, tmp_path: _pathlib.Path) -> None:
        """Should respect limit parameter."""
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text("")

        tool = tools.GlobTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "*.txt", "limit": 2})

        assert result.success is True
        lines = result.output.strip().split("\n")
        assert len(lines) == 2

    @_pytest.mark.asyncio
    async def test_glob_no_matches(self, tmp_path: _pathlib.Path) -> None:
        """Should succeed with message when no matches."""
        tool = tools.GlobTool(base_dir=tmp_path)
        result = await tool.execute({"pattern": "*.nonexistent"})

        assert result.success is True
        assert "no files found" in result.output.lower()

