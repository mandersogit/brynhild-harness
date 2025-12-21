"""
Tests for DeepChainMap 2.0 features.

These tests verify the new immutability and mutation semantics:
- front_layer for user overrides
- delete_layer for deletion tracking
- Path-based operations
- MutableProxy for natural dict syntax
"""

import typing as _typing

import pytest as _pytest

import brynhild.utils as utils
from brynhild.utils.deep_chain_map._core import _DELETED
from brynhild.utils.deep_chain_map._frozen import FrozenSequence
from brynhild.utils.deep_chain_map._proxy import MutableProxy
from brynhild.utils.deep_chain_map import _operations


class TestPathHelpers:
    """Tests for path-based helper methods."""

    def test_set_at_path_creates_nested_structure(self) -> None:
        """_set_at_path creates intermediate dicts."""
        dcm = utils.DeepChainMap({"existing": 1})

        dcm._set_at_path(("a", "b", "c"), "value")

        assert dcm._front_layer == {"a": {"b": {"c": "value"}}}

    def test_set_at_path_single_key(self) -> None:
        """_set_at_path with single key sets at top level."""
        dcm = utils.DeepChainMap()

        dcm._set_at_path(("key",), "value")

        assert dcm._front_layer == {"key": "value"}

    def test_set_at_path_empty_path_does_nothing(self) -> None:
        """_set_at_path with empty path is a no-op."""
        dcm = utils.DeepChainMap()

        dcm._set_at_path((), "value")

        assert dcm._front_layer == {}

    def test_set_at_path_merges_dicts_by_default(self) -> None:
        """_set_at_path deep merges dicts when merge=True (default)."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": {"existing": 1, "b": {"old": "value"}}}

        dcm._set_at_path(("a",), {"b": {"new": "added"}, "c": 2})

        assert dcm._front_layer["a"]["existing"] == 1
        assert dcm._front_layer["a"]["b"]["old"] == "value"
        assert dcm._front_layer["a"]["b"]["new"] == "added"
        assert dcm._front_layer["a"]["c"] == 2

    def test_set_at_path_replaces_when_merge_false(self) -> None:
        """_set_at_path replaces entirely when merge=False."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": {"existing": 1, "b": 2}}

        dcm._set_at_path(("a",), {"new": "only"}, merge=False)

        assert dcm._front_layer["a"] == {"new": "only"}

    def test_set_at_path_clears_deletion_marker(self) -> None:
        """_set_at_path removes deletion marker for the path."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": {"b": _DELETED}}

        dcm._set_at_path(("a", "b"), "restored")

        assert "b" not in dcm._delete_layer.get("a", {})
        assert dcm._front_layer["a"]["b"] == "restored"

    def test_set_at_path_clears_cache(self) -> None:
        """_set_at_path clears the cache."""
        dcm = utils.DeepChainMap({"a": 1})
        _ = dcm["a"]  # Populate cache
        assert "a" in dcm._cache

        dcm._set_at_path(("b",), 2)

        assert dcm._cache == {}

    def test_set_at_path_overwrites_non_dict_intermediate(self) -> None:
        """_set_at_path overwrites scalar with dict when path requires it."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": "scalar"}

        dcm._set_at_path(("a", "b"), "value")

        assert dcm._front_layer == {"a": {"b": "value"}}


class TestDeleteAtPath:
    """Tests for _delete_at_path."""

    def test_delete_at_path_creates_marker(self) -> None:
        """_delete_at_path creates _DELETED marker in delete_layer."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})

        dcm._delete_at_path(("a", "b"))

        assert dcm._delete_layer == {"a": {"b": _DELETED}}

    def test_delete_at_path_single_key(self) -> None:
        """_delete_at_path with single key deletes at top level."""
        dcm = utils.DeepChainMap({"a": 1})

        dcm._delete_at_path(("a",))

        assert dcm._delete_layer == {"a": _DELETED}

    def test_delete_at_path_empty_does_nothing(self) -> None:
        """_delete_at_path with empty path is a no-op."""
        dcm = utils.DeepChainMap()

        dcm._delete_at_path(())

        assert dcm._delete_layer == {}

    def test_delete_at_path_clears_front_layer_value(self) -> None:
        """_delete_at_path removes value from front_layer."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": {"b": "override"}}

        dcm._delete_at_path(("a", "b"))

        assert "b" not in dcm._front_layer.get("a", {})
        assert dcm._delete_layer == {"a": {"b": _DELETED}}

    def test_delete_at_path_clears_list_ops(self) -> None:
        """_delete_at_path removes list_ops for deleted path and sub-paths."""
        dcm = utils.DeepChainMap()
        dcm._list_ops = {
            ("a", "items"): ["op1"],
            ("a", "items", "nested"): ["op2"],
            ("b", "other"): ["op3"],
        }

        dcm._delete_at_path(("a",))

        assert ("a", "items") not in dcm._list_ops
        assert ("a", "items", "nested") not in dcm._list_ops
        assert ("b", "other") in dcm._list_ops

    def test_delete_at_path_clears_cache(self) -> None:
        """_delete_at_path clears the cache."""
        dcm = utils.DeepChainMap({"a": 1})
        _ = dcm["a"]
        assert "a" in dcm._cache

        dcm._delete_at_path(("a",))

        assert dcm._cache == {}


