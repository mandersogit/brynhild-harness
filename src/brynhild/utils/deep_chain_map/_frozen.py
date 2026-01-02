"""
Frozen (read-only) wrappers for collections.

These wrappers provide read-only views of mutable containers. Nested
containers are frozen on access, creating a fully immutable view of
the entire structure.

FrozenMapping wraps dicts, FrozenSequence wraps lists.
"""

from __future__ import annotations

import collections.abc as _abc
import typing as _typing


class FrozenMapping(_abc.Mapping[str, _typing.Any]):
    """
    Read-only view of a dict.

    Nested containers (dicts and lists) are frozen on access, so the
    entire structure is effectively immutable through this view.

    Example:
        >>> data = {"a": {"b": [1, 2, 3]}}
        >>> frozen = FrozenMapping(data)
        >>> frozen["a"]["b"][0]  # Works
        1
        >>> frozen["a"]["b"][0] = 99  # TypeError: immutable
    """

    __slots__ = ("_data",)

    def __init__(self, data: _abc.Mapping[str, _typing.Any]) -> None:
        """
        Wrap a mapping in a read-only view.

        Args:
            data: The mapping to wrap. If it's already a dict, it's used
                  directly (not copied). Otherwise it's converted to dict.
        """
        self._data = dict(data) if not isinstance(data, dict) else data

    def __getitem__(self, key: str) -> _typing.Any:
        """Get a value, freezing nested containers."""
        return freeze(self._data[key])

    def __iter__(self) -> _typing.Iterator[str]:
        """Iterate over keys."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return number of keys."""
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenMapping({self._data!r})"

    def __eq__(self, other: object) -> bool:
        """Compare equal to any Mapping with same content."""
        if isinstance(other, _abc.Mapping):
            return dict(self) == dict(other)
        return NotImplemented

    def __hash__(self) -> int:
        """FrozenMapping is not hashable (values may be mutable)."""
        raise TypeError(f"unhashable type: '{type(self).__name__}'")


class FrozenSequence(_abc.Sequence[_typing.Any]):
    """
    Read-only view of a list.

    Nested containers (dicts and lists) are frozen on access, so the
    entire structure is effectively immutable through this view.

    Example:
        >>> data = [{"a": 1}, {"b": 2}]
        >>> frozen = FrozenSequence(data)
        >>> frozen[0]["a"]  # Works
        1
        >>> frozen[0]["a"] = 99  # TypeError: immutable
    """

    __slots__ = ("_data",)

    def __init__(self, data: _abc.Sequence[_typing.Any]) -> None:
        """
        Wrap a sequence in a read-only view.

        Args:
            data: The sequence to wrap. If it's already a list, it's used
                  directly (not copied). Otherwise it's converted to list.
        """
        self._data = list(data) if not isinstance(data, list) else data

    @_typing.overload
    def __getitem__(self, index: int) -> _typing.Any: ...

    @_typing.overload
    def __getitem__(self, index: slice) -> FrozenSequence: ...

    def __getitem__(self, index: int | slice) -> _typing.Any:
        """Get an item or slice, freezing nested containers."""
        value = self._data[index]
        if isinstance(index, slice):
            return FrozenSequence(value)
        return freeze(value)

    def __len__(self) -> int:
        """Return length of sequence."""
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenSequence({self._data!r})"

    def __eq__(self, other: object) -> bool:
        """Compare equal to any Sequence with same content (except strings)."""
        if isinstance(other, str):
            return NotImplemented
        if isinstance(other, _abc.Sequence):
            return list(self) == list(other)
        return NotImplemented

    def __hash__(self) -> int:
        """FrozenSequence is not hashable (values may be mutable)."""
        raise TypeError(f"unhashable type: '{type(self).__name__}'")


def freeze(value: _typing.Any) -> _typing.Any:
    """
    Wrap mutable containers in frozen views.

    - dict/Mapping → FrozenMapping
    - list/Sequence → FrozenSequence (except str/bytes)
    - Already frozen types returned as-is
    - Other types returned as-is

    Args:
        value: Any value to potentially freeze.

    Returns:
        Frozen view if value is a mutable container, otherwise unchanged.

    Example:
        >>> freeze({"a": [1, 2]})
        FrozenMapping({'a': [1, 2]})
        >>> freeze([1, 2, 3])
        FrozenSequence([1, 2, 3])
        >>> freeze("string")
        'string'
    """
    # Already frozen - return as-is
    if isinstance(value, (FrozenMapping, FrozenSequence)):
        return value
    # Mapping types (dict, DcmMapping, OrderedDict, etc.)
    if isinstance(value, _abc.Mapping):
        return FrozenMapping(value)
    # Sequence types (list, etc.) but NOT str/bytes/tuple
    # Tuple is already immutable, str/bytes are not containers
    if isinstance(value, _abc.Sequence) and not isinstance(value, (str, bytes, tuple)):
        return FrozenSequence(value)
    return value

