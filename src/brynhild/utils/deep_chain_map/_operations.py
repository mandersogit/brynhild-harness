"""
List operation dataclasses for DeepChainMap.

These operations are stored in list_ops and replayed on the merged
source list when reading. This preserves visibility of source updates
while allowing user modifications.

Example:
    >>> dcm = DeepChainMap({"plugins": ["a", "b"]})
    >>> dcm.list_append(("plugins",), "c")  # Store operation
    >>> dcm["plugins"]  # Replays: ["a", "b"] + append("c") = ["a", "b", "c"]

Alternatively, use own_list() to copy the list to front_layer,
then continue using list operations:
    >>> dcm.own_list(("plugins",))  # Copy to front_layer
    >>> dcm.list_append(("plugins",), "d")  # Add more items
"""

from __future__ import annotations

import dataclasses as _dataclasses
import typing as _typing


@_dataclasses.dataclass(frozen=True, slots=True)
class ListOp:
    """Base class for list operations."""

    pass


@_dataclasses.dataclass(frozen=True, slots=True)
class SetItem(ListOp):
    """Set item at index."""

    index: int
    value: _typing.Any


@_dataclasses.dataclass(frozen=True, slots=True)
class DelItem(ListOp):
    """Delete item at index."""

    index: int


@_dataclasses.dataclass(frozen=True, slots=True)
class Append(ListOp):
    """Append value to end."""

    value: _typing.Any


@_dataclasses.dataclass(frozen=True, slots=True)
class Insert(ListOp):
    """Insert value at index."""

    index: int
    value: _typing.Any


@_dataclasses.dataclass(frozen=True, slots=True)
class Extend(ListOp):
    """Extend with values."""

    values: tuple[_typing.Any, ...]  # Immutable


@_dataclasses.dataclass(frozen=True, slots=True)
class Clear(ListOp):
    """Clear all items."""

    pass


@_dataclasses.dataclass(frozen=True, slots=True)
class Pop(ListOp):
    """Pop item at index (default -1)."""

    index: int = -1


@_dataclasses.dataclass(frozen=True, slots=True)
class Remove(ListOp):
    """Remove first occurrence of value."""

    value: _typing.Any


def apply_operations(
    base: list[_typing.Any],
    operations: list[ListOp],
) -> list[_typing.Any]:
    """
    Apply a sequence of operations to a base list.

    Creates a copy of the base list and applies each operation in order.

    Args:
        base: The base list to start from.
        operations: Sequence of ListOp to apply.

    Returns:
        New list with all operations applied.

    Raises:
        IndexError: If an operation references an invalid index.
        ValueError: If Remove can't find the value.
    """
    result = list(base)  # Copy

    for op in operations:
        if isinstance(op, SetItem):
            result[op.index] = op.value
        elif isinstance(op, DelItem):
            del result[op.index]
        elif isinstance(op, Append):
            result.append(op.value)
        elif isinstance(op, Insert):
            result.insert(op.index, op.value)
        elif isinstance(op, Extend):
            result.extend(op.values)
        elif isinstance(op, Clear):
            result.clear()
        elif isinstance(op, Pop):
            result.pop(op.index)
        elif isinstance(op, Remove):
            result.remove(op.value)
        else:
            raise TypeError(f"Unknown ListOp type: {type(op).__name__}")

    return result

