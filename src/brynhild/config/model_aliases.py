"""
Model alias configuration.

Translates canonical model names (OpenRouter format) to provider-specific names.

Configuration is loaded from three locations (highest precedence first):
1. Project: .brynhild/model-aliases.yaml
2. Global: ~/.config/brynhild/model-aliases.yaml
3. Brynhild defaults: built-in to the package

Example model-aliases.yaml:
    ollama:
      openai/gpt-oss-120b: gpt-oss:120b
      openai/gpt-oss-20b: gpt-oss:20b
"""

from __future__ import annotations

import pathlib as _pathlib

import yaml as _yaml

# Brynhild built-in defaults (lowest precedence)
# These provide reasonable defaults for common models
_BUILTIN_ALIASES: dict[str, dict[str, str]] = {
    "ollama": {
        # OpenAI models
        "openai/gpt-oss-120b": "gpt-oss:120b",
        "openai/gpt-oss-20b": "gpt-oss:20b",
    },
}

# Cached merged aliases (populated on first use)
_cached_aliases: dict[str, dict[str, str]] | None = None
_cached_project_root: _pathlib.Path | None = None


def get_global_aliases_path() -> _pathlib.Path:
    """Get the path to global model aliases config."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "model-aliases.yaml"


def get_project_aliases_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """Get the path to project model aliases config."""
    return project_root / ".brynhild" / "model-aliases.yaml"


def _load_yaml_aliases(path: _pathlib.Path) -> dict[str, dict[str, str]]:
    """Load aliases from a YAML file.

    Args:
        path: Path to model-aliases.yaml

    Returns:
        Dict mapping provider -> {canonical_name -> provider_name}
        Returns empty dict if file doesn't exist or is invalid.
    """
    if not path.exists():
        return {}

    try:
        content = path.read_text(encoding="utf-8")
        data = _yaml.safe_load(content)
        if not isinstance(data, dict):
            return {}
        # Validate structure: provider -> {model -> alias}
        result: dict[str, dict[str, str]] = {}
        for provider, aliases in data.items():
            if isinstance(provider, str) and isinstance(aliases, dict):
                result[provider] = {
                    str(k): str(v) for k, v in aliases.items()
                }
        return result
    except (_yaml.YAMLError, OSError):
        return {}


def _load_merged_aliases(
    project_root: _pathlib.Path | None = None,
) -> dict[str, dict[str, str]]:
    """Load and merge aliases from all config levels.

    Precedence (highest first):
    1. Project (.brynhild/model-aliases.yaml)
    2. Global (~/.config/brynhild/model-aliases.yaml)
    3. Brynhild built-in defaults

    Args:
        project_root: Project root directory. If None, only global and
                      built-in aliases are loaded.

    Returns:
        Merged aliases dict: provider -> {canonical_name -> provider_name}
    """
    # Start with built-in defaults (deep copy)
    merged: dict[str, dict[str, str]] = {
        provider: dict(aliases)
        for provider, aliases in _BUILTIN_ALIASES.items()
    }

    # Layer 2: Global user config
    global_path = get_global_aliases_path()
    global_aliases = _load_yaml_aliases(global_path)
    for provider, aliases in global_aliases.items():
        if provider not in merged:
            merged[provider] = {}
        merged[provider].update(aliases)

    # Layer 3: Project config (highest precedence)
    if project_root is not None:
        project_path = get_project_aliases_path(project_root)
        project_aliases = _load_yaml_aliases(project_path)
        for provider, aliases in project_aliases.items():
            if provider not in merged:
                merged[provider] = {}
            merged[provider].update(aliases)

    return merged


def get_aliases(
    project_root: _pathlib.Path | None = None,
    *,
    force_reload: bool = False,
) -> dict[str, dict[str, str]]:
    """Get merged model aliases.

    Results are cached. Use force_reload=True to reload from disk.

    Args:
        project_root: Project root directory.
        force_reload: If True, reload from config files.

    Returns:
        Merged aliases dict: provider -> {canonical_name -> provider_name}
    """
    global _cached_aliases, _cached_project_root

    # Check if cache is valid
    if (
        not force_reload
        and _cached_aliases is not None
        and _cached_project_root == project_root
    ):
        return _cached_aliases

    # Load and cache
    _cached_aliases = _load_merged_aliases(project_root)
    _cached_project_root = project_root
    return _cached_aliases


def translate_model(
    provider: str,
    model: str,
    project_root: _pathlib.Path | None = None,
) -> str:
    """Translate a canonical model name to provider-specific format.

    Args:
        provider: Provider name (e.g., 'ollama')
        model: Canonical model name (e.g., 'openai/gpt-oss-120b')
        project_root: Project root for loading project-level aliases.

    Returns:
        Provider-specific model name, or the original if no alias found.
    """
    # Try to get project root from cwd if not provided
    if project_root is None:
        try:
            import brynhild.config.settings as settings
            project_root = settings.find_project_root()
        except Exception:
            pass

    aliases = get_aliases(project_root)
    provider_aliases = aliases.get(provider, {})
    return provider_aliases.get(model, model)


def clear_cache() -> None:
    """Clear the cached aliases. Useful for testing."""
    global _cached_aliases, _cached_project_root
    _cached_aliases = None
    _cached_project_root = None

