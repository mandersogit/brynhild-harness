"""
MutableProxy for DeepChainMap.

Provides a mutable view of nested dictionaries that routes writes to
the front_layer and deletes to the delete_layer.

Example:
    >>> dcm = DeepChainMap({"a": {"b": {"c": 1}}})
    >>> proxy = dcm["a"]  # Returns MutableProxy
    >>> proxy["b"]["c"] = 99  # Routes to dcm._front_layer
    >>> del proxy["b"]["d"]   # Routes to dcm._delete_layer
"""

from __future__ import annotations

from collections import abc as _abc
import typing as _typing

if _typing.TYPE_CHECKING:
    import brynhild.utils.deep_chain_map._core as _core

import brynhild.utils.deep_chain_map._frozen as _frozen


class MutableProxy(_abc.MutableMapping[str, _typing.Any]):
    """
    Mutable view of a nested dict within a DeepChainMap.

    Reads return the merged value (frozen for nested containers).
    Writes route to the DeepChainMap's front_layer.
    Deletes route to the DeepChainMap's delete_layer.

    This allows natural Python dict syntax for deeply nested operations:
        dcm["config"]["model"]["name"] = "new_name"
        del dcm["config"]["deprecated_key"]
    """

    __slots__ = ("_dcm", "_path", "_data")

    def __init__(
        self,
        dcm: _core.DeepChainMap,
        path: tuple[str, ...],
        data: _abc.Mapping[str, _typing.Any],
    ) -> None:
        """
        Create a mutable proxy.

        Args:
            dcm: The owning DeepChainMap.
            path: The path from root to this dict.
            data: The merged dict data at this path.
        """
        self._dcm = dcm
        self._path = path
        self._data = data

    def __getitem__(self, key: str) -> _typing.Any:
        """
        Get a value, returning proxy for dicts and frozen for lists.

        Raises:
            KeyError: If key not in merged data or is deleted.
        """
        # Check if deleted
        full_path = self._path + (key,)
        if self._dcm._is_path_deleted(full_path):
            raise KeyError(key)

        # Get from data
        if key not in self._data:
            raise KeyError(key)

        value = self._data[key]

        # Wrap appropriately
        if isinstance(value, dict):
            return MutableProxy(self._dcm, full_path, value)
        if isinstance(value, list):
            return _frozen.FrozenSequence(value)
        return value

    def __setitem__(self, key: str, value: _typing.Any) -> None:
        """
        Set a value at this path, routing to front_layer.

        Nested dicts are deep-merged by default.
        """
        full_path = self._path + (key,)
        self._dcm._set_at_path(full_path, value)

    def __delitem__(self, key: str) -> None:
        """
        Mark a key as deleted, routing to delete_layer.

        Raises:
            KeyError: If key not in merged data.
        """
        full_path = self._path + (key,)

        # Check key exists before deleting
        if self._dcm._is_path_deleted(full_path):
            raise KeyError(key)
        if key not in self._data:
            raise KeyError(key)

        self._dcm._delete_at_path(full_path)

    def __iter__(self) -> _typing.Iterator[str]:
        """Iterate over keys, excluding deleted ones."""
        for key in self._data:
            full_path = self._path + (key,)
            if not self._dcm._is_path_deleted(full_path):
                yield key

    def __len__(self) -> int:
        """Return count of non-deleted keys."""
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        """Check if key exists and is not deleted."""
        if not isinstance(key, str):
            return False
        full_path = self._path + (key,)
        if self._dcm._is_path_deleted(full_path):
            return False
        return key in self._data

    def __repr__(self) -> str:
        # Show actual content (non-deleted keys)
        content = {k: self._data[k] for k in self}
        path_str = ".".join(self._path) if self._path else "<root>"
        return f"MutableProxy({content!r}, path={path_str!r})"

    def __eq__(self, other: object) -> bool:
        """Compare equal to any Mapping with same visible content."""
        if isinstance(other, _abc.Mapping):
            return dict(self.items()) == dict(other.items())
        return NotImplemented

    def __hash__(self) -> int:
        """Not hashable."""
        raise TypeError(f"unhashable type: '{type(self).__name__}'")

