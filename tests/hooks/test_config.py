"""Tests for hook configuration loading."""

import pathlib as _pathlib
import textwrap as _textwrap

import pytest as _pytest

import brynhild.hooks.config as config
import brynhild.hooks.events as events


class TestHookDefinition:
    """Tests for HookDefinition model."""

    def test_command_hook_valid(self) -> None:
        """Valid command hook definition."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo hello",
        )
        assert hook.name == "test-hook"
        assert hook.type == "command"
        assert hook.command == "echo hello"

    def test_command_hook_requires_command(self) -> None:
        """Command hook must have command field."""
        with _pytest.raises(ValueError, match="command hooks must specify"):
            config.HookDefinition(
                name="test-hook",
                type="command",
            )

    def test_script_hook_valid(self) -> None:
        """Valid script hook definition."""
        hook = config.HookDefinition(
            name="test-hook",
            type="script",
            script="hooks/my_hook.py",
        )
        assert hook.script == "hooks/my_hook.py"

    def test_script_hook_requires_script(self) -> None:
        """Script hook must have script field."""
        with _pytest.raises(ValueError, match="script hooks must specify"):
            config.HookDefinition(
                name="test-hook",
                type="script",
            )

    def test_prompt_hook_valid(self) -> None:
        """Valid prompt hook definition."""
        hook = config.HookDefinition(
            name="test-hook",
            type="prompt",
            prompt="Is this safe? {{tool_input.command}}",
        )
        assert hook.prompt == "Is this safe? {{tool_input.command}}"

    def test_prompt_hook_requires_prompt(self) -> None:
        """Prompt hook must have prompt field."""
        with _pytest.raises(ValueError, match="prompt hooks must specify"):
            config.HookDefinition(
                name="test-hook",
                type="prompt",
            )

    def test_timeout_defaults(self) -> None:
        """Timeout has sensible defaults."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo hello",
        )
        assert hook.timeout.seconds == 30
        assert hook.timeout.on_timeout == "block"

    def test_timeout_custom(self) -> None:
        """Custom timeout configuration."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="slow-command",
            timeout=config.HookTimeoutConfig(seconds=60, on_timeout="continue"),
        )
        assert hook.timeout.seconds == 60
        assert hook.timeout.on_timeout == "continue"

    def test_match_patterns(self) -> None:
        """Hook can have match patterns."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo blocked",
            match={"tool": "Bash", "tool_input.command": "^rm"},
        )
        assert hook.match["tool"] == "Bash"

    def test_enabled_default_true(self) -> None:
        """Hooks are enabled by default."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo hello",
        )
        assert hook.enabled is True


class TestHooksConfig:
    """Tests for HooksConfig model."""

    def test_empty_config(self) -> None:
        """Empty config is valid."""
        cfg = config.HooksConfig()
        assert cfg.version == 1
        assert cfg.hooks == {}

    def test_get_hooks_for_event_empty(self) -> None:
        """get_hooks_for_event returns empty list when no hooks."""
        cfg = config.HooksConfig()
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert hooks == []

    def test_get_hooks_for_event_with_hooks(self) -> None:
        """get_hooks_for_event returns matching hooks."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo hello",
        )
        cfg = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "test-hook"

    def test_get_hooks_for_event_filters_disabled(self) -> None:
        """get_hooks_for_event excludes disabled hooks."""
        enabled_hook = config.HookDefinition(
            name="enabled",
            type="command",
            command="echo enabled",
            enabled=True,
        )
        disabled_hook = config.HookDefinition(
            name="disabled",
            type="command",
            command="echo disabled",
            enabled=False,
        )
        cfg = config.HooksConfig(hooks={"pre_tool_use": [enabled_hook, disabled_hook]})
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "enabled"


