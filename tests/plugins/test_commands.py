"""
Tests for plugin command parsing.

Tests verify that:
- Command markdown files are parsed correctly
- Frontmatter validation works
- Template variables are substituted
- Aliases are registered
"""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.plugins.commands as commands


class TestCommandFrontmatter:
    """Tests for CommandFrontmatter pydantic model."""

    def test_minimal_frontmatter_requires_name(self) -> None:
        """Name is the only required field."""
        fm = commands.CommandFrontmatter(name="build")
        assert fm.name == "build"
        assert fm.description == ""
        assert fm.aliases == []
        assert fm.args == ""

    def test_full_frontmatter_preserves_all_fields(self) -> None:
        """All fields are preserved when provided."""
        fm = commands.CommandFrontmatter(
            name="deploy",
            description="Deploy the application",
            aliases=["d", "push"],
            args="<environment>",
        )
        assert fm.name == "deploy"
        assert fm.description == "Deploy the application"
        assert fm.aliases == ["d", "push"]
        assert fm.args == "<environment>"

    def test_name_length_limits(self) -> None:
        """Name must be 1-64 characters."""
        # Empty not allowed
        with _pytest.raises(ValueError, match="at least 1"):
            commands.CommandFrontmatter(name="")

        # Max allowed
        commands.CommandFrontmatter(name="a" * 64)

        # Over max
        with _pytest.raises(ValueError, match="at most 64"):
            commands.CommandFrontmatter(name="a" * 65)

    def test_extra_fields_rejected(self) -> None:
        """Unknown fields are rejected."""
        with _pytest.raises(ValueError, match="Extra inputs"):
            commands.CommandFrontmatter(name="test", unknown="value")


class TestParseCommandMarkdown:
    """Tests for parse_command_markdown function."""

    def test_parses_valid_markdown(self) -> None:
        """Valid markdown with frontmatter parses correctly."""
        content = """---
name: build
description: Build the project
---

# Build Command

This command builds the project.

Arguments: {{args}}
"""
        fm, body = commands.parse_command_markdown(content)
        assert fm.name == "build"
        assert fm.description == "Build the project"
        assert "# Build Command" in body
        assert "{{args}}" in body

    def test_missing_frontmatter_raises_error(self) -> None:
        """Missing frontmatter raises ValueError."""
        content = "# No frontmatter here"
        with _pytest.raises(ValueError, match="must have YAML frontmatter"):
            commands.parse_command_markdown(content)

    def test_empty_frontmatter_raises_error(self) -> None:
        """Empty frontmatter (missing name) raises ValueError."""
        content = """---
description: No name field
---

# Empty frontmatter
"""
        with _pytest.raises(ValueError, match="Invalid command frontmatter"):
            commands.parse_command_markdown(content)

    def test_invalid_yaml_raises_error(self) -> None:
        """Invalid YAML in frontmatter raises ValueError."""
        content = """---
name: [invalid yaml {{
---

Body
"""
        with _pytest.raises(ValueError, match="Invalid YAML"):
            commands.parse_command_markdown(content)


class TestCommand:
    """Tests for Command dataclass."""

    def _make_command(
        self,
        name: str = "test",
        body: str = "Test body",
        path: _pathlib.Path | None = None,
    ) -> commands.Command:
        """Helper to create a Command."""
        fm = commands.CommandFrontmatter(name=name)
        return commands.Command(
            frontmatter=fm,
            body=body,
            path=path or _pathlib.Path("/fake/path.md"),
        )

    def test_properties_expose_frontmatter(self) -> None:
        """Properties delegate to frontmatter."""
        fm = commands.CommandFrontmatter(
            name="build",
            description="Build it",
            aliases=["b"],
        )
        cmd = commands.Command(
            frontmatter=fm,
            body="body",
            path=_pathlib.Path("/test.md"),
        )
        assert cmd.name == "build"
        assert cmd.description == "Build it"
        assert cmd.aliases == ["b"]

    def test_render_substitutes_args(self) -> None:
        """{{args}} is replaced with provided args."""
        cmd = self._make_command(body="Run with: {{args}}")
        result = cmd.render(args="--verbose")
        assert result == "Run with: --verbose"

    def test_render_substitutes_cwd(self) -> None:
        """{{cwd}} is replaced with current directory."""
        cmd = self._make_command(body="Dir: {{cwd}}")
        result = cmd.render()
        assert _pathlib.Path.cwd().name in result

    def test_render_substitutes_custom_context(self) -> None:
        """Custom context variables are substituted."""
        cmd = self._make_command(body="File: {{file}}, Branch: {{git_branch}}")
        result = cmd.render(file="/src/main.py", git_branch="main")
        assert result == "File: /src/main.py, Branch: main"

    def test_render_substitutes_env_vars(self) -> None:
        """{{env.VAR}} is replaced with environment variable."""
        cmd = self._make_command(body="User: {{env.TEST_USER}}")
        with _mock.patch.dict(_os.environ, {"TEST_USER": "alice"}):
            result = cmd.render()
        assert result == "User: alice"

    def test_render_missing_env_var_becomes_empty(self) -> None:
        """Missing env vars are replaced with empty string."""
        cmd = self._make_command(body="Value: {{env.NONEXISTENT_VAR_XYZ}}")
        result = cmd.render()
        assert result == "Value: "

    def test_to_dict_serializes_all_fields(self) -> None:
        """to_dict includes all relevant fields."""
        fm = commands.CommandFrontmatter(
            name="test",
            description="Test cmd",
            aliases=["t"],
            args="<file>",
        )
        cmd = commands.Command(
            frontmatter=fm,
            body="body",
            path=_pathlib.Path("/test.md"),
            plugin_name="my-plugin",
        )
        d = cmd.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "Test cmd"
        assert d["aliases"] == ["t"]
        assert d["args"] == "<file>"
        assert d["path"] == "/test.md"
        assert d["plugin_name"] == "my-plugin"


