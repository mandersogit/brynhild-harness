"""Custom pydantic-settings sources for Brynhild configuration.

This module provides:

- DeepChainMapSettingsSource: A pydantic-settings source that loads
  configuration from layered YAML files using DeepChainMap for merging.

Configuration layers (in precedence order, highest first):
1. Environment variables (handled by pydantic-settings)
2. Project config: .brynhild/config.yaml in project root
3. User config: ~/.config/brynhild/config.yaml (or BRYNHILD_CONFIG_DIR)
4. Built-in defaults: bundled config.yaml

The DeepChainMapSettingsSource handles layers 2-4, merging them using
DeepChainMap so that nested dictionaries merge naturally while other
values override.

Environment variables:
- BRYNHILD_CONFIG_DIR: Override user config directory (default: ~/.config/brynhild)
"""

import collections.abc as _abc
import os as _os
import pathlib as _pathlib
import typing as _typing

import pydantic.fields as _pydantic_fields
import pydantic_settings as _pydantic_settings
import yaml as _yaml

import brynhild.utils as utils

# Environment variable for overriding user config directory
ENV_CONFIG_DIR = "BRYNHILD_CONFIG_DIR"


class ConfigFileError(Exception):
    """Error loading or parsing a configuration file."""

    def __init__(self, path: _pathlib.Path, message: str) -> None:
        self.path = path
        super().__init__(f"Error in config file {path}: {message}")


class DeepChainMapSettingsSource(_pydantic_settings.PydanticBaseSettingsSource):
    """
    Settings source that loads from layered YAML config files via DeepChainMap.

    Architecture:
        DCM is used ONLY for merging YAML layers. After merging, the result
        is a plain dict that Pydantic validates and converts to typed objects.
        DCM is a merge tool, not a storage layer.

        Flow:
        1. Load each YAML file into a dict
        2. DCM merges dicts (handles nested dicts, list operations)
        3. Return merged dict to pydantic-settings
        4. Pydantic validates everything (fail-fast on errors)
        5. Settings object holds only validated, typed data

    Layers (lowest to highest precedence):
    1. Built-in defaults (src/brynhild/config/defaults/config.yaml)
    2. User config (~/.config/brynhild/config.yaml)
    3. Project config (.brynhild/config.yaml)
    """

    def __init__(
        self,
        settings_cls: type[_pydantic_settings.BaseSettings],
        project_root: _pathlib.Path | None = None,
        *,
        user_config_path: _pathlib.Path | None = None,
        builtin_config_path: _pathlib.Path | None = None,
    ) -> None:
        """
        Initialize the settings source.

        Args:
            settings_cls: The Settings class being populated.
            project_root: Optional project root path for project-level config.
            user_config_path: Override path for user config file (for testing).
                If not provided, uses BRYNHILD_CONFIG_DIR env var or default XDG path.
            builtin_config_path: Override path for builtin defaults (for testing).
                If not provided, uses the bundled defaults/config.yaml.
        """
        super().__init__(settings_cls)
        self._project_root = project_root
        self._user_config_path = user_config_path
        self._builtin_config_path = builtin_config_path
        self._dcm = self._load_config_layers()

    def _load_config_layers(self) -> utils.DeepChainMap:
        """
        Load config files into a DeepChainMap.

        DCM takes maps in priority order where first = highest precedence.
        So we build layers in reverse precedence order (builtin first),
        then reverse the list before passing to DCM.

        Returns:
            DeepChainMap containing merged configuration.
        """
        # Build layers in ascending precedence order
        layers: list[dict[str, _typing.Any]] = []

        # Layer 1: Built-in defaults (lowest precedence) — REQUIRED
        # Must exist AND have content. If missing or empty, this is an
        # installation bug that must be surfaced, not silently ignored.
        builtin_path = self._get_builtin_config_path()
        if not builtin_path.exists():
            raise ConfigFileError(
                builtin_path,
                "built-in defaults not found (possible installation problem)",
            )
        builtin_content = self._load_yaml_file(builtin_path)
        if not builtin_content:
            raise ConfigFileError(
                builtin_path,
                "built-in defaults file is empty (possible installation problem)",
            )
        layers.append(builtin_content)

        # Layer 2: User config — OPTIONAL
        # Missing user config is normal (user hasn't created one yet).
        user_path = self._get_user_config_path()
        if user_path.exists():
            content = self._load_yaml_file(user_path)
            if content:
                layers.append(content)

        # Layer 3: Project config — OPTIONAL
        # Missing project config is normal (project doesn't use brynhild config).
        if self._project_root:
            project_path = self._project_root / ".brynhild" / "config.yaml"
            if project_path.exists():
                content = self._load_yaml_file(project_path)
                if content:
                    layers.append(content)

        # Reverse so highest precedence (project) is first
        # DCM: first map = highest priority
        layers.reverse()
        return utils.DeepChainMap(*layers)

    def _get_builtin_config_path(self) -> _pathlib.Path:
        """Get path to builtin defaults, respecting override."""
        if self._builtin_config_path is not None:
            return self._builtin_config_path
        return _pathlib.Path(__file__).parent / "defaults" / "config.yaml"

    def _get_user_config_path(self) -> _pathlib.Path:
        """Get path to user config, respecting override and env var."""
        if self._user_config_path is not None:
            return self._user_config_path

        # Check environment variable
        config_dir_env = _os.environ.get(ENV_CONFIG_DIR)
        if config_dir_env:
            return _pathlib.Path(config_dir_env) / "config.yaml"

        # Default XDG path
        return _pathlib.Path.home() / ".config" / "brynhild" / "config.yaml"

    def _load_yaml_file(
        self,
        path: _pathlib.Path,
    ) -> dict[str, _typing.Any] | None:
        """
        Load a YAML file and return its contents as a dict.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed YAML contents, or None if file is empty.

        Raises:
            ConfigFileError: If the file cannot be read, is malformed YAML,
                or contains non-dict content at the top level.
        """
        # Handle file read errors
        try:
            content = path.read_text(encoding="utf-8")
        except PermissionError as e:
            raise ConfigFileError(path, f"permission denied: {e}") from e
        except OSError as e:
            raise ConfigFileError(path, f"cannot read file: {e}") from e

        # Handle YAML parse errors
        try:
            parsed = _yaml.safe_load(content)
        except _yaml.YAMLError as e:
            raise ConfigFileError(path, f"invalid YAML: {e}") from e

        # Handle empty file
        if parsed is None:
            return None

        # Validate top-level is a dict
        if not isinstance(parsed, dict):
            type_name = type(parsed).__name__
            raise ConfigFileError(
                path,
                f"config must be a YAML mapping (dict), got {type_name}",
            )

        return parsed

    def get_field_value(
        self,
        field: _pydantic_fields.FieldInfo,  # noqa: ARG002 - required by pydantic-settings interface
        field_name: str,
    ) -> tuple[_typing.Any, str, bool]:
        """
        Get value for a field from the DeepChainMap.

        Args:
            field: The Pydantic field info.
            field_name: Name of the field to retrieve.

        Returns:
            Tuple of (value, field_name, is_complex).
            is_complex is True if the value is a dict or list.
        """
        # For now, assume flat structure matching Settings fields
        # Nested config (e.g., models.default) is handled by Pydantic
        # after we return the top-level dict
        value = self._dcm.get(field_name, None)

        if value is None:
            return None, field_name, False

        # DCM returns MutableProxy for nested dicts, which is a Mapping
        return value, field_name, isinstance(value, (_abc.Mapping, list))

    def __call__(self) -> dict[str, _typing.Any]:
        """
        Return merged config as a plain dict for Pydantic validation.

        This returns the FULL merged config, including unknown keys.
        Unknown keys will be captured in Settings.model_extra via extra="allow",
        enabling strict validation mode to detect typos.

        Returns:
            Full merged config dict (not filtered to known fields).
        """
        return self._dcm.to_dict()