class TestIsPathDeleted:
    """Tests for _is_path_deleted."""

    def test_path_not_deleted(self) -> None:
        """Returns False when path is not deleted."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})

        assert dcm._is_path_deleted(("a", "b")) is False

    def test_path_deleted_exact(self) -> None:
        """Returns True when exact path is deleted."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": {"b": _DELETED}}

        assert dcm._is_path_deleted(("a", "b")) is True

    def test_path_deleted_ancestor(self) -> None:
        """Returns True when ancestor is deleted."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": _DELETED}

        assert dcm._is_path_deleted(("a", "b", "c")) is True

    def test_path_partial_no_match(self) -> None:
        """Returns False when delete_layer has different path."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": {"x": _DELETED}}

        assert dcm._is_path_deleted(("a", "b")) is False

    def test_empty_path_not_deleted(self) -> None:
        """Empty path is never deleted."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": _DELETED}

        assert dcm._is_path_deleted(()) is False


class TestClearPathIn:
    """Tests for _clear_path_in."""

    def test_clears_existing_path(self) -> None:
        """_clear_path_in removes existing path."""
        dcm = utils.DeepChainMap()
        target: dict[str, _typing.Any] = {"a": {"b": {"c": 1}}}

        dcm._clear_path_in(target, ("a", "b", "c"))

        assert target == {"a": {"b": {}}}

    def test_clears_single_key(self) -> None:
        """_clear_path_in clears single-key path."""
        dcm = utils.DeepChainMap()
        target: dict[str, _typing.Any] = {"a": 1, "b": 2}

        dcm._clear_path_in(target, ("a",))

        assert target == {"b": 2}

    def test_noop_if_path_missing(self) -> None:
        """_clear_path_in is no-op if path doesn't exist."""
        dcm = utils.DeepChainMap()
        target: dict[str, _typing.Any] = {"a": 1}

        dcm._clear_path_in(target, ("x", "y", "z"))

        assert target == {"a": 1}

    def test_empty_path_does_nothing(self) -> None:
        """_clear_path_in with empty path is no-op."""
        dcm = utils.DeepChainMap()
        target: dict[str, _typing.Any] = {"a": 1}

        dcm._clear_path_in(target, ())

        assert target == {"a": 1}


class TestDeepMergeDicts:
    """Tests for _deep_merge_dicts."""

    def test_simple_merge(self) -> None:
        """Merges non-overlapping keys."""
        dcm = utils.DeepChainMap()

        result = dcm._deep_merge_dicts({"a": 1}, {"b": 2})

        assert result == {"a": 1, "b": 2}

    def test_override_wins(self) -> None:
        """Override values win for same key."""
        dcm = utils.DeepChainMap()

        result = dcm._deep_merge_dicts({"a": 1}, {"a": 2})

        assert result == {"a": 2}

    def test_nested_merge(self) -> None:
        """Nested dicts are merged recursively."""
        dcm = utils.DeepChainMap()
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"c": 3, "d": 4}}

        result = dcm._deep_merge_dicts(base, override)

        assert result == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_type_mismatch_override_wins(self) -> None:
        """Type mismatch: override wins."""
        dcm = utils.DeepChainMap()

        result = dcm._deep_merge_dicts({"a": {"nested": 1}}, {"a": "string"})

        assert result == {"a": "string"}

    def test_does_not_mutate_inputs(self) -> None:
        """Does not mutate base or override."""
        dcm = utils.DeepChainMap()
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}

        _ = dcm._deep_merge_dicts(base, override)

        assert base == {"a": {"b": 1}}
        assert override == {"a": {"c": 2}}


class TestDeletedSentinel:
    """Tests for _DELETED sentinel."""

    def test_deleted_repr(self) -> None:
        """_DELETED has readable repr."""
        assert repr(_DELETED) == "<DELETED>"

    def test_deleted_is_singleton(self) -> None:
        """_DELETED is same object when imported."""
        from brynhild.utils.deep_chain_map._core import _DELETED as d2
        assert _DELETED is d2


