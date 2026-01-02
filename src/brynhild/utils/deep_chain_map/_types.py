"""
Type aliases for DeepChainMap.

This module provides type aliases used throughout the DCM package:
- Path: Tuple of strings representing a nested key path
- Provenance: Recursive dict structure tracking which layer each key came from
"""

from __future__ import annotations

import typing as _typing

# Path alias for nested key paths
# Example: ("config", "model", "name") represents config.model.name
Path: _typing.TypeAlias = tuple[str, ...]

# Provenance tracks which layer each key came from
# Structure: {"key": layer_index, "nested": {"subkey": layer_index, ...}}
# Special key "." indicates the value itself (for scalars)
# Layer index -1 indicates front_layer
if _typing.TYPE_CHECKING:
    # Recursive type for type checking
    Provenance: _typing.TypeAlias = dict[str, "int | Provenance"]
else:
    # Runtime-safe fallback (mypy uses TYPE_CHECKING branch)
    Provenance: _typing.TypeAlias = dict[str, object]