class TestLoadHooksYaml:
    """Tests for YAML loading."""

    def test_load_valid_yaml(self, tmp_path: _pathlib.Path) -> None:
        """Load a valid hooks.yaml file."""
        yaml_content = _textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: log-commands
                  type: command
                  command: 'echo "Command: $BRYNHILD_TOOL_INPUT"'
                  match:
                    tool: Bash
        """)
        yaml_path = tmp_path / "hooks.yaml"
        yaml_path.write_text(yaml_content)

        cfg = config.load_hooks_yaml(yaml_path)
        assert cfg.version == 1
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "log-commands"
        assert hooks[0].match["tool"] == "Bash"

    def test_load_missing_file(self, tmp_path: _pathlib.Path) -> None:
        """Loading missing file raises FileNotFoundError."""
        with _pytest.raises(FileNotFoundError):
            config.load_hooks_yaml(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml(self, tmp_path: _pathlib.Path) -> None:
        """Loading invalid YAML raises ValueError."""
        yaml_path = tmp_path / "hooks.yaml"
        yaml_path.write_text("{ invalid yaml: [")

        with _pytest.raises(ValueError, match="Invalid YAML"):
            config.load_hooks_yaml(yaml_path)

    def test_load_invalid_schema(self, tmp_path: _pathlib.Path) -> None:
        """Loading YAML with invalid schema raises ValueError."""
        yaml_content = _textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: bad-hook
                  type: command
                  # missing command field
        """)
        yaml_path = tmp_path / "hooks.yaml"
        yaml_path.write_text(yaml_content)

        with _pytest.raises(ValueError, match="Invalid hooks config"):
            config.load_hooks_yaml(yaml_path)


class TestMergedConfig:
    """Tests for global + project config merging."""

    def test_load_merged_empty(self, tmp_path: _pathlib.Path) -> None:
        """Merged config with no files returns empty config."""
        # Use tmp_path as project root to avoid finding real config
        cfg = config.load_merged_config(project_root=tmp_path)
        assert cfg.hooks == {}

    def test_project_hook_extends_global(
        self,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Project hooks are added after global hooks."""
        # Create "global" config in temp location
        global_dir = tmp_path / "global" / ".config" / "brynhild"
        global_dir.mkdir(parents=True)
        global_yaml = global_dir / "hooks.yaml"
        global_yaml.write_text(_textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: global-hook
                  type: command
                  command: echo global
        """))

        # Create project config
        project_dir = tmp_path / "project"
        project_hooks_dir = project_dir / ".brynhild"
        project_hooks_dir.mkdir(parents=True)
        project_yaml = project_hooks_dir / "hooks.yaml"
        project_yaml.write_text(_textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: project-hook
                  type: command
                  command: echo project
        """))

        # Patch global path
        monkeypatch.setattr(
            config,
            "get_global_hooks_path",
            lambda: global_yaml,
        )

        cfg = config.load_merged_config(project_root=project_dir)
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 2
        assert hooks[0].name == "global-hook"
        assert hooks[1].name == "project-hook"

    def test_project_hook_overrides_global_by_name(
        self,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Project hook with same name replaces global hook."""
        global_dir = tmp_path / "global" / ".config" / "brynhild"
        global_dir.mkdir(parents=True)
        global_yaml = global_dir / "hooks.yaml"
        global_yaml.write_text(_textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: shared-name
                  type: command
                  command: echo global-version
        """))

        project_dir = tmp_path / "project"
        project_hooks_dir = project_dir / ".brynhild"
        project_hooks_dir.mkdir(parents=True)
        project_yaml = project_hooks_dir / "hooks.yaml"
        project_yaml.write_text(_textwrap.dedent("""
            version: 1
            hooks:
              pre_tool_use:
                - name: shared-name
                  type: command
                  command: echo project-version
        """))

        monkeypatch.setattr(
            config,
            "get_global_hooks_path",
            lambda: global_yaml,
        )

        cfg = config.load_merged_config(project_root=project_dir)
        hooks = cfg.get_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].command == "echo project-version"