class TestLoadCommand:
    """Tests for load_command function."""

    def test_loads_valid_file(self, tmp_path: _pathlib.Path) -> None:
        """Valid command file loads correctly."""
        cmd_file = tmp_path / "build.md"
        cmd_file.write_text("""---
name: build
description: Build the project
---

Build command body
""")
        cmd = commands.load_command(cmd_file, plugin_name="test-plugin")
        assert cmd.name == "build"
        assert cmd.description == "Build the project"
        assert "Build command body" in cmd.body
        assert cmd.plugin_name == "test-plugin"

    def test_missing_file_raises_error(self, tmp_path: _pathlib.Path) -> None:
        """Missing file raises FileNotFoundError."""
        with _pytest.raises(FileNotFoundError):
            commands.load_command(tmp_path / "nonexistent.md")


class TestCommandLoader:
    """Tests for CommandLoader class."""

    def _create_command_file(
        self,
        path: _pathlib.Path,
        name: str,
        aliases: list[str] | None = None,
    ) -> None:
        """Helper to create a command file."""
        aliases_yaml = f"aliases: {aliases}" if aliases else ""
        path.write_text(f"""---
name: {name}
{aliases_yaml}
---

{name} command body
""")

    def test_loads_commands_from_directory(self, tmp_path: _pathlib.Path) -> None:
        """Commands are loaded from directory."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        self._create_command_file(commands_dir / "build.md", "build")
        self._create_command_file(commands_dir / "deploy.md", "deploy")

        loader = commands.CommandLoader()
        cmds = loader.load_from_directory(commands_dir, "test-plugin")

        assert len(cmds) == 2
        assert "build" in cmds
        assert "deploy" in cmds
        assert cmds["build"].name == "build"

    def test_registers_aliases(self, tmp_path: _pathlib.Path) -> None:
        """Aliases are registered as separate entries."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        self._create_command_file(
            commands_dir / "build.md", "build", aliases=["b", "make"]
        )

        loader = commands.CommandLoader()
        cmds = loader.load_from_directory(commands_dir)

        assert len(cmds) == 3  # build, b, make
        assert cmds["build"] is cmds["b"]  # Same Command instance
        assert cmds["build"] is cmds["make"]

    def test_skips_invalid_files(self, tmp_path: _pathlib.Path) -> None:
        """Invalid command files are skipped."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        self._create_command_file(commands_dir / "valid.md", "valid")
        (commands_dir / "invalid.md").write_text("no frontmatter")

        loader = commands.CommandLoader()
        cmds = loader.load_from_directory(commands_dir)

        assert len(cmds) == 1
        assert "valid" in cmds

    def test_load_from_plugin(self, tmp_path: _pathlib.Path) -> None:
        """load_from_plugin uses commands/ subdirectory."""
        plugin_dir = tmp_path / "my-plugin"
        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir(parents=True)
        self._create_command_file(commands_dir / "test.md", "test")

        loader = commands.CommandLoader()
        cmds = loader.load_from_plugin(plugin_dir, "my-plugin")

        assert "test" in cmds
        assert cmds["test"].plugin_name == "my-plugin"

    def test_nonexistent_directory_returns_empty(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Non-existent commands/ directory returns empty dict."""
        loader = commands.CommandLoader()
        cmds = loader.load_from_directory(tmp_path / "nonexistent")
        assert cmds == {}