def get_builtin_defaults_path() -> _pathlib.Path:
    """
    Get the path to the built-in defaults config file.

    Returns:
        Path to defaults/config.yaml.
    """
    return _pathlib.Path(__file__).parent / "defaults" / "config.yaml"


def get_user_config_path() -> _pathlib.Path:
    """
    Get the path to the user config file.

    Respects BRYNHILD_CONFIG_DIR environment variable if set,
    otherwise uses XDG standard path.

    Returns:
        Path to config.yaml in user config directory.
    """
    config_dir_env = _os.environ.get(ENV_CONFIG_DIR)
    if config_dir_env:
        return _pathlib.Path(config_dir_env) / "config.yaml"
    return _pathlib.Path.home() / ".config" / "brynhild" / "config.yaml"


def get_user_config_dir() -> _pathlib.Path:
    """
    Get the user config directory.

    Respects BRYNHILD_CONFIG_DIR environment variable if set,
    otherwise uses XDG standard path.

    Returns:
        Path to user config directory.
    """
    config_dir_env = _os.environ.get(ENV_CONFIG_DIR)
    if config_dir_env:
        return _pathlib.Path(config_dir_env)
    return _pathlib.Path.home() / ".config" / "brynhild"


def get_project_config_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """
    Get the path to the project config file.

    Args:
        project_root: The project root directory.

    Returns:
        Path to .brynhild/config.yaml within the project.
    """
    return project_root / ".brynhild" / "config.yaml"