class TestMutableProxy:
    """Tests for MutableProxy dict wrapper."""

    def test_getitem_returns_value(self) -> None:
        """Can access values by key."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1, "b": 2})

        assert proxy["a"] == 1
        assert proxy["b"] == 2

    def test_getitem_missing_raises(self) -> None:
        """Missing key raises KeyError."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            _ = proxy["missing"]

    def test_getitem_deleted_raises(self) -> None:
        """Deleted key raises KeyError."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            _ = proxy["a"]

    def test_getitem_nested_dict_returns_proxy(self) -> None:
        """Nested dict returns another MutableProxy."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": {"b": 1}})

        nested = proxy["a"]

        assert isinstance(nested, MutableProxy)
        assert nested["b"] == 1

    def test_getitem_nested_list_returns_frozen(self) -> None:
        """Nested list returns FrozenSequence."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"items": [1, 2, 3]})

        items = proxy["items"]

        assert isinstance(items, FrozenSequence)
        assert list(items) == [1, 2, 3]

    def test_setitem_routes_to_front_layer(self) -> None:
        """Setting value routes to dcm._set_at_path."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, ("config",), {"existing": 1})

        proxy["new_key"] = "value"

        assert dcm._front_layer == {"config": {"new_key": "value"}}

    def test_setitem_deeply_nested(self) -> None:
        """Setting value through nested proxies works."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": {"b": {"c": 1}}})

        proxy["a"]["b"]["new"] = "deep"

        assert dcm._front_layer == {"a": {"b": {"new": "deep"}}}

    def test_delitem_routes_to_delete_layer(self) -> None:
        """Deleting marks key in delete_layer."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, ("config",), {"key": 1})

        del proxy["key"]

        assert dcm._delete_layer == {"config": {"key": _DELETED}}

    def test_delitem_missing_raises(self) -> None:
        """Deleting missing key raises KeyError."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            del proxy["missing"]

    def test_delitem_already_deleted_raises(self) -> None:
        """Deleting already-deleted key raises KeyError."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            del proxy["a"]

    def test_iter_excludes_deleted(self) -> None:
        """Iteration skips deleted keys."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"b": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1, "b": 2, "c": 3})

        keys = list(proxy)

        assert sorted(keys) == ["a", "c"]

    def test_len_excludes_deleted(self) -> None:
        """Length excludes deleted keys."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"b": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1, "b": 2, "c": 3})

        assert len(proxy) == 2

    def test_contains_respects_deletion(self) -> None:
        """'in' operator respects deletion."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"b": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1, "b": 2})

        assert "a" in proxy
        assert "b" not in proxy
        assert "missing" not in proxy

    def test_contains_non_string_returns_false(self) -> None:
        """'in' with non-string key returns False."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        assert 123 not in proxy  # type: ignore[operator]

    def test_repr(self) -> None:
        """repr shows content and path."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, ("config", "model"), {"name": "test"})

        result = repr(proxy)

        assert "MutableProxy" in result
        assert "name" in result
        assert "config.model" in result

    def test_repr_root_path(self) -> None:
        """repr shows <root> for empty path."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        result = repr(proxy)

        assert "<root>" in result

    def test_eq_with_dict(self) -> None:
        """MutableProxy equals dict with same visible content."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"b": _DELETED}
        proxy = MutableProxy(dcm, (), {"a": 1, "b": 2})

        assert proxy == {"a": 1}

    def test_eq_with_proxy(self) -> None:
        """MutableProxy equals another proxy with same content."""
        dcm = utils.DeepChainMap()
        proxy1 = MutableProxy(dcm, (), {"a": 1})
        proxy2 = MutableProxy(dcm, (), {"a": 1})

        assert proxy1 == proxy2

    def test_eq_with_non_mapping(self) -> None:
        """MutableProxy compared to non-Mapping returns NotImplemented."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        # Comparison with non-Mapping should return NotImplemented
        # which Python interprets as inequality (unless reflected op succeeds)
        assert not (proxy == "string")
        assert not (proxy == 123)
        assert not (proxy == [1, 2, 3])

    def test_not_hashable(self) -> None:
        """MutableProxy is not hashable."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(TypeError, match="unhashable"):
            hash(proxy)

    def test_getitem_non_string_key_raises(self) -> None:
        """Non-string key raises KeyError (key not found)."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            _ = proxy[123]

    def test_setitem_non_string_key_raises(self) -> None:
        """Non-string key in setitem raises TypeError."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, ("config",), {"a": 1})

        with _pytest.raises(TypeError, match="Path components must be strings"):
            proxy[123] = "value"  # type: ignore[index]

    def test_delitem_non_string_key_raises(self) -> None:
        """Non-string key in delitem raises KeyError (key not found)."""
        dcm = utils.DeepChainMap()
        proxy = MutableProxy(dcm, (), {"a": 1})

        with _pytest.raises(KeyError):
            del proxy[123]


class TestNestedProxyOperations:
    """Tests for nested dict operations via MutableProxy."""

    def test_nested_delete(self) -> None:
        """Can delete nested key via proxy chain: del dcm['a']['b']."""
        dcm = utils.DeepChainMap({"a": {"b": 1, "c": 2}})

        del dcm["a"]["b"]

        assert "b" not in dcm["a"]
        assert dcm["a"]["c"] == 2

    def test_deeply_nested_delete(self) -> None:
        """Can delete deeply nested key: del dcm['a']['b']['c']['d']."""
        dcm = utils.DeepChainMap({"a": {"b": {"c": {"d": 1, "e": 2}}}})

        del dcm["a"]["b"]["c"]["d"]

        assert "d" not in dcm["a"]["b"]["c"]
        assert dcm["a"]["b"]["c"]["e"] == 2

    def test_deeply_nested_set(self) -> None:
        """Can set deeply nested value: dcm['a']['b']['c']['d'] = x."""
        dcm = utils.DeepChainMap({"a": {"b": {"c": {"existing": 1}}}})

        dcm["a"]["b"]["c"]["new"] = "deep_value"

        assert dcm["a"]["b"]["c"]["new"] == "deep_value"
        assert dcm["a"]["b"]["c"]["existing"] == 1

    def test_nested_set_creates_path(self) -> None:
        """Setting nested value on empty DCM creates full path."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": {"b": {}}}

        # Access via proxy and set
        dcm["a"]["b"]["c"] = "value"

        assert dcm["a"]["b"]["c"] == "value"


class TestAddLayerPriority:
    """Tests for add_layer priority parameter."""

    def test_add_layer_default_highest_priority(self) -> None:
        """add_layer without priority adds at highest priority (index 0)."""
        dcm = utils.DeepChainMap({"key": "low"})
        dcm.add_layer({"key": "high"})

        assert dcm["key"] == "high"

    def test_add_layer_priority_zero_is_highest(self) -> None:
        """add_layer with priority=0 is highest priority."""
        dcm = utils.DeepChainMap({"key": "existing"})
        dcm.add_layer({"key": "new_highest"}, priority=0)

        assert dcm["key"] == "new_highest"

    def test_add_layer_priority_end_is_lowest(self) -> None:
        """add_layer at end of list is lowest priority."""
        dcm = utils.DeepChainMap({"key": "high"})
        dcm.add_layer({"key": "low"}, priority=1)

        assert dcm["key"] == "high"

    def test_add_layer_middle_priority(self) -> None:
        """add_layer in middle has correct priority."""
        dcm = utils.DeepChainMap({"key": "highest"}, {"key": "lowest"})
        dcm.add_layer({"key": "middle"}, priority=1)

        # After add: [highest, middle, lowest]
        assert len(dcm.source_layers) == 3
        assert dcm.source_layers[0]["key"] == "highest"
        assert dcm.source_layers[1]["key"] == "middle"
        assert dcm.source_layers[2]["key"] == "lowest"


class TestProvenanceWithFrontLayer:
    """Tests for get_with_provenance behavior with front_layer."""

    def test_provenance_source_only(self) -> None:
        """Provenance works for source-only values."""
        dcm = utils.DeepChainMap({"key": "value"}, track_provenance=True)

        value, prov = dcm.get_with_provenance("key")

        assert value == "value"
        # Scalar provenance uses '.' for the root value, layer 0
        assert prov == {".": 0}

    def test_provenance_front_layer_override(self) -> None:
        """Provenance for front_layer override shows -1 for overridden value."""
        dcm = utils.DeepChainMap({"key": "source"}, track_provenance=True)
        dcm["key"] = "front"

        value, prov = dcm.get_with_provenance("key")

        # Value comes from front_layer
        assert value == "front"
        # Front layer values have provenance -1
        assert prov == {".": -1}

    def test_provenance_front_only_value(self) -> None:
        """Provenance for value only in front_layer uses -1."""
        dcm = utils.DeepChainMap(track_provenance=True)
        dcm["new_key"] = "front_only"

        value, prov = dcm.get_with_provenance("new_key")

        assert value == "front_only"
        # Front layer values have provenance -1
        assert prov == {".": -1}

    def test_provenance_not_enabled_raises(self) -> None:
        """get_with_provenance without track_provenance raises RuntimeError."""
        dcm = utils.DeepChainMap({"key": "value"})

        with _pytest.raises(RuntimeError, match="Provenance tracking not enabled"):
            dcm.get_with_provenance("key")


