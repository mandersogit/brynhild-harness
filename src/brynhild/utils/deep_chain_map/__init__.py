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
"""

from brynhild.utils.deep_chain_map._core import DeepChainMap

__all__ = ["DeepChainMap"]

