"""Tests for tools/inspect.py."""

import pathlib as _pathlib
import tempfile as _tempfile

import pytest as _pytest

import brynhild.tools.inspect as inspect_tool


class TestInspectTool:
    """Tests for InspectTool."""

    def test_name(self) -> None:
        """Tool has correct name."""
        tool = inspect_tool.InspectTool()
        assert tool.name == "Inspect"

    def test_description(self) -> None:
        """Tool has meaningful description."""
        tool = inspect_tool.InspectTool()
        assert "filesystem" in tool.description.lower()
        assert "cwd" in tool.description
        assert "ls" in tool.description

    def test_requires_permission_false(self) -> None:
        """Inspect does not require permission."""
        tool = inspect_tool.InspectTool()
        assert tool.requires_permission is False

    def test_input_schema(self) -> None:
        """Schema defines expected operations."""
        tool = inspect_tool.InspectTool()
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]
        ops = schema["properties"]["operation"]["enum"]
        assert "cwd" in ops
        assert "ls" in ops
        assert "stat" in ops
        assert "exists" in ops

    @_pytest.mark.asyncio
    async def test_cwd_operation(self) -> None:
        """cwd returns current working directory."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"operation": "cwd"})

            assert result.success is True
            assert tmpdir in result.output

    @_pytest.mark.asyncio
    async def test_ls_operation(self) -> None:
        """ls lists directory contents."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            (_pathlib.Path(tmpdir) / "file1.txt").write_text("hello")
            (_pathlib.Path(tmpdir) / "file2.txt").write_text("world")
            (_pathlib.Path(tmpdir) / "subdir").mkdir()

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"operation": "ls", "path": "."})

            assert result.success is True
            assert "file1.txt" in result.output
            assert "file2.txt" in result.output
            assert "subdir" in result.output

    @_pytest.mark.asyncio
    async def test_ls_sort_by_mtime(self) -> None:
        """ls can sort by mtime."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            import time as _time

            # Create files with different mtimes
            f1 = _pathlib.Path(tmpdir) / "old.txt"
            f1.write_text("old")
            _time.sleep(0.1)
            f2 = _pathlib.Path(tmpdir) / "new.txt"
            f2.write_text("new")

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute(
                {
                    "operation": "ls",
                    "path": ".",
                    "sort_by": "mtime",
                    "filter": "files",
                }
            )

            assert result.success is True
            # old.txt should appear before new.txt (oldest first by default)
            old_pos = result.output.find("old.txt")
            new_pos = result.output.find("new.txt")
            assert old_pos < new_pos

    @_pytest.mark.asyncio
    async def test_ls_filter_files(self) -> None:
        """ls can filter to files only."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            (_pathlib.Path(tmpdir) / "file.txt").write_text("hello")
            (_pathlib.Path(tmpdir) / "subdir").mkdir()

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute(
                {
                    "operation": "ls",
                    "path": ".",
                    "filter": "files",
                }
            )

            assert result.success is True
            assert "file.txt" in result.output
            assert "subdir" not in result.output

    @_pytest.mark.asyncio
    async def test_ls_filter_dirs(self) -> None:
        """ls can filter to directories only."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            (_pathlib.Path(tmpdir) / "file.txt").write_text("hello")
            (_pathlib.Path(tmpdir) / "subdir").mkdir()

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute(
                {
                    "operation": "ls",
                    "path": ".",
                    "filter": "dirs",
                }
            )

            assert result.success is True
            assert "file.txt" not in result.output
            assert "subdir" in result.output

    @_pytest.mark.asyncio
    async def test_ls_limit(self) -> None:
        """ls respects limit parameter."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                (_pathlib.Path(tmpdir) / f"file{i}.txt").write_text(f"content{i}")

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute(
                {
                    "operation": "ls",
                    "path": ".",
                    "limit": 3,
                }
            )

            assert result.success is True
            # Count file entries (look for the file icon)
            file_count = result.output.count("📄")
            assert file_count == 3

    @_pytest.mark.asyncio
    async def test_stat_operation(self) -> None:
        """stat returns file metadata."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            test_file = _pathlib.Path(tmpdir) / "test.txt"
            test_file.write_text("hello world")

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"operation": "stat", "path": "test.txt"})

            assert result.success is True
            assert "test.txt" in result.output
            assert "file" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_exists_operation_file_exists(self) -> None:
        """exists returns true for existing file."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            test_file = _pathlib.Path(tmpdir) / "exists.txt"
            test_file.write_text("hello")

            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"operation": "exists", "path": "exists.txt"})

            assert result.success is True
            assert "exists.txt" in result.output
            assert "file" in result.output.lower()

    @_pytest.mark.asyncio
    async def test_exists_operation_file_not_exists(self) -> None:
        """exists returns false for non-existing file."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            tool = inspect_tool.InspectTool(working_dir=_pathlib.Path(tmpdir))
            result = await tool.execute({"operation": "exists", "path": "nonexistent.txt"})

            assert result.success is True
            assert "does not exist" in result.output

    @_pytest.mark.asyncio
    async def test_unknown_operation(self) -> None:
        """Unknown operation returns error."""
        tool = inspect_tool.InspectTool()
        result = await tool.execute({"operation": "invalid"})

        assert result.success is False
        assert "Unknown operation" in (result.error or "")
