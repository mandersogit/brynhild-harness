"""
MutableProxy for DeepChainMap.

Provides a live mutable view of nested dictionaries that routes writes to
the front_layer. Unlike a snapshot, reads always reflect the current state.

Example:
    >>> dcm = DeepChainMap({"a": {"b": {"c": 1}}})
    >>> proxy = dcm["a"]  # Returns MutableProxy
    >>> proxy["b"]["c"] = 99  # Routes to dcm._front_layer
    >>> proxy["b"]["c"]  # Returns 99 (live view!)
"""

from __future__ import annotations

import collections.abc as _abc
import typing as _typing

if _typing.TYPE_CHECKING:
    import brynhild.utils.deep_chain_map._core as _core

import brynhild.utils.deep_chain_map._frozen as _frozen


class MutableProxy(_abc.MutableMapping[str, _typing.Any]):
    """
    Live mutable view of a nested dict within a DeepChainMap.

    Reads always reflect the current merged state (not a stale snapshot).
    Writes route to the DeepChainMap's front_layer.
    Deletes place DELETE markers in front_layer.

    This allows natural Python dict syntax for deeply nested operations:
        dcm["config"]["model"]["name"] = "new_name"
        del dcm["config"]["deprecated_key"]

    Unlike previous versions, this proxy is a LIVE VIEW — changes made
    through the proxy are immediately visible when reading through the
    same proxy instance.
    """

    __slots__ = ("_dcm", "_path", "_use_live_data", "_data")

    def __init__(
        self,
        dcm: _core.DeepChainMap,
        path: tuple[str, ...],
        data: _abc.Mapping[str, _typing.Any],
        *,
        _use_live_data: bool = False,
    ) -> None:
        """
        Create a mutable proxy.

        Args:
            dcm: The owning DeepChainMap.
            path: The path from root to this dict (at least one component for live mode).
            data: The merged dict data at this path (ignored if _use_live_data=True).
            _use_live_data: Internal flag - if True, fetch data from DCM cache.
                           If False (default), use the passed data directly.

        For normal usage through DeepChainMap.__getitem__, _use_live_data=True is passed
        to enable live view semantics. For testing or when constructing proxies directly,
        the default False preserves backward compatibility.
        """
        self._dcm = dcm
        self._path = path
        self._use_live_data = _use_live_data
        # Store data reference when not in live mode
        # In live mode, this is unused but initialized for safety
        self._data = data

    def _get_data(self) -> _abc.Mapping[str, _typing.Any]:
        """
        Get the current data at this path.

        In live mode, fetches from DCM cache. Otherwise uses stored data.

        Returns:
            The current Mapping.

        Raises:
            KeyError: If the path no longer exists (live mode only).
        """
        if self._use_live_data:
            return self._dcm._get_cached_data_at_path(self._path)
        return self._data

    def __getitem__(self, key: str) -> _typing.Any:
        """
        Get a value, returning proxy for Mappings and frozen for lists.

        Raises:
            KeyError: If key not in merged data or is deleted.
        """
        # Check if deleted in front_layer
        full_path = self._path + (key,)
        if self._dcm._is_deleted_in_front_layer(full_path):
            raise KeyError(key)

        # Get current data
        data = self._get_data()
        if key not in data:
            raise KeyError(key)

        value = data[key]

        # Wrap appropriately - check Mapping to catch DcmMapping and other types
        # Propagate live data mode to nested proxies
        if isinstance(value, _abc.Mapping):
            return MutableProxy(self._dcm, full_path, value, _use_live_data=self._use_live_data)
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
        Mark a key as deleted by placing DELETE marker in front_layer.

        Raises:
            KeyError: If key not in merged data.
        """
        full_path = self._path + (key,)

        # Check key exists before deleting
        if self._dcm._is_deleted_in_front_layer(full_path):
            raise KeyError(key)

        data = self._get_data()
        if key not in data:
            raise KeyError(key)

        self._dcm._delete_at_path(full_path)

    def __iter__(self) -> _typing.Iterator[str]:
        """Iterate over keys, excluding deleted ones."""
        data = self._get_data()
        for key in data:
            full_path = self._path + (key,)
            if not self._dcm._is_deleted_in_front_layer(full_path):
                yield key

    def __len__(self) -> int:
        """Return count of non-deleted keys."""
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        """Check if key exists and is not deleted."""
        if not isinstance(key, str):
            return False
        full_path = self._path + (key,)
        if self._dcm._is_deleted_in_front_layer(full_path):
            return False
        data = self._get_data()
        return key in data

    def __repr__(self) -> str:
        # Show actual content (non-deleted keys)
        try:
            data = self._get_data()
            content: _typing.Any = {k: data[k] for k in self}
        except KeyError:
            content = "<stale path>"
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
