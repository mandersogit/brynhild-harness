"""
Hook configuration loading.

Hooks are configured in YAML files:
- Global: ~/.config/brynhild/hooks.yaml
- Project: .brynhild/hooks.yaml

Global hooks run first, then project hooks. Project hooks with the same
name as global hooks replace them.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import pydantic as _pydantic
import yaml as _yaml

import brynhild.hooks.events as events


class HookTimeoutConfig(_pydantic.BaseModel):
    """Configuration for hook timeout behavior."""

    seconds: int = 30
    """Timeout in seconds (default 30)."""

    on_timeout: _typing.Literal["block", "continue"] = "block"
    """Action to take when timeout is exceeded."""


class HookDefinition(_pydantic.BaseModel):
    """
    Definition of a single hook.

    Hooks are defined in hooks.yaml and specify:
    - When to fire (event type and match conditions)
    - What to execute (command, script, or prompt)
    - How to handle results
    """

    model_config = _pydantic.ConfigDict(extra="forbid")

    name: str
    """Unique identifier for this hook."""

    type: _typing.Literal["command", "script", "prompt"]
    """Hook type: command (shell), script (Python), or prompt (LLM)."""

    # Trigger conditions
    event: str | None = None
    """Event to trigger on (if defined at hook level, not section level)."""

    match: dict[str, _typing.Any] = _pydantic.Field(default_factory=dict)
    """Pattern matching conditions. All must match (AND logic)."""

    # Execution
    command: str | None = None
    """Shell command to execute (for type=command)."""

    script: str | None = None
    """Path to Python script (for type=script)."""

    prompt: str | None = None
    """LLM prompt template (for type=prompt)."""

    model: str | None = None
    """Model to use for prompt hooks (optional, uses default)."""

    # Result handling
    message: str | None = None
    """Message to show user if hook blocks (for type=command)."""

    timeout: HookTimeoutConfig = _pydantic.Field(default_factory=HookTimeoutConfig)
    """Timeout configuration."""

    enabled: bool = True
    """Whether this hook is enabled."""

    @_pydantic.model_validator(mode="after")
    def _validate_type_fields(self) -> HookDefinition:
        """Validate that the right fields are set for the hook type."""
        if self.type == "command" and not self.command:
            raise ValueError("command hooks must specify 'command' field")
        if self.type == "script" and not self.script:
            raise ValueError("script hooks must specify 'script' field")
        if self.type == "prompt" and not self.prompt:
            raise ValueError("prompt hooks must specify 'prompt' field")
        return self


class HooksConfig(_pydantic.BaseModel):
    """
    Complete hooks configuration from a hooks.yaml file.

    The config is organized by event type:
    ```yaml
    version: 1
    hooks:
      pre_tool_use:
        - name: log_commands
          type: command
          ...
      post_tool_use:
        - name: notify_errors
          type: script
          ...
    ```
    """

    model_config = _pydantic.ConfigDict(extra="forbid")

    version: int = 1
    """Config version (for future compatibility)."""

    hooks: dict[str, list[HookDefinition]] = _pydantic.Field(default_factory=dict)
    """Hooks organized by event name."""

    def get_hooks_for_event(self, event: events.HookEvent) -> list[HookDefinition]:
        """Get all enabled hooks for a given event."""
        hook_list = self.hooks.get(event.value, [])
        return [h for h in hook_list if h.enabled]


def load_hooks_yaml(path: _pathlib.Path) -> HooksConfig:
    """
    Load hooks configuration from a YAML file.

    Args:
        path: Path to hooks.yaml file.

    Returns:
        Parsed HooksConfig.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Hooks config not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
        data = _yaml.safe_load(content) or {}
        return HooksConfig.model_validate(data)
    except _yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e
    except _pydantic.ValidationError as e:
        raise ValueError(f"Invalid hooks config in {path}: {e}") from e


def get_global_hooks_path() -> _pathlib.Path:
    """Get the path to global hooks config."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "hooks.yaml"


def get_project_hooks_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """Get the path to project-local hooks config."""
    return project_root / ".brynhild" / "hooks.yaml"


def load_merged_config(
    project_root: _pathlib.Path | None = None,
) -> HooksConfig:
    """
    Load and merge global and project hooks configs.

    Global hooks run first, then project hooks. Project hooks with the
    same name as global hooks replace them.

    Args:
        project_root: Project root directory. If None, only global hooks
                      are loaded.

    Returns:
        Merged HooksConfig.
    """
    # Start with empty config
    merged_hooks: dict[str, list[HookDefinition]] = {}

    # Load global hooks
    global_path = get_global_hooks_path()
    if global_path.exists():
        try:
            global_config = load_hooks_yaml(global_path)
            for event_name, hooks in global_config.hooks.items():
                merged_hooks[event_name] = list(hooks)
        except (ValueError, FileNotFoundError):
            # Skip invalid global config
            pass

    # Load project hooks
    if project_root is not None:
        project_path = get_project_hooks_path(project_root)
        if project_path.exists():
            try:
                project_config = load_hooks_yaml(project_path)

                for event_name, project_hooks in project_config.hooks.items():
                    if event_name not in merged_hooks:
                        merged_hooks[event_name] = []

                    # Get existing hook names for this event
                    existing_names = {h.name for h in merged_hooks[event_name]}

                    for hook in project_hooks:
                        if hook.name in existing_names:
                            # Replace existing hook with same name
                            merged_hooks[event_name] = [
                                h if h.name != hook.name else hook
                                for h in merged_hooks[event_name]
                            ]
                        else:
                            # Append new hook
                            merged_hooks[event_name].append(hook)
            except (ValueError, FileNotFoundError):
                # Skip invalid project config
                pass

    return HooksConfig(hooks=merged_hooks)

