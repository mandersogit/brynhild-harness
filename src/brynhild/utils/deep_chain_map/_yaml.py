"""
YAML loader and mapping types for DCM-layered configurations.

Provides:
- DcmMapping: A MutableMapping that handles DELETE and ReplaceMarker transparently
- DcmLoader: YAML loader that produces DcmMapping with custom tags

Custom tags:
- !delete — Mark a key for deletion from the merged result
- !replace — Mark a value to replace exactly (no deep merge)

Example:
    >>> import yaml
    >>> from brynhild.utils.deep_chain_map import DcmLoader
    >>>
    >>> data = yaml.load('''
    ... normal: value
    ... removed: !delete
    ... exact: !replace
    ...   only: this
    ... ''', Loader=DcmLoader)
    >>> "removed" in data
    False
    >>> data["exact"]
    {'only': 'this'}
"""

from __future__ import annotations

import collections.abc as _abc
import typing as _typing

import yaml as _yaml

# =============================================================================
# Marker Types
# =============================================================================


class _DeleteMarker:
    """
    Sentinel marking a key for deletion during DCM merge.

    When a layer contains `key: !delete`, the key is removed from the
    merged result, even if parent layers define it.

    This is a singleton — use the DELETE constant, not the class.
    """

    _instance: _DeleteMarker | None = None

    def __new__(cls) -> _DeleteMarker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "DELETE"

    def __reduce__(self) -> tuple[_typing.Callable[[], _DeleteMarker], tuple[()]]:
        """Support pickling by returning the singleton factory."""
        return (_get_delete_singleton, ())


def _get_delete_singleton() -> _DeleteMarker:
    """Return the DELETE singleton. Used by pickle."""
    return DELETE


# The singleton instance
DELETE = _DeleteMarker()


class ReplaceMarker:
    """
    Wrapper marking a value for exact replacement (no deep merge).

    When a layer contains `key: !replace <value>`, the value replaces
    any parent value exactly, without deep merging even if both are dicts.

    Use `.value` to access the wrapped value.
    """

    __slots__ = ("_value",)

    def __init__(self, value: _typing.Any) -> None:
        self._value = value

    @property
    def value(self) -> _typing.Any:
        """The wrapped value to use (without merging)."""
        return self._value

    def __repr__(self) -> str:
        return f"ReplaceMarker({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ReplaceMarker):
            return bool(self._value == other._value)
        return NotImplemented

    def __hash__(self) -> int:
        # Not hashable if value isn't hashable
        return hash(("ReplaceMarker", id(self._value)))


# =============================================================================
# Helper Functions
# =============================================================================


def is_delete(value: _typing.Any) -> bool:
    """Check if a value is the DELETE marker."""
    return value is DELETE


def is_replace(value: _typing.Any) -> bool:
    """Check if a value is a ReplaceMarker."""
    return isinstance(value, ReplaceMarker)


def unwrap_value(value: _typing.Any) -> _typing.Any:
    """
    Unwrap a value, handling ReplaceMarker.

    Returns the inner value if ReplaceMarker, otherwise returns as-is.
    DELETE markers are NOT unwrapped (caller should check is_delete first).
    """
    if is_replace(value):
        return value.value
    return value


# =============================================================================
# DcmMapping
# =============================================================================


class DcmMapping(_abc.MutableMapping[str, _typing.Any]):
    """
    A MutableMapping that handles DELETE and ReplaceMarker transparently.

    This mapping wraps a dict and interprets DCM markers on access:
    - DELETE markers cause KeyError (key appears not to exist)
    - ReplaceMarker values are unwrapped automatically
    - Nested dicts are wrapped in DcmMapping recursively

    For DCM internal use, raw data (including markers) is accessible via
    `_raw_data()` or `_raw_getitem()`.

    Example:
        >>> data = DcmMapping({"normal": "value", "removed": DELETE})
        >>> "removed" in data
        False
        >>> data["removed"]
        KeyError: 'removed'
        >>> data._raw_getitem("removed")
        DELETE
    """

    __slots__ = ("_data",)

    def __init__(
        self,
        data: dict[str, _typing.Any] | None = None,
        /,
        **kwargs: _typing.Any,
    ) -> None:
        """
        Create a DcmMapping.

        Args:
            data: Initial dict to wrap. If None, creates empty mapping.
            **kwargs: Additional key-value pairs to add.
        """
        if data is None:
            self._data: dict[str, _typing.Any] = {}
        else:
            self._data = data
        if kwargs:
            self._data.update(kwargs)

    # -------------------------------------------------------------------------
    # MutableMapping abstract methods
    # -------------------------------------------------------------------------

    def __getitem__(self, key: str) -> _typing.Any:
        """
        Get a value, interpreting markers.

        DELETE markers raise KeyError.
        ReplaceMarker values are unwrapped.
        Nested dicts are wrapped in DcmMapping.
        """
        value = self._data[key]
        if is_delete(value):
            raise KeyError(key)
        return _wrap_value(unwrap_value(value))

    def __setitem__(self, key: str, value: _typing.Any) -> None:
        """Set a value (overwrites any existing value or DELETE marker)."""
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        """
        Mark a key as deleted by placing a DELETE marker.

        Unlike normal dict deletion, this places a DELETE marker so
        the deletion can be preserved when used as a DCM layer.
        """
        if key not in self._data and key not in self:
            raise KeyError(key)
        self._data[key] = DELETE

    def __iter__(self) -> _typing.Iterator[str]:
        """Iterate over keys, skipping those with DELETE markers."""
        for key in self._data:
            if not is_delete(self._data[key]):
                yield key

    def __len__(self) -> int:
        """Count keys, excluding those with DELETE markers."""
        return sum(1 for key in self._data if not is_delete(self._data[key]))

    # -------------------------------------------------------------------------
    # Additional dict-like methods
    # -------------------------------------------------------------------------

    def __contains__(self, key: object) -> bool:
        """Check if key exists and is not deleted."""
        if not isinstance(key, str):
            return False
        if key not in self._data:
            return False
        return not is_delete(self._data[key])

    def __repr__(self) -> str:
        # Show the filtered view
        items = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
        return f"DcmMapping({{{items}}})"

    def __eq__(self, other: object) -> bool:
        """Compare with another mapping (compares filtered view)."""
        if isinstance(other, DcmMapping):
            return dict(self.items()) == dict(other.items())
        if isinstance(other, _abc.Mapping):
            return dict(self.items()) == dict(other.items())
        return NotImplemented

    def copy(self) -> DcmMapping:
        """Return a shallow copy."""
        return DcmMapping(self._data.copy())

    # -------------------------------------------------------------------------
    # Raw access for DCM internal use
    # -------------------------------------------------------------------------

    def _raw_data(self) -> dict[str, _typing.Any]:
        """
        Get the underlying dict with markers intact.

        For DCM internal use — allows access to DELETE and ReplaceMarker
        values for merge logic.
        """
        return self._data

    def _raw_getitem(self, key: str) -> _typing.Any:
        """
        Get raw value including markers.

        For DCM internal use — returns DELETE/ReplaceMarker as-is.
        """
        return self._data[key]

    def _raw_contains(self, key: str) -> bool:
        """
        Check if key exists in underlying data (including deleted keys).

        For DCM internal use.
        """
        return key in self._data

    def _raw_iter(self) -> _typing.Iterator[str]:
        """
        Iterate over all keys including deleted ones.

        For DCM internal use.
        """
        return iter(self._data)


