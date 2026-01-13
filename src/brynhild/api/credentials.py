"""
Credentials loading utilities for LLM providers.

Provides shared functionality for loading credentials from JSON files
with path expansion (~ and environment variables).
"""

import json as _json
import os as _os
import pathlib as _pathlib
import typing as _typing


def load_credentials_from_path(path: str) -> dict[str, _typing.Any]:
    """
    Load credentials from a JSON file.

    Args:
        path: Path to credentials JSON file. Supports ~ and $VAR expansion.

    Returns:
        Dict containing credentials (e.g., {"api_key": "..."}).

    Raises:
        ValueError: If file cannot be read or parsed.

    Example:
        >>> creds = load_credentials_from_path("~/.config/brynhild/credentials/openrouter.json")
        >>> api_key = creds.get("api_key")
    """
    # Expand ~ and environment variables
    expanded_path = _os.path.expandvars(_os.path.expanduser(path))
    creds_path = _pathlib.Path(expanded_path)

    if not creds_path.exists():
        raise ValueError(f"Credentials file not found: {expanded_path}")

    try:
        content = creds_path.read_text(encoding="utf-8")
        credentials = _json.loads(content)
        if not isinstance(credentials, dict):
            raise ValueError(
                f"Credentials file must contain a JSON object: {expanded_path}"
            )
        return credentials
    except PermissionError as e:
        raise ValueError(
            f"Permission denied reading credentials file: {expanded_path}"
        ) from e
    except _json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in credentials file {expanded_path}: {e}"
        ) from e