class TestRemoveLayerEdgeCases:
    """Tests for remove_layer edge cases."""

    def test_remove_layer_returns_removed(self) -> None:
        """remove_layer returns the removed layer."""
        original = {"key": "value"}
        dcm = utils.DeepChainMap(original, {"other": 1})

        removed = dcm.remove_layer(0)

        assert removed is original

    def test_remove_layer_updates_priority(self) -> None:
        """After remove, remaining layers shift priority."""
        dcm = utils.DeepChainMap({"key": "first"}, {"key": "second"})
        dcm.remove_layer(0)

        # Now "second" is highest priority
        assert dcm["key"] == "second"

    def test_remove_last_layer(self) -> None:
        """Can remove the last (only) source layer."""
        dcm = utils.DeepChainMap({"key": "only"})
        dcm.remove_layer(0)

        assert len(dcm.source_layers) == 0
        assert "key" not in dcm


class TestEmptyDeepChainMap:
    """Tests for operations on empty DeepChainMap."""

    def test_empty_getitem_raises(self) -> None:
        """Empty DCM raises KeyError on access."""
        dcm = utils.DeepChainMap()

        with _pytest.raises(KeyError):
            _ = dcm["missing"]

    def test_empty_setitem_works(self) -> None:
        """Can set item on empty DCM."""
        dcm = utils.DeepChainMap()

        dcm["key"] = "value"

        assert dcm["key"] == "value"
        assert dcm._front_layer == {"key": "value"}

    def test_empty_delitem_raises(self) -> None:
        """Deleting from empty DCM raises KeyError."""
        dcm = utils.DeepChainMap()

        with _pytest.raises(KeyError):
            del dcm["missing"]

    def test_empty_iter(self) -> None:
        """Iterating empty DCM yields nothing."""
        dcm = utils.DeepChainMap()

        assert list(dcm) == []

    def test_empty_len(self) -> None:
        """Empty DCM has length 0."""
        dcm = utils.DeepChainMap()

        assert len(dcm) == 0

    def test_empty_contains(self) -> None:
        """Empty DCM contains nothing."""
        dcm = utils.DeepChainMap()

        assert "anything" not in dcm

    def test_empty_to_dict(self) -> None:
        """to_dict on empty DCM returns empty dict."""
        dcm = utils.DeepChainMap()

        assert dcm.to_dict() == {}


class TestListOperations:
    """Tests for list operation dataclasses."""

    def test_apply_setitem(self) -> None:
        """SetItem replaces value at index."""
        base = [1, 2, 3]
        ops = [_operations.SetItem(1, 99)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 99, 3]
        assert base == [1, 2, 3]  # Original unchanged

    def test_apply_delitem(self) -> None:
        """DelItem removes value at index."""
        base = [1, 2, 3]
        ops = [_operations.DelItem(1)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 3]

    def test_apply_append(self) -> None:
        """Append adds value to end."""
        base = [1, 2]
        ops = [_operations.Append(3)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 2, 3]

    def test_apply_insert(self) -> None:
        """Insert adds value at index."""
        base = [1, 3]
        ops = [_operations.Insert(1, 2)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 2, 3]

    def test_apply_extend(self) -> None:
        """Extend adds multiple values."""
        base = [1]
        ops = [_operations.Extend((2, 3, 4))]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 2, 3, 4]

    def test_apply_clear(self) -> None:
        """Clear removes all values."""
        base = [1, 2, 3]
        ops = [_operations.Clear()]

        result = _operations.apply_operations(base, ops)

        assert result == []

    def test_apply_pop(self) -> None:
        """Pop removes item at index."""
        base = [1, 2, 3]
        ops = [_operations.Pop(-1)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 2]

    def test_apply_remove(self) -> None:
        """Remove removes first occurrence of value."""
        base = [1, 2, 3, 2]
        ops = [_operations.Remove(2)]

        result = _operations.apply_operations(base, ops)

        assert result == [1, 3, 2]

    def test_apply_multiple_operations(self) -> None:
        """Multiple operations applied in order."""
        base = [1, 2, 3]
        ops = [
            _operations.Append(4),
            _operations.SetItem(0, 0),
            _operations.DelItem(1),
        ]

        result = _operations.apply_operations(base, ops)

        # [1,2,3] -> [1,2,3,4] -> [0,2,3,4] -> [0,3,4]
        assert result == [0, 3, 4]

    def test_apply_unknown_op_raises(self) -> None:
        """Unknown op type raises TypeError."""

        class BadOp(_operations.ListOp):
            pass

        with _pytest.raises(TypeError, match="Unknown ListOp"):
            _operations.apply_operations([1], [BadOp()])