def _wrap_value(value: _typing.Any) -> _typing.Any:
    """
    Wrap nested dicts/lists in DcmMapping/list with wrapped items.

    Called during __getitem__ to ensure nested structures also
    handle markers correctly.
    """
    if isinstance(value, DcmMapping):
        return value
    if isinstance(value, dict):
        return DcmMapping(value)
    if isinstance(value, list):
        return [_wrap_value(item) for item in value]
    return value


# =============================================================================
# YAML Constructors
# =============================================================================


def _delete_constructor(
    loader: _yaml.Loader,  # noqa: ARG001 - required by YAML constructor API
    node: _yaml.Node,  # noqa: ARG001 - required by YAML constructor API
) -> _DeleteMarker:
    """
    Construct a DELETE marker from !delete tag.

    The tag should have no value or an empty value:
        key: !delete
        key: !delete ~
    """
    # We ignore any value — !delete always means delete
    return DELETE


def _replace_constructor(
    loader: _yaml.Loader,
    node: _yaml.Node,
) -> ReplaceMarker:
    """
    Construct a ReplaceMarker from !replace tag.

    The tag wraps whatever value follows:
        key: !replace value
        key: !replace
          nested: dict
          not: merged
        key: !replace [list, items]
        key: !replace ~  (null)
    """
    value: _typing.Any
    if isinstance(node, _yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, _yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, _yaml.ScalarNode):
        # Parse scalar value properly
        scalar_value = node.value
        if scalar_value in ("~", "null", "Null", "NULL", ""):
            value = None
        elif scalar_value in ("true", "True", "TRUE"):
            value = True
        elif scalar_value in ("false", "False", "FALSE"):
            value = False
        else:
            # Try to interpret as number
            try:
                value = int(scalar_value)
            except ValueError:
                try:
                    value = float(scalar_value)
                except ValueError:
                    value = scalar_value
    else:
        value = None

    return ReplaceMarker(value)


def _dcm_mapping_constructor(
    loader: _yaml.Loader,
    node: _yaml.MappingNode,
) -> DcmMapping:
    """
    Construct a DcmMapping from a YAML mapping node.

    This replaces the default dict constructor so YAML mappings
    become DcmMapping instances.
    """
    loader.flatten_mapping(node)
    pairs = loader.construct_pairs(node, deep=True)  # type: ignore[no-untyped-call]
    return DcmMapping(dict(pairs))


# =============================================================================
# DcmLoader
# =============================================================================


class DcmLoader(_yaml.SafeLoader):
    """
    YAML loader for DeepChainMap layered configurations.

    Extends SafeLoader with:
    - Custom tags: `!delete` and `!replace`
    - Produces DcmMapping instead of dict

    The resulting DcmMapping handles markers transparently:
    - `!delete` keys appear not to exist
    - `!replace` values are unwrapped automatically

    Example YAML:
        # Remove an inherited key
        deprecated_setting: !delete

        # Replace a dict entirely (don't merge with parent's dict)
        api_params: !replace
          only: these
          params: used

    Usage:
        >>> import yaml
        >>> from brynhild.utils.deep_chain_map import DcmLoader
        >>> data = yaml.load(content, Loader=DcmLoader)
        >>> "deprecated_setting" in data
        False
    """

    pass


# Register custom constructors
DcmLoader.add_constructor("!delete", _delete_constructor)
DcmLoader.add_constructor("!replace", _replace_constructor)
# Override default mapping constructor to produce DcmMapping
DcmLoader.add_constructor(
    _yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _dcm_mapping_constructor,
)


# =============================================================================
# Convenience Functions
# =============================================================================


def load(stream: _typing.Any) -> _typing.Any:
    """
    Load YAML with DCM extensions (!delete, !replace).

    Args:
        stream: YAML content (string, bytes, or file-like object).

    Returns:
        DcmMapping with markers handled transparently.
    """
    return _yaml.load(stream, Loader=DcmLoader)
