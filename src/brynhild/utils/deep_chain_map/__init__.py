"""
DeepChainMap — ChainMap with deep merging and immutable semantics.

This package provides a ChainMap-like class that recursively merges nested
dictionaries at lookup time. Layers are checked in priority order (first
layer = highest priority).

Example:
    >>> from brynhild.utils.deep_chain_map import DeepChainMap
    >>> builtin = {"model": {"name": "llama", "size": "7b"}}
    >>> user = {"model": {"size": "70b"}}  # Override just size
    >>> dcm = DeepChainMap(user, builtin)
    >>> dcm["model"]
    {'name': 'llama', 'size': '70b'}

YAML Extensions:

    The package also provides a custom YAML loader with tags for controlling
    merge behavior in DCM layered configurations:

    - !delete — Mark a key for deletion from the merged result
    - !replace — Mark a value to replace exactly (no deep merge)

    Example:
        >>> from brynhild.utils.deep_chain_map import DcmLoader, DELETE
        >>> import yaml
        >>> data = yaml.load("key: !delete", Loader=DcmLoader)
        >>> data["key"] is DELETE
        True
"""

from brynhild.utils.deep_chain_map._core import DeepChainMap
from brynhild.utils.deep_chain_map._yaml import (
    DELETE,
    DcmLoader,
    DcmMapping,
    ReplaceMarker,
    is_delete,
    is_replace,
    load,
    unwrap_value,
)

__all__ = [
    "DeepChainMap",
    "DcmLoader",
    "DcmMapping",
    "DELETE",
    "ReplaceMarker",
    "is_delete",
    "is_replace",
    "load",
    "unwrap_value",
]