class TestListOpMethods:
    """Tests for DeepChainMap list operation methods."""

    def test_own_list_copies_to_front(self) -> None:
        """own_list copies list to front_layer."""
        dcm = utils.DeepChainMap({"items": [1, 2, 3]})

        dcm.own_list(("items",))

        assert dcm._front_layer == {"items": [1, 2, 3]}
        # Original layer unchanged
        assert dcm._layers[0]["items"] == [1, 2, 3]

    def test_own_list_not_list_raises(self) -> None:
        """own_list on non-list raises TypeError."""
        dcm = utils.DeepChainMap({"value": "string"})

        with _pytest.raises(TypeError, match="not a list"):
            dcm.own_list(("value",))

    def test_own_list_missing_raises(self) -> None:
        """own_list on missing path raises KeyError."""
        dcm = utils.DeepChainMap({})

        with _pytest.raises(KeyError):
            dcm.own_list(("missing",))

    def test_list_append_stores_op(self) -> None:
        """list_append stores Append operation."""
        dcm = utils.DeepChainMap({"items": [1, 2]})

        dcm.list_append(("items",), 3)

        assert ("items",) in dcm._list_ops
        ops = dcm._list_ops[("items",)]
        assert len(ops) == 1
        assert isinstance(ops[0], _operations.Append)
        assert ops[0].value == 3

    def test_list_extend_stores_op(self) -> None:
        """list_extend stores Extend operation."""
        dcm = utils.DeepChainMap()

        dcm.list_extend(("items",), [3, 4, 5])

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.Extend)
        assert ops[0].values == (3, 4, 5)

    def test_list_insert_stores_op(self) -> None:
        """list_insert stores Insert operation."""
        dcm = utils.DeepChainMap()

        dcm.list_insert(("items",), 0, "first")

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.Insert)
        assert ops[0].index == 0
        assert ops[0].value == "first"

    def test_list_setitem_stores_op(self) -> None:
        """list_setitem stores SetItem operation."""
        dcm = utils.DeepChainMap()

        dcm.list_setitem(("items",), 2, "new")

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.SetItem)
        assert ops[0].index == 2
        assert ops[0].value == "new"

    def test_list_delitem_stores_op(self) -> None:
        """list_delitem stores DelItem operation."""
        dcm = utils.DeepChainMap()

        dcm.list_delitem(("items",), 1)

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.DelItem)
        assert ops[0].index == 1

    def test_list_pop_stores_op(self) -> None:
        """list_pop stores Pop operation."""
        dcm = utils.DeepChainMap()

        dcm.list_pop(("items",))

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.Pop)
        assert ops[0].index == -1

    def test_list_remove_stores_op(self) -> None:
        """list_remove stores Remove operation."""
        dcm = utils.DeepChainMap()

        dcm.list_remove(("items",), "value")

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.Remove)
        assert ops[0].value == "value"

    def test_list_clear_stores_op(self) -> None:
        """list_clear stores Clear operation."""
        dcm = utils.DeepChainMap()

        dcm.list_clear(("items",))

        ops = dcm._list_ops[("items",)]
        assert isinstance(ops[0], _operations.Clear)

    def test_multiple_ops_accumulate(self) -> None:
        """Multiple operations on same path accumulate."""
        dcm = utils.DeepChainMap()

        dcm.list_append(("items",), 1)
        dcm.list_append(("items",), 2)
        dcm.list_pop(("items",))

        ops = dcm._list_ops[("items",)]
        assert len(ops) == 3

    def test_list_ops_clear_cache(self) -> None:
        """List operations clear cache."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        _ = dcm["items"]  # Populate cache
        assert "items" in dcm._cache

        dcm.list_append(("items",), 3)

        assert dcm._cache == {}


class TestReprV2:
    """Tests for updated __repr__."""

    def test_repr_shows_front_layer(self) -> None:
        """repr includes front_layer when non-empty."""
        dcm = utils.DeepChainMap({"a": 1})
        dcm["b"] = 2  # Write to front_layer

        result = repr(dcm)

        assert "front=" in result
        assert "'b'" in result

    def test_repr_shows_delete_layer(self) -> None:
        """repr includes delete_layer when non-empty."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]  # Delete to delete_layer

        result = repr(dcm)

        assert "deleted=" in result

    def test_repr_shows_list_ops(self) -> None:
        """repr shows list_ops count when non-empty."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_append(("items",), 3)

        result = repr(dcm)

        assert "list_ops=" in result
        assert "1 paths" in result


class TestOwnListClearsOps:
    """Test that own_list clears pending list_ops."""

    def test_own_list_clears_pending_ops(self) -> None:
        """own_list removes pending operations for the path."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_append(("items",), 3)
        assert ("items",) in dcm._list_ops

        dcm.own_list(("items",))

        assert ("items",) not in dcm._list_ops
        assert dcm._front_layer["items"] == [1, 2, 3]


class TestDeletedKeyAccess:
    """Test accessing deleted keys."""

    def test_getitem_on_deleted_raises(self) -> None:
        """Accessing deleted key raises KeyError."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]

        with _pytest.raises(KeyError):
            _ = dcm["a"]


class TestContainsNonString:
    """Test __contains__ with non-string keys."""

    def test_contains_non_string_returns_false(self) -> None:
        """Non-string key returns False for 'in' operator."""
        dcm = utils.DeepChainMap({"a": 1})

        assert 123 not in dcm  # type: ignore[operator]
        assert ["a"] not in dcm  # type: ignore[operator]


class TestIsPathDeletedEdgeCases:
    """Edge cases for _is_path_deleted."""

    def test_non_dict_intermediate(self) -> None:
        """Non-dict value in path returns False."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": "not_a_dict"}

        # "a" contains a string, not a dict, so path a.b cannot be checked
        assert dcm._is_path_deleted(("a", "b")) is False


class TestGetMutable:
    """Tests for get_mutable() method."""

    def test_get_mutable_returns_dict(self) -> None:
        """get_mutable returns plain dict, not proxy."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})

        result = dcm.get_mutable("a")

        assert isinstance(result, dict)
        assert result == {"b": 1}

    def test_get_mutable_is_deep_copy(self) -> None:
        """get_mutable returns independent copy."""
        dcm = utils.DeepChainMap({"a": {"b": {"c": 1}}})

        result = dcm.get_mutable("a")
        result["b"]["c"] = 999  # Mutate the copy

        # DCM unchanged
        assert dcm["a"]["b"]["c"] == 1

    def test_get_mutable_missing_raises(self) -> None:
        """get_mutable raises KeyError for missing key."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(KeyError):
            dcm.get_mutable("missing")


class TestFrontLayerIntegration:
    """Tests for front_layer integration with reads."""

    def test_key_only_in_front_layer(self) -> None:
        """Key only in front_layer is accessible."""
        dcm = utils.DeepChainMap({"source": 1})
        dcm["front_only"] = 42

        assert dcm["front_only"] == 42
        assert "front_only" in dcm

    def test_front_layer_overrides_source(self) -> None:
        """Front layer value takes priority over source."""
        dcm = utils.DeepChainMap({"key": "source_value"})
        dcm["key"] = "front_value"

        assert dcm["key"] == "front_value"

    def test_front_layer_merges_nested_with_source(self) -> None:
        """Front layer nested dict merges with source."""
        dcm = utils.DeepChainMap({"config": {"a": 1, "b": 2}})
        dcm["config"] = {"b": 99, "c": 3}

        result = dcm["config"]
        assert result["a"] == 1   # From source
        assert result["b"] == 99  # From front (overrides)
        assert result["c"] == 3   # From front (new key)

    def test_iter_includes_front_layer_keys(self) -> None:
        """Iteration includes keys only in front_layer."""
        dcm = utils.DeepChainMap({"source": 1})
        dcm["front"] = 2

        keys = list(dcm)
        assert "source" in keys
        assert "front" in keys

    def test_len_includes_front_layer_keys(self) -> None:
        """Length includes front_layer-only keys."""
        dcm = utils.DeepChainMap({"a": 1})
        dcm["b"] = 2

        assert len(dcm) == 2

    def test_contains_front_layer_only_key(self) -> None:
        """'in' works for front_layer-only keys."""
        dcm = utils.DeepChainMap()
        dcm["front_only"] = 1

        assert "front_only" in dcm


