"""
DeepChainMap: A ChainMap-like class with deep merging and immutable semantics.

Unlike collections.ChainMap which returns the first dict containing a key,
DeepChainMap recursively merges values from all layers that contain a key.

2.0 Architecture:
- Source layers: Stored by reference, never modified by DCM (can be DcmMapping or dict)
- Front layer: DcmMapping for user overrides and deletions via __setitem__/__delitem__
- List ops: Pending operations on lists (append, setitem, etc.)

Read semantics:
- Dicts: Returns MutableProxy (writes route to front_layer)
- Lists: Returns FrozenSequence (use list_* methods to modify)
- Scalars: Returns value directly

Thread safety: NOT thread-safe for concurrent writes. Read-only
concurrent access is safe.
"""

from __future__ import annotations

import collections.abc as _abc
import copy as _copy
import typing as _typing

import brynhild.utils.deep_chain_map._frozen as _frozen
import brynhild.utils.deep_chain_map._operations as _operations
import brynhild.utils.deep_chain_map._yaml as _yaml_markers


# Sentinel for missing values during layer lookup
class _MissingType:
    """Sentinel for missing values (distinct from None)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingType()


class DeepChainMap(_typing.MutableMapping[str, _typing.Any]):
    """
    A ChainMap-like mapping with deep merging at lookup time.

    Layers are stored separately and merged on access. Results are cached
    for efficiency and can be invalidated with reload().

    Example:
        >>> builtin = {"model": {"name": "llama", "size": "7b"}}
        >>> user = {"model": {"size": "70b"}}  # Override just size
        >>> dcm = DeepChainMap(user, builtin)  # user has priority
        >>> dcm["model"]
        {'name': 'llama', 'size': '70b'}

    Provenance tracking:
        >>> dcm.get_with_provenance("model")
        ({'name': 'llama', 'size': '70b'}, {'name': 1, 'size': 0})
        # 1 = builtin layer, 0 = user layer (indices into layers)
        # -1 = front_layer (user overrides via __setitem__)

    Args:
        *maps: Dicts in priority order (first = highest priority).
        track_provenance: Whether to track which layer values came from.

    Note:
        **Source layer semantics:** Source layers are stored **by reference**,
        not copied. This means:

        1. DeepChainMap will never modify your source dicts (writes go to
           ``front_layer``, deletes go to ``delete_layer``)
        2. If you modify source dicts externally, DCM won't see changes
           until you call ``reload()`` to clear the cache
        3. Multiple DeepChainMaps can share the same source layers

        The ``layers`` and ``source_layers`` properties return FrozenMapping
        wrappers to prevent accidental mutation, but the underlying dicts
        remain accessible if you hold a reference to them.

        If you need snapshot semantics (isolated from source changes),
        deep copy your dicts before passing them::

            import copy
            dcm = DeepChainMap(copy.deepcopy(config))

        **Thread safety:** Not thread-safe for concurrent writes. Specifically:

        - Multiple threads calling ``__setitem__`` concurrently: UNSAFE
        - One thread writing while another reads: UNSAFE
        - Multiple threads reading concurrently (no writes): SAFE

        Use external synchronization (e.g., ``threading.Lock``) if concurrent
        write access is required.

        **Cache sharing:** Returned proxies share underlying cache data for
        performance. If you need to mutate a returned value without affecting
        the DCM, use ``get_mutable(key)`` to get an independent deep copy.
    """

    def __init__(
        self,
        *maps: _abc.Mapping[str, _typing.Any],
        track_provenance: bool = False,
    ) -> None:
        # Source layers - stored by reference, can be DcmMapping or plain dict
        # Exposed as FrozenMappings via properties to prevent mutation
        self._layers: list[_abc.Mapping[str, _typing.Any]] = list(maps)
        self._track_provenance = track_provenance
        self._cache: dict[str, _typing.Any] = {}
        self._provenance_cache: dict[str, dict[str, _typing.Any]] = {}

        # Front layer for user modifications (DcmMapping handles both values and deletions)
        self._front_layer: _yaml_markers.DcmMapping = _yaml_markers.DcmMapping()
        self._list_ops: dict[tuple[str, ...], list[_typing.Any]] = {}

    @property
    def layers(self) -> list[_frozen.FrozenMapping]:
        """Read-only access to source layers.

        DEPRECATED: Use source_layers instead.

        Returns:
            List of FrozenMappings wrapping the source layers.
            Mutations to these will raise TypeError.
        """
        return [_frozen.FrozenMapping(layer) for layer in self._layers]

    @property
    def source_layers(self) -> list[_frozen.FrozenMapping]:
        """Read-only access to source layers (original data, frozen).

        Returns:
            List of FrozenMappings wrapping the source layers.
            Mutations to these will raise TypeError.
        """
        return [_frozen.FrozenMapping(layer) for layer in self._layers]

    @property
    def front_layer(self) -> _yaml_markers.DcmMapping:
        """Read-only access to the front layer (user overrides and deletions)."""
        return self._front_layer

    @property
    def list_ops(self) -> dict[tuple[str, ...], list[_typing.Any]]:
        """Read-only access to pending list operations."""
        return self._list_ops

    def add_layer(
        self,
        data: dict[str, _typing.Any],
        priority: int | None = None,
    ) -> None:
        """
        Add a new layer.

        Args:
            data: The dict to add as a layer.
            priority: Index to insert at. None = highest priority (index 0).
        """
        self._clear_cache()
        if priority is None:
            self._layers.insert(0, data)
        else:
            self._layers.insert(priority, data)

    def remove_layer(self, index: int) -> _abc.Mapping[str, _typing.Any]:
        """
        Remove and return a layer by index.

        Args:
            index: Layer index (0 = highest priority).

        Returns:
            The removed layer (Mapping, e.g., dict or DcmMapping).
        """
        self._clear_cache()
        return self._layers.pop(index)

    def reload(self) -> None:
        """
        Clear the cache, forcing re-merge on next access.

        Call this after modifying layer contents in place.
        Does NOT clear front_layer or list_ops.
        """
        self._clear_cache()

    def clear_front_layer(self) -> None:
        """Clear all user overrides and deletions in front_layer."""
        self._front_layer._raw_data().clear()
        self._clear_cache()

    def clear_list_ops(self) -> None:
        """Clear all pending list operations."""
        self._list_ops.clear()
        self._clear_cache()

    def reset(self) -> None:
        """
        Clear all user modifications.

        Clears front_layer, list_ops, and cache.
        Source layers are preserved.
        """
        self._front_layer._raw_data().clear()
        self._list_ops.clear()
        self._clear_cache()

    def reorder_layers(self, new_order: list[int]) -> None:
        """
        Reorder source layers.

        Args:
            new_order: List of current indices in desired new order.
                       E.g., [2, 0, 1] moves layer 2 to position 0.

        Raises:
            ValueError: If new_order is invalid.
        """
        if sorted(new_order) != list(range(len(self._layers))):
            raise ValueError(
                f"new_order must contain each index 0..{len(self._layers)-1} exactly once"
            )
        self._layers = [self._layers[i] for i in new_order]
        self._clear_cache()

    def _clear_cache(self) -> None:
        """Clear internal caches."""
        self._cache.clear()
        self._provenance_cache.clear()

    # =========================================================================
    # Path helpers for 2.0 mutation semantics
    # =========================================================================

    def _set_at_path(
        self,
        path: tuple[str, ...],
        value: _typing.Any,
        *,
        merge: bool = True,
    ) -> None:
        """
        Set a value at a nested path in front_layer.

        Creates intermediate dicts as needed. If the final key exists and
        both old and new values are dicts, they are merged (unless merge=False).

        Setting a value automatically clears any DELETE marker at that path.

        Args:
            path: Tuple of keys representing the path (e.g., ("a", "b", "c")).
            value: The value to set.
            merge: If True and both existing and new values are dicts, merge them.
                   If False, replace entirely.

        Raises:
            TypeError: If any path component is not a string.
        """
        if not path:
            return

        # Validate all path components are strings
        for component in path:
            if not isinstance(component, str):
                raise TypeError(
                    f"Path components must be strings, got {type(component).__name__}"
                )

        # Navigate/create path in front_layer's raw data
        raw_data = self._front_layer._raw_data()
        current: dict[str, _typing.Any] = raw_data
        for key in path[:-1]:
            raw_value = current.get(key)
            # Skip DELETE markers and non-dicts
            if raw_value is None or _yaml_markers.is_delete(raw_value) or not isinstance(raw_value, dict):
                current[key] = {}
            current = current[key]

        final_key = path[-1]

        # Handle merge vs replace
        if merge and isinstance(value, dict):
            existing = current.get(final_key)
            # Don't merge with DELETE markers
            if isinstance(existing, dict) and not _yaml_markers.is_delete(existing):
                current[final_key] = self._deep_merge_dicts(existing, value)
            else:
                current[final_key] = _copy.deepcopy(value)
        else:
            current[final_key] = _copy.deepcopy(value)

        self._clear_cache()

    def _delete_at_path(self, path: tuple[str, ...]) -> None:
        """
        Mark a path as deleted by placing DELETE marker in front_layer.

        Args:
            path: Tuple of keys representing the path to delete.

        Raises:
            TypeError: If any path component is not a string.
        """
        if not path:
            return

        # Validate all path components are strings
        for component in path:
            if not isinstance(component, str):
                raise TypeError(
                    f"Path components must be strings, got {type(component).__name__}"
                )

        # Clear any list_ops for this path or sub-paths
        to_remove = [p for p in self._list_ops if p == path or (
            len(p) > len(path) and p[:len(path)] == path
        )]
        for p in to_remove:
            del self._list_ops[p]

        # Place DELETE marker in front_layer's raw data
        raw_data = self._front_layer._raw_data()
        current: dict[str, _typing.Any] = raw_data
        for key in path[:-1]:
            raw_value = current.get(key)
            if raw_value is None or _yaml_markers.is_delete(raw_value) or not isinstance(raw_value, dict):
                current[key] = {}
            current = current[key]

        current[path[-1]] = _yaml_markers.DELETE
        self._clear_cache()

    def _is_deleted_in_front_layer(self, path: tuple[str, ...]) -> bool:
        """
        Check if a path has DELETE marker in front_layer.

        Returns True if any prefix of the path is marked with DELETE.

        Args:
            path: Tuple of keys to check.

        Returns:
            True if the path or any ancestor is deleted in front_layer.
        """
        raw_data = self._front_layer._raw_data()
        current: _typing.Any = raw_data
        for key in path:
            if not isinstance(current, dict):
                return False
            if key not in current:
                return False
            value = current[key]
            if _yaml_markers.is_delete(value):
                return True
            current = value
        return False

    def _deep_merge_dicts(
        self,
        base: dict[str, _typing.Any],
        override: dict[str, _typing.Any],
    ) -> dict[str, _typing.Any]:
        """
        Deep merge two dicts, with override taking priority.

        Handles YAML markers:
        - DELETE: removes the key from merged result
        - ReplaceMarker: uses value exactly, no deep merge

        Args:
            base: The base dict (or Mapping).
            override: The dict to merge in (or Mapping, takes priority).

        Returns:
            New merged dict.
        """
        result = dict(base)

        # Iterate using raw access for DcmMapping to see DELETE markers
        override_keys: _typing.Iterable[str]
        if isinstance(override, _yaml_markers.DcmMapping):
            override_keys = override._raw_iter()
        else:
            override_keys = override.keys()

        for key in override_keys:
            # Get raw value (handles DcmMapping)
            if isinstance(override, _yaml_markers.DcmMapping):
                value = override._raw_getitem(key)
            else:
                value = override[key]

            # Handle YAML DELETE marker
            if _yaml_markers.is_delete(value):
                result.pop(key, None)
                continue

            # Handle YAML ReplaceMarker - no deep merge
            if _yaml_markers.is_replace(value):
                result[key] = _copy.deepcopy(value.value)
                continue

            # Normal merge logic (check for Mapping, not just dict)
            result_is_mapping = isinstance(result.get(key), _abc.Mapping)
            value_is_mapping = isinstance(value, _abc.Mapping)

            if key in result and result_is_mapping and value_is_mapping:
                result[key] = self._deep_merge_dicts(result[key], value)
            else:
                result[key] = _copy.deepcopy(value)
        return result

    # =========================================================================
    # List operations for 2.0 semantics
    # =========================================================================

    def own_list(self, path: tuple[str, ...]) -> None:
        """
        Copy a list from source layers to front_layer.

        After owning, the list is independent of source updates.
        Direct mutations to front_layer[path] won't be visible to sources.

        Args:
            path: Path to the list to own.

        Raises:
            KeyError: If path doesn't exist.
            TypeError: If value at path is not a list.
        """
        import collections.abc as _abc

        # Get current merged value at path
        value = self._get_at_path(path)

        # Support list and Sequence (FrozenSequence)
        if not isinstance(value, _abc.Sequence) or isinstance(value, str):
            raise TypeError(f"Value at path {path!r} is not a list")

        # Copy to front_layer
        self._set_at_path(path, list(value), merge=False)

        # Clear any pending operations for this path
        if path in self._list_ops:
            del self._list_ops[path]

        self._clear_cache()

    def list_append(self, path: tuple[str, ...], value: _typing.Any) -> None:
        """
        Append a value to a list.

        Stores an Append operation to be replayed on read.

        Args:
            path: Path to the list.
            value: Value to append.
        """
        self._add_list_op(path, _operations.Append(value))

    def list_extend(
        self,
        path: tuple[str, ...],
        values: _typing.Iterable[_typing.Any],
    ) -> None:
        """
        Extend a list with values.

        Args:
            path: Path to the list.
            values: Values to extend with.
        """
        self._add_list_op(path, _operations.Extend(tuple(values)))

    def list_insert(
        self,
        path: tuple[str, ...],
        index: int,
        value: _typing.Any,
    ) -> None:
        """
        Insert a value at an index.

        Args:
            path: Path to the list.
            index: Index to insert at.
            value: Value to insert.
        """
        self._add_list_op(path, _operations.Insert(index, value))

    def list_setitem(
        self,
        path: tuple[str, ...],
        index: int,
        value: _typing.Any,
    ) -> None:
        """
        Set item at index.

        Args:
            path: Path to the list.
            index: Index to set.
            value: Value to set.
        """
        self._add_list_op(path, _operations.SetItem(index, value))

    def list_delitem(self, path: tuple[str, ...], index: int) -> None:
        """
        Delete item at index.

        Args:
            path: Path to the list.
            index: Index to delete.
        """
        self._add_list_op(path, _operations.DelItem(index))

    def list_pop(self, path: tuple[str, ...], index: int = -1) -> None:
        """
        Record a pop operation at the given index.

        Unlike Python's list.pop(), this does NOT return the removed value.
        List operations are lazy: the pop is recorded and applied when the
        list is next accessed. Use own_list() first if you need the value.

        Args:
            path: Path to the list.
            index: Index to pop (default: -1, last item).

        Note:
            To get the value before popping:
                value = list(dcm["items"])[-1]  # Get last item
                dcm.list_pop(("items",))        # Then pop it
        """
        self._add_list_op(path, _operations.Pop(index))

    def list_remove(self, path: tuple[str, ...], value: _typing.Any) -> None:
        """
        Remove first occurrence of value.

        Args:
            path: Path to the list.
            value: Value to remove.
        """
        self._add_list_op(path, _operations.Remove(value))

    def list_clear(self, path: tuple[str, ...]) -> None:
        """
        Clear all items from list.

        Args:
            path: Path to the list.
        """
        self._add_list_op(path, _operations.Clear())

    def _add_list_op(self, path: tuple[str, ...], op: _operations.ListOp) -> None:
        """
        Add a list operation for a path.

        Args:
            path: Path to the list.
            op: Operation to add.
        """
        if path not in self._list_ops:
            self._list_ops[path] = []
        self._list_ops[path].append(op)
        self._clear_cache()

    def _get_raw_layer_value(
        self,
        layer: _abc.Mapping[str, _typing.Any],
        key: str,
    ) -> _typing.Any:
        """
        Get raw value from a layer, including markers.

        Works with both DcmMapping (uses _raw_getitem) and plain dict.

        Args:
            layer: The layer to query.
            key: The key to look up.

        Returns:
            The raw value, or _MISSING if key not in layer.
        """
        if isinstance(layer, _yaml_markers.DcmMapping):
            if layer._raw_contains(key):
                return layer._raw_getitem(key)
            return _MISSING
        # Plain dict or other Mapping
        if key in layer:
            return layer[key]
        return _MISSING

    def _get_at_path(self, path: tuple[str, ...]) -> _typing.Any:
        """
        Get value at a nested path from merged layers.

        Args:
            path: Path to navigate.

        Returns:
            Value at path.

        Raises:
            KeyError: If path doesn't exist.
        """
        if not path:
            raise KeyError("Empty path")

        current: _typing.Any = self[path[0]]
        for key in path[1:]:
            # Support both dict and Mapping (MutableProxy)
            if isinstance(current, _abc.Mapping):
                current = current[key]
            else:
                raise KeyError(f"Cannot navigate through non-dict at {key!r}")
        return current

    def __getitem__(self, key: str) -> _typing.Any:
        """
        Get a merged value for key.

        Merge order (2.0 semantics):
        1. Check front_layer for DELETE (masks everything)
        2. Merge source layers (lowest to highest priority)
           - DELETE marker stops merging from that layer down
           - ReplaceMarker prevents deep merge, uses value exactly
        3. Apply list_ops (replay operations on lists)
        4. Apply front_layer (deep merge overrides)
        5. Return appropriate wrapper (MutableProxy for dicts, FrozenSequence for lists)

        Raises:
            KeyError: If key doesn't exist or is deleted.
        """
        # Check front_layer for DELETE (masks everything)
        front_raw = self._front_layer._raw_data()
        if key in front_raw:
            raw_front_value = front_raw[key]
            if _yaml_markers.is_delete(raw_front_value):
                raise KeyError(key)

        if key in self._cache:
            return self._wrap_for_return(key, self._cache[key])

        # Step 1: Collect values from source layers (highest to lowest priority)
        # Stop collecting when we hit a DELETE or REPLACE marker
        values: list[tuple[int, _typing.Any]] = []
        for i, layer in enumerate(self._layers):
            layer_value = self._get_raw_layer_value(layer, key)
            if layer_value is not _MISSING:
                if _yaml_markers.is_delete(layer_value):
                    # DELETE marker - stop here, don't include lower layers
                    break
                # REPLACE marker - use this value, don't include lower layers
                if _yaml_markers.is_replace(layer_value):
                    values.append((i, layer_value.value))
                    break  # Don't merge with lower layers
                values.append((i, layer_value))

        # Check front_layer for non-DELETE value
        has_front = key in front_raw and not _yaml_markers.is_delete(front_raw[key])
        front_value = None
        if has_front:
            raw_value = front_raw[key]
            # Unwrap ReplaceMarker
            if _yaml_markers.is_replace(raw_value):
                front_value = raw_value.value
            else:
                front_value = raw_value

        if not values and not has_front:
            raise KeyError(key)

        # Reverse values to process lowest-to-highest priority for merge
        values = list(reversed(values))

        # Merge source layers
        provenance: dict[str, _typing.Any]
        if len(values) == 0:
            # Value only in front_layer
            result = _copy.deepcopy(front_value)
            # Provenance: -1 indicates front_layer
            if isinstance(result, dict):
                provenance = dict.fromkeys(result, -1)
            else:
                provenance = {".": -1}
        elif len(values) == 1:
            result = _copy.deepcopy(values[0][1])
            provenance = self._build_provenance(result, values[0][0])
        else:
            result, provenance = self._deep_merge_with_provenance(values)

        # Step 2: Apply nested YAML markers (DELETE and ReplaceMarker)
        if isinstance(result, dict):
            result = self._apply_yaml_markers(result, (key,))

        # Step 3: Apply list_ops
        result = self._apply_all_list_ops(result, (key,))

        # Step 4: Apply front_layer override
        if has_front:
            if isinstance(result, dict) and isinstance(front_value, dict):
                result = self._deep_merge_dicts(result, front_value)
                # Update provenance for front_layer keys (-1 = front_layer)
                if self._track_provenance:
                    self._update_provenance_for_front(provenance, front_value)
            else:
                result = _copy.deepcopy(front_value)
                # Scalar from front_layer
                if self._track_provenance:
                    provenance = {".": -1}

        self._cache[key] = result
        if self._track_provenance:
            self._provenance_cache[key] = provenance

        return self._wrap_for_return(key, result)

    def _apply_yaml_markers(
        self,
        value: dict[str, _typing.Any],
        path: tuple[str, ...],
        seen: set[int] | None = None,
    ) -> dict[str, _typing.Any]:
        """
        Recursively process YAML markers (!delete, !replace) in merged dict.

        This handles nested DELETE and ReplaceMarker values that survived
        the initial merge (e.g., from nested structures).

        Args:
            value: The dict to process.
            path: Current path (for future provenance tracking).
            seen: Set of object ids to detect circular references.

        Returns:
            Dict with YAML markers processed.
        """
        if seen is None:
            seen = set()

        obj_id = id(value)
        if obj_id in seen:
            return value  # Circular reference, return as-is
        seen.add(obj_id)

        result = {}
        for k, v in value.items():
            # DELETE marker - skip this key
            if _yaml_markers.is_delete(v):
                continue
            # ReplaceMarker - unwrap and use value directly
            if _yaml_markers.is_replace(v):
                result[k] = _copy.deepcopy(v.value)
            elif isinstance(v, dict):
                result[k] = self._apply_yaml_markers(v, path + (k,), seen)
            else:
                result[k] = v
        return result

    def _apply_all_list_ops(
        self,
        value: _typing.Any,
        path: tuple[str, ...],
        seen: set[int] | None = None,
    ) -> _typing.Any:
        """
        Recursively apply list_ops to lists in the structure.

        Args:
            value: The value to process.
            path: Current path for list_ops lookup.
            seen: Set of object ids to detect circular references.

        Returns:
            Value with list operations applied.
        """
        if seen is None:
            seen = set()

        if isinstance(value, list):
            if path in self._list_ops:
                return _operations.apply_operations(value, self._list_ops[path])
            return value
        elif isinstance(value, dict):
            obj_id = id(value)
            if obj_id in seen:
                return value  # Circular reference
            seen.add(obj_id)

            result = {}
            for k, v in value.items():
                result[k] = self._apply_all_list_ops(v, path + (k,), seen)
            return result
        return value

    def _wrap_for_return(self, key: str, value: _typing.Any) -> _typing.Any:
        """
        Wrap a value appropriately for return from __getitem__.

        Args:
            key: The top-level key.
            value: The merged value.

        Returns:
            MutableProxy for dicts, FrozenSequence for lists, value otherwise.
        """
        import brynhild.utils.deep_chain_map._proxy as _proxy

        if isinstance(value, dict):
            return _proxy.MutableProxy(self, (key,), value)
        if isinstance(value, list):
            return _frozen.FrozenSequence(value)
        return value

    def __setitem__(self, key: str, value: _typing.Any) -> None:
        """
        Set a value in front_layer.

        2.0 semantics: Writes go to front_layer, not source layers.
        Source layers are never modified.
        """
        self._set_at_path((key,), value)

    def __delitem__(self, key: str) -> None:
        """
        Mark a key as deleted.

        2.0 semantics: Deletion markers go to front_layer.
        Source layers are never modified.
        """
        # Check key exists first
        if key not in self:
            raise KeyError(key)
        self._delete_at_path((key,))

    def __iter__(self) -> _typing.Iterator[str]:
        """Iterate over all unique keys, respecting deletions."""
        seen: set[str] = set()
        deleted: set[str] = set()  # Keys deleted by DELETE markers

        # Include front_layer keys (using raw access to see DELETE markers)
        front_raw = self._front_layer._raw_data()
        for key in front_raw:
            if key in seen:
                continue
            seen.add(key)
            value = front_raw[key]
            if _yaml_markers.is_delete(value):
                deleted.add(key)
            else:
                yield key

        # Include source layer keys - DELETE marker masks all lower layers
        for layer in self._layers:
            for key in self._iter_layer_keys(layer):
                if key in seen:
                    continue
                seen.add(key)
                if key in deleted:
                    continue  # Already deleted by higher layer
                value = self._get_raw_layer_value(layer, key)
                if _yaml_markers.is_delete(value):
                    deleted.add(key)  # DELETE masks all lower layers
                else:
                    yield key

    def _iter_layer_keys(
        self,
        layer: _abc.Mapping[str, _typing.Any],
    ) -> _typing.Iterator[str]:
        """Iterate over keys in a layer (raw, including deleted)."""
        if isinstance(layer, _yaml_markers.DcmMapping):
            return layer._raw_iter()
        return iter(layer)

    def __len__(self) -> int:
        """Count unique non-deleted keys."""
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        """Check if key exists and is not deleted."""
        if not isinstance(key, str):
            return False

        # Check front_layer first (using raw access)
        front_raw = self._front_layer._raw_data()
        if key in front_raw:
            value = front_raw[key]
            # DELETE in front_layer masks everything
            return not _yaml_markers.is_delete(value)

        # Check source layers - DELETE in higher-priority layer masks lower layers
        for layer in self._layers:
            value = self._get_raw_layer_value(layer, key)
            if value is not _MISSING:
                return not _yaml_markers.is_delete(value)
        return False

    def __repr__(self) -> str:
        parts = [repr(layer) for layer in self._layers]
        front_raw = self._front_layer._raw_data()
        if front_raw:
            parts.insert(0, f"front={front_raw!r}")
        if self._list_ops:
            parts.append(f"list_ops={len(self._list_ops)} paths")
        return f"DeepChainMap({', '.join(parts)})"

    def get_with_provenance(
        self,
        key: str,
    ) -> tuple[_typing.Any, dict[str, _typing.Any]]:
        """
        Get a merged value along with provenance information.

        Returns:
            Tuple of (merged_value, provenance_dict).
            The provenance dict maps leaf keys to layer indices (0 = highest priority).

        Raises:
            KeyError: If no layer contains the key.
            RuntimeError: If track_provenance was not enabled.
        """
        if not self._track_provenance:
            raise RuntimeError(
                "Provenance tracking not enabled. "
                "Create DeepChainMap with track_provenance=True."
            )

        value = self[key]  # Ensures cache is populated
        return value, self._provenance_cache.get(key, {})

    def to_dict(self) -> dict[str, _typing.Any]:
        """
        Return a fully merged dict of all keys as a plain dict.

        This eagerly merges everything and returns a mutable deep copy.
        Useful for serialization (JSON, etc.) or when you need a snapshot.
        """
        result: dict[str, _typing.Any] = {}
        for key in self:
            value = self._cache.get(key)
            if value is None:
                # Trigger cache population
                _ = self[key]
                value = self._cache[key]
            result[key] = _copy.deepcopy(value)
        return result

    def copy(self) -> DeepChainMap:
        """
        Return a shallow copy of this DeepChainMap.

        The copy shares the same source layer references but has independent
        front_layer and list_ops. Changes to the copy's user state
        (set/delete/list ops) won't affect the original.

        Returns:
            A new DeepChainMap with shared source layers.

        Note:
            Source layers are shared, not copied. If you mutate a source
            layer dict directly, both the original and copy will see the
            change (after reload()).
        """
        new = DeepChainMap(
            *self._layers,
            track_provenance=self._track_provenance,
        )
        # Deep copy front_layer's raw data into a new DcmMapping
        new._front_layer = _yaml_markers.DcmMapping(
            _copy.deepcopy(self._front_layer._raw_data())
        )
        new._list_ops = {
            path: list(ops) for path, ops in self._list_ops.items()
        }
        return new

    def get_mutable(self, key: str) -> _typing.Any:
        """
        Get a deep copy of merged value, safe to mutate.

        Unlike __getitem__ which returns proxies/frozen views, this
        returns a fully mutable deep copy.

        Args:
            key: The key to get.

        Returns:
            Deep copy of the merged value.
        """
        _ = self[key]  # Populate cache
        return _copy.deepcopy(self._cache[key])

    def _deep_merge_with_provenance(
        self,
        values: list[tuple[int, _typing.Any]],
    ) -> tuple[_typing.Any, dict[str, _typing.Any]]:
        """
        Deep merge values from multiple layers.

        Args:
            values: List of (layer_index, value) tuples, sorted from
                    lowest to highest priority.

        Returns:
            Tuple of (merged_value, provenance_dict).
        """
        # Start with the lowest priority value
        result = _copy.deepcopy(values[0][1])
        provenance = self._build_provenance(result, values[0][0])

        # Merge each higher priority value
        for layer_idx, value in values[1:]:
            result, provenance = self._merge_value(
                result, value, provenance, layer_idx
            )

        return result, provenance

    def _merge_value(
        self,
        base: _typing.Any,
        override: _typing.Any,
        # TODO: Define a proper recursive TypeAlias for provenance instead of Any.
        # Provenance maps keys to either int (layer index) or nested provenance dict.
        # Correct type: Provenance = dict[str, int | Provenance]
        provenance: dict[str, _typing.Any],
        layer_idx: int,
    ) -> tuple[_typing.Any, dict[str, _typing.Any]]:
        """
        Merge override into base.

        Handles YAML markers:
        - DELETE: removes the key from merged result
        - ReplaceMarker: uses value exactly, no deep merge

        Args:
            base: The current merged value.
            override: The higher-priority value to merge in.
            provenance: Current provenance dict.
            layer_idx: Index of the layer override came from.

        Returns:
            Tuple of (merged_value, updated_provenance).
        """
        # Unwrap ReplaceMarker at top level - don't deep merge
        if _yaml_markers.is_replace(override):
            return _copy.deepcopy(override.value), {".": layer_idx}

        # Check for dict-like types (dict or Mapping like DcmMapping)
        base_is_mapping = isinstance(base, _abc.Mapping)
        override_is_mapping = isinstance(override, _abc.Mapping)

        if base_is_mapping and override_is_mapping:
            # Recursive dict merge
            result = dict(base)
            new_provenance = dict(provenance)

            # Iterate using raw access for DcmMapping to see DELETE markers
            override_keys: _typing.Iterable[str]
            if isinstance(override, _yaml_markers.DcmMapping):
                override_keys = override._raw_iter()
            else:
                override_keys = override.keys()

            for key in override_keys:
                # Get raw value (handles DcmMapping)
                if isinstance(override, _yaml_markers.DcmMapping):
                    value = override._raw_getitem(key)
                else:
                    value = override[key]

                # Handle YAML DELETE marker
                if _yaml_markers.is_delete(value):
                    # Remove key from result
                    result.pop(key, None)
                    new_provenance.pop(key, None)
                    continue

                # Handle YAML ReplaceMarker - no deep merge
                if _yaml_markers.is_replace(value):
                    result[key] = _copy.deepcopy(value.value)
                    new_provenance[key] = layer_idx
                    continue

                # Normal merge logic - check for nested mappings
                result_is_mapping = isinstance(result.get(key), _abc.Mapping)
                value_is_mapping = isinstance(value, _abc.Mapping)

                if key in result and result_is_mapping and value_is_mapping:
                    # Recursive merge for nested dicts
                    result[key], sub_prov = self._merge_value(
                        result[key],
                        value,
                        provenance.get(key, {}) if isinstance(provenance.get(key), dict) else {},
                        layer_idx,
                    )
                    new_provenance[key] = sub_prov
                else:
                    # Replace (scalar, list, or type mismatch)
                    result[key] = _copy.deepcopy(value)
                    if isinstance(value, list):
                        base_val = base.get(key) if base_is_mapping else None
                        result[key] = self._merge_list(
                            base_val if isinstance(base_val, list) else None,
                            value,
                        )
                    new_provenance[key] = layer_idx

            return result, new_provenance

        elif isinstance(base, list) and isinstance(override, list):
            # List merge based on strategy
            return self._merge_list(base, override), {".": layer_idx}

        else:
            # Scalar or type mismatch: override wins
            return _copy.deepcopy(override), {".": layer_idx}

    def _merge_list(
        self,
        base: list[_typing.Any] | None,
        override: list[_typing.Any],
    ) -> list[_typing.Any]:
        """
        Merge lists: higher priority replaces lower priority.

        For more complex list operations, use the list_* methods
        (list_append, list_extend, etc.) which store operations to
        be applied on read.

        Args:
            base: The lower-priority list (ignored).
            override: The higher-priority list.

        Returns:
            Deep copy of the override list.
        """
        # Lists always replace (no automatic merging)
        # Use list_append/list_extend for explicit operations
        del base  # Unused, but kept for API compatibility
        return _copy.deepcopy(override)

    def _build_provenance(
        self,
        value: _typing.Any,
        layer_idx: int,
        *,
        _seen: set[int] | None = None,
    ) -> dict[str, _typing.Any]:
        """
        Build initial provenance dict for a value from a single layer.

        Recursively builds provenance for nested dicts so that all keys
        at all levels are tracked.

        Args:
            value: The value to build provenance for.
            layer_idx: The layer index it came from.
            _seen: Internal set of seen object ids for cycle detection.

        Returns:
            Provenance dict mapping keys to layer indices (or nested dicts).
        """
        if isinstance(value, dict):
            # Cycle detection: skip if we've seen this exact dict object
            if _seen is None:
                _seen = set()
            value_id = id(value)
            if value_id in _seen:
                return {}  # Circular reference, stop recursion
            _seen.add(value_id)

            result: dict[str, _typing.Any] = {}
            for k, v in value.items():
                if isinstance(v, dict):
                    # Recursively build provenance for nested dicts
                    result[k] = self._build_provenance(v, layer_idx, _seen=_seen)
                else:
                    result[k] = layer_idx
            return result
        else:
            return {".": layer_idx}

    def _update_provenance_for_front(
        self,
        provenance: dict[str, _typing.Any],
        front_value: dict[str, _typing.Any],
    ) -> None:
        """
        Update provenance dict in-place for front_layer values.

        Front layer values are marked with index -1 to distinguish them
        from source layers (which have indices >= 0).

        Args:
            provenance: The provenance dict to update (modified in place).
            front_value: The dict from front_layer being merged.
        """
        for key in front_value:
            provenance[key] = -1

