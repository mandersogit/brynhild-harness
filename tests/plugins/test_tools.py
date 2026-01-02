"""
Tests for plugin tool loading.

Tests verify that:
- Tool modules are loaded dynamically
- Tool classes are discovered correctly
- Invalid tools are handled gracefully
"""

import pathlib as _pathlib

import brynhild.plugins.tools as tools


class TestLoadToolModule:
    """Tests for load_tool_module function."""

    def test_loads_valid_module(self, tmp_path: _pathlib.Path) -> None:
        """Valid Python module is loaded."""
        tool_file = tmp_path / "my_tool.py"
        tool_file.write_text("""
class Tool:
    name = "my_tool"
    description = "A test tool"

    def execute(self, **kwargs):
        return {"output": "done"}
""")
        module = tools.load_tool_module(tool_file, "test-plugin")
        assert hasattr(module, "Tool")
        assert module.Tool.name == "my_tool"

    def test_missing_file_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Missing file raises ToolLoadError."""
        try:
            tools.load_tool_module(tmp_path / "nonexistent.py", "test")
        except tools.ToolLoadError as e:
            assert "not found" in str(e)
        else:
            raise AssertionError("Expected ToolLoadError")

    def test_non_py_file_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Non-.py file raises ToolLoadError."""
        txt_file = tmp_path / "tool.txt"
        txt_file.write_text("not python")
        try:
            tools.load_tool_module(txt_file, "test")
        except tools.ToolLoadError as e:
            assert ".py" in str(e)
        else:
            raise AssertionError("Expected ToolLoadError")

    def test_syntax_error_raises_tool_load_error(self, tmp_path: _pathlib.Path) -> None:
        """Python syntax error raises ToolLoadError."""
        tool_file = tmp_path / "bad_syntax.py"
        tool_file.write_text("def broken(:\n    pass")
        try:
            tools.load_tool_module(tool_file, "test")
        except tools.ToolLoadError as e:
            assert "Failed to load" in str(e)
        else:
            raise AssertionError("Expected ToolLoadError")


class TestGetToolClassFromModule:
    """Tests for get_tool_class_from_module function."""

    def test_finds_tool_class(self, tmp_path: _pathlib.Path) -> None:
        """Finds class named 'Tool'."""
        tool_file = tmp_path / "my_tool.py"
        tool_file.write_text("""
class Tool:
    name = "my_tool"
    def execute(self): pass
""")
        module = tools.load_tool_module(tool_file, "test")
        tool_cls = tools.get_tool_class_from_module(module)
        assert tool_cls is not None
        assert tool_cls.name == "my_tool"

    def test_finds_by_name_attribute(self, tmp_path: _pathlib.Path) -> None:
        """Finds class with matching 'name' attribute."""
        tool_file = tmp_path / "custom.py"
        tool_file.write_text("""
class MyCustomTool:
    name = "custom_tool"
    def execute(self): pass
""")
        module = tools.load_tool_module(tool_file, "test")
        tool_cls = tools.get_tool_class_from_module(module, expected_name="custom_tool")
        assert tool_cls is not None
        assert tool_cls.name == "custom_tool"

    def test_returns_none_for_no_tool(self, tmp_path: _pathlib.Path) -> None:
        """Returns None if no tool class found."""
        tool_file = tmp_path / "empty.py"
        tool_file.write_text("""
# No tool class here
x = 42
""")
        module = tools.load_tool_module(tool_file, "test")
        tool_cls = tools.get_tool_class_from_module(module)
        assert tool_cls is None

    def test_skips_private_classes(self, tmp_path: _pathlib.Path) -> None:
        """Private classes (starting with _) are skipped."""
        tool_file = tmp_path / "private.py"
        tool_file.write_text("""
class _PrivateTool:
    name = "private"
    def execute(self): pass
""")
        module = tools.load_tool_module(tool_file, "test")
        tool_cls = tools.get_tool_class_from_module(module, expected_name="private")
        assert tool_cls is None