class TestDeleteAndAddLayer:
    """Tests for delete + add_layer interaction."""

    def test_delete_then_add_layer_key_still_deleted(self) -> None:
        """Adding layer doesn't resurrect deleted key."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]
        dcm.add_layer({"a": "new"})

        # Still deleted because delete_layer takes precedence
        assert "a" not in dcm

    def test_delete_then_clear_delete_layer_then_add(self) -> None:
        """After clearing delete_layer, added layer is visible."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]
        dcm.clear_delete_layer()
        dcm.add_layer({"a": "resurrected"})

        assert dcm["a"] == "resurrected"

    def test_delete_nested_overwrites_intermediate_marker(self) -> None:
        """Deleting nested path overwrites intermediate _DELETED marker with dict."""
        dcm = utils.DeepChainMap({"a": {"b": {"c": 1}}})

        # First delete "a.b" - creates {"a": {"b": _DELETED}}
        del dcm["a"]["b"]
        assert dcm._delete_layer == {"a": {"b": _DELETED}}

        # Now delete "a.b.c" - should replace _DELETED with dict
        dcm._delete_at_path(("a", "b", "c"))

        # "a.b" now points to dict, not _DELETED
        assert dcm._delete_layer == {"a": {"b": {"c": _DELETED}}}
        # But "a.b" itself is no longer marked deleted
        assert not dcm._is_path_deleted(("a", "b"))
        assert dcm._is_path_deleted(("a", "b", "c"))


class TestSetAfterDelete:
    """Tests for set-after-delete semantics."""

    def test_set_after_delete_restores_key(self) -> None:
        """Setting a deleted key restores it."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]
        assert "a" not in dcm

        dcm["a"] = "new_value"
        assert "a" in dcm
        assert dcm["a"] == "new_value"

    def test_set_after_delete_clears_delete_marker(self) -> None:
        """Setting after delete removes the delete marker."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]
        assert ("a",) in [tuple([k]) for k in dcm._delete_layer.keys() if dcm._delete_layer[k] is _DELETED]

        dcm["a"] = "restored"
        assert "a" not in dcm._delete_layer or dcm._delete_layer.get("a") is not _DELETED


class TestListOpsOnRead:
    """Tests for list operations being applied on read."""

    def test_list_append_visible_on_read(self) -> None:
        """list_append operation is applied when reading."""
        dcm = utils.DeepChainMap({"items": [1, 2, 3]})
        dcm.list_append(("items",), 4)

        result = dcm["items"]
        assert list(result) == [1, 2, 3, 4]

    def test_multiple_list_ops_applied_in_order(self) -> None:
        """Multiple operations applied in sequence."""
        dcm = utils.DeepChainMap({"items": [1, 2, 3]})
        dcm.list_append(("items",), 4)
        dcm.list_setitem(("items",), 0, 0)

        result = dcm["items"]
        # [1,2,3] -> [1,2,3,4] -> [0,2,3,4]
        assert list(result) == [0, 2, 3, 4]

    def test_nested_list_ops(self) -> None:
        """List ops work on nested paths."""
        dcm = utils.DeepChainMap({"config": {"plugins": ["a", "b"]}})
        dcm.list_append(("config", "plugins"), "c")

        result = dcm["config"]["plugins"]
        assert list(result) == ["a", "b", "c"]


class TestToDictWithFullState:
    """Tests for to_dict with front_layer, delete_layer, list_ops."""

    def test_to_dict_includes_front_layer(self) -> None:
        """to_dict includes front_layer values."""
        dcm = utils.DeepChainMap({"source": 1})
        dcm["front"] = 2

        result = dcm.to_dict()

        assert result == {"source": 1, "front": 2}

    def test_to_dict_excludes_deleted(self) -> None:
        """to_dict excludes deleted keys."""
        dcm = utils.DeepChainMap({"a": 1, "b": 2})
        del dcm["a"]

        result = dcm.to_dict()

        assert result == {"b": 2}

    def test_to_dict_applies_list_ops(self) -> None:
        """to_dict includes list operations."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_append(("items",), 3)

        result = dcm.to_dict()

        assert result["items"] == [1, 2, 3]

    def test_to_dict_full_integration(self) -> None:
        """to_dict with all 2.0 features active."""
        dcm = utils.DeepChainMap(
            {"a": 1, "b": 2, "items": [1], "config": {"x": 10}},
        )
        dcm["c"] = 3                            # front_layer
        dcm["config"]["y"] = 20                 # nested front_layer
        del dcm["a"]                            # delete_layer
        dcm.list_append(("items",), 2)          # list_ops

        result = dcm.to_dict()

        assert "a" not in result                # Deleted
        assert result["b"] == 2                 # Source
        assert result["c"] == 3                 # Front
        assert result["config"]["x"] == 10     # Source nested
        assert result["config"]["y"] == 20     # Front nested
        assert result["items"] == [1, 2]       # List ops applied


class TestReloadPreservesUserState:
    """Tests that reload() only clears cache."""

    def test_reload_preserves_front_layer(self) -> None:
        """reload() doesn't clear front_layer."""
        dcm = utils.DeepChainMap({"source": 1})
        dcm["front"] = 2
        dcm.reload()

        assert dcm["front"] == 2

    def test_reload_preserves_delete_layer(self) -> None:
        """reload() doesn't clear delete_layer."""
        dcm = utils.DeepChainMap({"a": 1})
        del dcm["a"]
        dcm.reload()

        assert "a" not in dcm

    def test_reload_preserves_list_ops(self) -> None:
        """reload() doesn't clear list_ops."""
        dcm = utils.DeepChainMap({"items": [1]})
        dcm.list_append(("items",), 2)
        dcm.reload()

        assert list(dcm["items"]) == [1, 2]


class TestDeleteKeyOnlyInFrontLayer:
    """Tests for deleting keys that only exist in front_layer."""

    def test_delete_front_only_key(self) -> None:
        """Can delete key that only exists in front_layer."""
        dcm = utils.DeepChainMap()
        dcm["front_only"] = 1
        assert "front_only" in dcm

        del dcm["front_only"]

        assert "front_only" not in dcm


class TestGetAtPath:
    """Tests for _get_at_path helper."""

    def test_single_key(self) -> None:
        """Get value at single key path."""
        dcm = utils.DeepChainMap({"a": 42})

        result = dcm._get_at_path(("a",))

        assert result == 42

    def test_nested_path(self) -> None:
        """Get value at nested path."""
        dcm = utils.DeepChainMap({"a": {"b": {"c": "deep"}}})

        result = dcm._get_at_path(("a", "b", "c"))

        assert result == "deep"

    def test_empty_path_raises(self) -> None:
        """Empty path raises KeyError."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(KeyError, match="Empty path"):
            dcm._get_at_path(())

    def test_missing_key_raises(self) -> None:
        """Missing key raises KeyError."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(KeyError):
            dcm._get_at_path(("missing",))

    def test_non_dict_intermediate_raises(self) -> None:
        """Non-dict intermediate raises KeyError."""
        dcm = utils.DeepChainMap({"a": "string"})

        with _pytest.raises(KeyError, match="non-dict"):
            dcm._get_at_path(("a", "b"))


class TestLayerManagementV2:
    """Tests for 2.0 layer management features."""

    def test_source_layers_property(self) -> None:
        """source_layers returns frozen wrappers of source data."""
        from brynhild.utils.deep_chain_map._frozen import FrozenMapping

        layer0 = {"a": 1}
        layer1 = {"b": 2}
        dcm = utils.DeepChainMap(layer0, layer1)

        # Returns FrozenMapping wrappers
        assert isinstance(dcm.source_layers[0], FrozenMapping)
        assert isinstance(dcm.source_layers[1], FrozenMapping)
        # Content is equal
        assert dcm.source_layers[0] == layer0
        assert dcm.source_layers[1] == layer1

    def test_front_layer_property(self) -> None:
        """front_layer returns the front layer dict."""
        dcm = utils.DeepChainMap()
        dcm._set_at_path(("a",), 1)

        assert dcm.front_layer == {"a": 1}

    def test_delete_layer_property(self) -> None:
        """delete_layer returns the delete layer dict."""
        dcm = utils.DeepChainMap({"a": 1})
        dcm._delete_at_path(("a",))

        assert dcm.delete_layer == {"a": _DELETED}

    def test_list_ops_property(self) -> None:
        """list_ops returns the list operations dict."""
        dcm = utils.DeepChainMap()
        dcm.list_append(("items",), 1)

        assert ("items",) in dcm.list_ops
        assert len(dcm.list_ops[("items",)]) == 1


class TestClearingMethods:
    """Tests for clearing methods."""

    def test_clear_front_layer(self) -> None:
        """clear_front_layer empties front_layer."""
        dcm = utils.DeepChainMap()
        dcm._front_layer = {"a": 1, "b": 2}

        dcm.clear_front_layer()

        assert dcm._front_layer == {}

    def test_clear_front_layer_clears_cache(self) -> None:
        """clear_front_layer clears cache."""
        dcm = utils.DeepChainMap({"a": 1})
        _ = dcm["a"]
        assert "a" in dcm._cache

        dcm.clear_front_layer()

        assert dcm._cache == {}

    def test_clear_delete_layer(self) -> None:
        """clear_delete_layer empties delete_layer."""
        dcm = utils.DeepChainMap()
        dcm._delete_layer = {"a": _DELETED}

        dcm.clear_delete_layer()

        assert dcm._delete_layer == {}

    def test_clear_list_ops(self) -> None:
        """clear_list_ops empties list_ops."""
        dcm = utils.DeepChainMap()
        dcm._list_ops = {("a",): [_operations.Append(1)]}

        dcm.clear_list_ops()

        assert dcm._list_ops == {}

    def test_reset_clears_all(self) -> None:
        """reset clears front_layer, delete_layer, list_ops, and cache."""
        dcm = utils.DeepChainMap({"a": 1})
        dcm._front_layer = {"b": 2}
        dcm._delete_layer = {"c": _DELETED}
        dcm._list_ops = {("d",): [_operations.Append(3)]}
        _ = dcm["a"]

        dcm.reset()

        assert dcm._front_layer == {}
        assert dcm._delete_layer == {}
        assert dcm._list_ops == {}
        assert dcm._cache == {}

    def test_reset_preserves_source_layers(self) -> None:
        """reset does not modify source layers."""
        layer = {"a": 1}
        dcm = utils.DeepChainMap(layer)
        dcm._front_layer = {"b": 2}

        dcm.reset()

        assert dcm._layers[0] is layer
        assert layer == {"a": 1}