class TestIsToolClass:
    """Tests for _is_tool_class function."""

    def test_requires_name_and_execute(self) -> None:
        """Tool class must have name attribute and execute method."""

        class ValidTool:
            name = "test"

            def execute(self) -> None:
                pass

        class NoName:
            def execute(self) -> None:
                pass

        class NoExecute:
            name = "test"

        assert tools._is_tool_class(ValidTool) is True
        assert tools._is_tool_class(NoName) is False
        assert tools._is_tool_class(NoExecute) is False

    def test_accepts_run_instead_of_execute(self) -> None:
        """run() method is also accepted."""

        class ToolWithRun:
            name = "test"

            def run(self) -> None:
                pass

        assert tools._is_tool_class(ToolWithRun) is True

    def test_rejects_non_classes(self) -> None:
        """Non-class objects are rejected."""
        assert tools._is_tool_class("not a class") is False
        assert tools._is_tool_class(42) is False
        assert tools._is_tool_class(None) is False


class TestToolLoader:
    """Tests for ToolLoader class."""

    def _create_tool_file(
        self, path: _pathlib.Path, name: str, tool_name: str | None = None
    ) -> None:
        """Helper to create a tool file."""
        tool_name = tool_name or name
        path.write_text(f"""
class Tool:
    name = "{tool_name}"
    description = "A {tool_name} tool"

    def execute(self, **kwargs):
        return {{"output": "{tool_name}"}}
""")

    def test_loads_tools_from_directory(self, tmp_path: _pathlib.Path) -> None:
        """Tools are loaded from directory."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        self._create_tool_file(tools_dir / "tool_a.py", "tool_a")
        self._create_tool_file(tools_dir / "tool_b.py", "tool_b")

        loader = tools.ToolLoader()
        loaded = loader.load_from_directory(tools_dir, "test-plugin")

        assert len(loaded) == 2
        assert "tool_a" in loaded
        assert "tool_b" in loaded

    def test_skips_init_files(self, tmp_path: _pathlib.Path) -> None:
        """__init__.py and private modules are skipped."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        self._create_tool_file(tools_dir / "valid.py", "valid")
        (tools_dir / "__init__.py").write_text("")
        (tools_dir / "_private.py").write_text("x = 1")

        loader = tools.ToolLoader()
        loaded = loader.load_from_directory(tools_dir)

        assert len(loaded) == 1
        assert "valid" in loaded

    def test_skips_invalid_modules(self, tmp_path: _pathlib.Path) -> None:
        """Invalid Python modules are skipped."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        self._create_tool_file(tools_dir / "valid.py", "valid")
        (tools_dir / "invalid.py").write_text("syntax error {{{{")

        loader = tools.ToolLoader()
        loaded = loader.load_from_directory(tools_dir)

        assert len(loaded) == 1
        assert "valid" in loaded

    def test_load_from_plugin(self, tmp_path: _pathlib.Path) -> None:
        """load_from_plugin uses tools/ subdirectory."""
        plugin_dir = tmp_path / "my-plugin"
        tools_dir = plugin_dir / "tools"
        tools_dir.mkdir(parents=True)
        self._create_tool_file(tools_dir / "my_tool.py", "my_tool")

        loader = tools.ToolLoader()
        loaded = loader.load_from_plugin(plugin_dir, "my-plugin")

        assert "my_tool" in loaded

    def test_nonexistent_directory_returns_empty(self, tmp_path: _pathlib.Path) -> None:
        """Non-existent tools/ directory returns empty dict."""
        loader = tools.ToolLoader()
        loaded = loader.load_from_directory(tmp_path / "nonexistent")
        assert loaded == {}

    def test_tracks_loaded_tools(self, tmp_path: _pathlib.Path) -> None:
        """get_loaded_tools returns all tools loaded."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        self._create_tool_file(tools_dir / "tool_a.py", "tool_a")

        loader = tools.ToolLoader()
        loader.load_from_directory(tools_dir)

        loaded = loader.get_loaded_tools()
        assert "tool_a" in loaded