class TestReorderLayers:
    """Tests for reorder_layers."""

    def test_reorder_reverses(self) -> None:
        """reorder_layers can reverse layer order."""
        dcm = utils.DeepChainMap({"a": "first"}, {"a": "second"}, {"a": "third"})

        dcm.reorder_layers([2, 1, 0])

        assert dcm["a"] == "third"  # Now first

    def test_reorder_rotates(self) -> None:
        """reorder_layers can rotate layers."""
        layer0 = {"id": 0}
        layer1 = {"id": 1}
        layer2 = {"id": 2}
        dcm = utils.DeepChainMap(layer0, layer1, layer2)

        dcm.reorder_layers([1, 2, 0])

        assert dcm._layers[0] is layer1
        assert dcm._layers[1] is layer2
        assert dcm._layers[2] is layer0

    def test_reorder_clears_cache(self) -> None:
        """reorder_layers clears cache."""
        dcm = utils.DeepChainMap({"a": 1})
        _ = dcm["a"]
        assert "a" in dcm._cache

        dcm.reorder_layers([0])

        assert dcm._cache == {}

    def test_reorder_invalid_missing_index(self) -> None:
        """reorder_layers raises on missing index."""
        dcm = utils.DeepChainMap({"a": 1}, {"b": 2})

        with _pytest.raises(ValueError, match="each index"):
            dcm.reorder_layers([0, 0])  # Missing 1

    def test_reorder_invalid_extra_index(self) -> None:
        """reorder_layers raises on extra index."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(ValueError, match="each index"):
            dcm.reorder_layers([0, 1])  # 1 doesn't exist

    def test_reorder_empty(self) -> None:
        """reorder_layers works with empty list."""
        dcm = utils.DeepChainMap()

        dcm.reorder_layers([])

        assert dcm._layers == []


class TestCopyMethod:
    """Tests for copy() method."""

    def test_copy_returns_new_instance(self) -> None:
        """copy() returns a different object."""
        dcm = utils.DeepChainMap({"a": 1})

        copied = dcm.copy()

        assert copied is not dcm

    def test_copy_shares_source_layers(self) -> None:
        """copy() shares references to source layers."""
        layer = {"a": 1}
        dcm = utils.DeepChainMap(layer)

        copied = dcm.copy()

        assert copied._layers[0] is layer

    def test_copy_has_independent_front_layer(self) -> None:
        """copy() has its own front_layer."""
        dcm = utils.DeepChainMap({"a": 1})
        dcm["b"] = 2

        copied = dcm.copy()
        copied["c"] = 3

        assert "c" in copied
        assert "c" not in dcm
        assert "b" in copied  # Copied from original

    def test_copy_has_independent_delete_layer(self) -> None:
        """copy() has its own delete_layer."""
        dcm = utils.DeepChainMap({"a": 1, "b": 2})
        del dcm["a"]

        copied = dcm.copy()
        del copied["b"]

        assert "a" not in dcm
        assert "b" in dcm  # Not deleted in original
        assert "a" not in copied
        assert "b" not in copied

    def test_copy_has_independent_list_ops(self) -> None:
        """copy() has its own list_ops."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_append(("items",), 3)

        copied = dcm.copy()
        copied.list_append(("items",), 4)

        assert list(dcm["items"]) == [1, 2, 3]
        assert list(copied["items"]) == [1, 2, 3, 4]

    def test_copy_preserves_settings(self) -> None:
        """copy() preserves track_provenance setting."""
        dcm = utils.DeepChainMap({"a": 1}, track_provenance=True)

        copied = dcm.copy()

        assert copied._track_provenance is True


class TestPickle2_0State:
    """Tests for pickle with 2.0 state."""

    def test_pickle_preserves_front_layer(self) -> None:
        """Pickle roundtrip preserves front_layer values."""
        import pickle as _pickle

        dcm = utils.DeepChainMap({"source": 1})
        dcm["front"] = 2

        restored = _pickle.loads(_pickle.dumps(dcm))

        assert restored["front"] == 2
        assert restored._front_layer == {"front": 2}

    def test_pickle_preserves_delete_layer(self) -> None:
        """Pickle roundtrip preserves deletion markers."""
        import pickle as _pickle

        dcm = utils.DeepChainMap({"a": 1, "b": 2})
        del dcm["a"]

        restored = _pickle.loads(_pickle.dumps(dcm))

        assert "a" not in restored
        assert restored["b"] == 2

    def test_pickle_preserves_list_ops(self) -> None:
        """Pickle roundtrip preserves list operations."""
        import pickle as _pickle

        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_append(("items",), 3)

        restored = _pickle.loads(_pickle.dumps(dcm))

        assert list(restored["items"]) == [1, 2, 3]

    def test_pickle_full_state(self) -> None:
        """Pickle preserves all 2.0 state together."""
        import pickle as _pickle

        dcm = utils.DeepChainMap(
            {"a": 1, "b": 2, "items": [1], "config": {"x": 10}},
        )
        dcm["c"] = 3
        dcm["config"]["y"] = 20
        del dcm["a"]
        dcm.list_append(("items",), 2)

        restored = _pickle.loads(_pickle.dumps(dcm))

        assert "a" not in restored
        assert restored["b"] == 2
        assert restored["c"] == 3
        assert restored["config"]["x"] == 10
        assert restored["config"]["y"] == 20
        assert list(restored["items"]) == [1, 2]


class TestPathValidation:
    """Tests for path component type validation."""

    def test_set_at_path_non_string_raises(self) -> None:
        """_set_at_path with non-string path raises TypeError."""
        dcm = utils.DeepChainMap()

        with _pytest.raises(TypeError, match="Path components must be strings"):
            dcm._set_at_path(("a", 123, "c"), "value")  # type: ignore[arg-type]

    def test_delete_at_path_non_string_raises(self) -> None:
        """_delete_at_path with non-string path raises TypeError."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})

        with _pytest.raises(TypeError, match="Path components must be strings"):
            dcm._delete_at_path(("a", 123))  # type: ignore[arg-type]


class TestProvenanceFrontLayer:
    """Tests for provenance tracking with front_layer values."""

    def test_provenance_front_only_dict(self) -> None:
        """Provenance for dict only in front_layer uses -1."""
        dcm = utils.DeepChainMap(track_provenance=True)
        dcm["config"] = {"a": 1, "b": 2}

        _, prov = dcm.get_with_provenance("config")

        assert prov == {"a": -1, "b": -1}

    def test_provenance_front_only_scalar(self) -> None:
        """Provenance for scalar only in front_layer uses -1."""
        dcm = utils.DeepChainMap(track_provenance=True)
        dcm["value"] = 42

        _, prov = dcm.get_with_provenance("value")

        assert prov == {".": -1}

    def test_provenance_front_overrides_source(self) -> None:
        """Front layer override shows -1 for overridden keys."""
        dcm = utils.DeepChainMap(
            {"config": {"a": 1, "b": 2}},
            track_provenance=True,
        )
        dcm["config"] = {"b": 99, "c": 3}

        _, prov = dcm.get_with_provenance("config")

        assert prov["a"] == 0   # From source layer 0
        assert prov["b"] == -1  # Overridden by front
        assert prov["c"] == -1  # New from front

    def test_provenance_front_replaces_scalar(self) -> None:
        """Front layer replacing source scalar shows -1."""
        dcm = utils.DeepChainMap(
            {"value": "source"},
            track_provenance=True,
        )
        dcm["value"] = "front"

        _, prov = dcm.get_with_provenance("value")

        assert prov == {".": -1}

