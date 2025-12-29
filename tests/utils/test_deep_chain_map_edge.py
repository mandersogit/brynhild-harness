"""
Edge case tests for DeepChainMap.

These tests verify robustness and document edge case behaviors that
may not be obvious from the basic tests. Organized by category per
the test plan in workflow/deep-chain-map-test-plan.md.
"""

import copy as _copy
import json as _json
import pickle as _pickle
import typing as _typing

import pytest as _pytest

import brynhild.utils as utils
import brynhild.utils.deep_chain_map as deep_chain_map
import brynhild.utils.deep_chain_map._frozen as _frozen

# Re-export for convenience in tests
FrozenMapping = _frozen.FrozenMapping


# =============================================================================
# Category 6: Cache Correctness (P0)
# =============================================================================


class TestCacheCorrectness:
    """Tests for cache behavior and invalidation.

    Cache bugs cause inconsistent behavior that's very hard to debug.
    These tests verify the caching contract is correct.
    """

    def test_cache_returns_equal_proxies(self) -> None:
        """Multiple accesses return proxies wrapping same cached data."""
        dcm = utils.DeepChainMap({"a": {"nested": 1}})

        result1 = dcm["a"]
        result2 = dcm["a"]

        # 2.0: MutableProxy objects are equal, underlying data is cached
        assert result1 == result2, (
            "Expected equal content on repeated access"
        )
        assert result1["nested"] == result2["nested"] == 1

    def test_cache_stale_after_layer_mutation(self) -> None:
        """Modifying layer in place returns stale cached value until reload."""
        data = {"a": 1}
        dcm = utils.DeepChainMap(data)

        # Populate cache
        result1 = dcm["a"]
        assert result1 == 1

        # Modify layer in place (without using DCM API)
        data["a"] = 999

        # Cache should be stale
        result2 = dcm["a"]
        assert result2 == 1, (
            "Cache should be stale — modification without reload() "
            "should return old cached value"
        )

    def test_reload_refreshes_cache(self) -> None:
        """reload() clears cache, causing re-merge on next access."""
        data = {"a": {"b": 1}}
        dcm = utils.DeepChainMap(data)

        result1 = dcm["a"]
        assert result1["b"] == 1

        # Modify and reload
        data["a"]["b"] = 2
        dcm.reload()

        result2 = dcm["a"]
        assert result2["b"] == 2, (
            "After reload(), cache should be cleared and value re-merged"
        )
        assert result1 is not result2, "Should be different objects after reload"

    def test_cache_isolation_from_caller_mutation(self) -> None:
        """Caller mutating returned value also mutates cache (shared reference).

        This documents current behavior — callers should NOT mutate returned
        values if they want consistent behavior. Consider this a known
        limitation for performance.
        """
        dcm = utils.DeepChainMap({"a": {"nested": "original"}})

        result = dcm["a"]
        result["nested"] = "mutated"

        # Cache is also mutated because result IS the cached object
        assert dcm["a"]["nested"] == "mutated", (
            "Cache should be mutated when caller mutates returned value "
            "(they share the same object reference)"
        )

    def test_setitem_clears_all_cache(self) -> None:
        """Setting any key clears entire cache."""
        dcm = utils.DeepChainMap(
            {"a": {"from": "layer0"}, "b": {"from": "layer0"}},
            {"a": {"extra": "layer1"}, "b": {"extra": "layer1"}},
        )

        # Populate cache for both keys
        result_a = dcm["a"]
        result_b = dcm["b"]

        # Set a different key
        dcm["c"] = "new"

        # Both caches should be cleared
        new_a = dcm["a"]
        new_b = dcm["b"]

        assert new_a is not result_a, "Cache for 'a' should be cleared after setitem"
        assert new_b is not result_b, "Cache for 'b' should be cleared after setitem"

    def test_add_layer_clears_cache(self) -> None:
        """add_layer() clears cache."""
        dcm = utils.DeepChainMap({"a": "original"})

        result1 = dcm["a"]
        dcm.add_layer({"a": "new_priority"})
        result2 = dcm["a"]

        assert result2 == "new_priority"
        assert result1 is not result2, "Cache should be cleared after add_layer"

    def test_remove_layer_clears_cache(self) -> None:
        """remove_layer() clears cache."""
        layer0 = {"a": "high"}
        layer1 = {"a": "low"}
        dcm = utils.DeepChainMap(layer0, layer1)

        result1 = dcm["a"]
        assert result1 == "high"

        dcm.remove_layer(0)
        result2 = dcm["a"]

        assert result2 == "low"
        assert result1 is not result2, "Cache should be cleared after remove_layer"


# =============================================================================
# Category 1: Empty and None Values (P0)
# =============================================================================


class TestEmptyAndNoneValues:
    """Tests for empty dict, None, and empty string edge cases.

    Config files commonly have empty sections or explicit null values.
    These tests verify the merge semantics are correct.
    """

    def test_none_overrides_value(self) -> None:
        """Higher priority None overrides lower priority value."""
        dcm = utils.DeepChainMap({"a": None}, {"a": 1})

        assert dcm["a"] is None, (
            "Expected None to override 1 (None is a valid value, not 'unset')"
        )

    def test_value_overrides_none(self) -> None:
        """Higher priority value overrides lower priority None."""
        dcm = utils.DeepChainMap({"a": 1}, {"a": None})

        assert dcm["a"] == 1

    def test_empty_dict_merges_with_populated(self) -> None:
        """Empty dict in high priority merges with populated dict (doesn't replace)."""
        dcm = utils.DeepChainMap(
            {"a": {}},
            {"a": {"b": 1, "c": 2}},
        )

        result = dcm["a"]
        assert result == {"b": 1, "c": 2}, (
            "Empty dict should merge, not replace — keys from lower layer preserved"
        )

    def test_populated_merges_with_empty(self) -> None:
        """Populated dict in high priority merges with empty (preserves content)."""
        dcm = utils.DeepChainMap(
            {"a": {"b": 1}},
            {"a": {}},
        )

        result = dcm["a"]
        assert result == {"b": 1}

    def test_empty_string_key(self) -> None:
        """Empty string is a valid key."""
        dcm = utils.DeepChainMap({"": "empty_key_value", "normal": "value"})

        assert dcm[""] == "empty_key_value"
        assert "" in dcm
        assert len(dcm) == 2

    def test_none_vs_dict_type_mismatch(self) -> None:
        """None in high priority replaces dict (type mismatch)."""
        dcm = utils.DeepChainMap(
            {"a": None},
            {"a": {"b": 1, "c": 2}},
        )

        assert dcm["a"] is None, (
            "None should win over dict (type mismatch = higher priority wins)"
        )

    def test_no_layers(self) -> None:
        """DeepChainMap with no layers is empty."""
        dcm = utils.DeepChainMap()

        assert len(dcm) == 0
        assert list(dcm) == []
        assert "anything" not in dcm

        with _pytest.raises(KeyError):
            _ = dcm["anything"]


# =============================================================================
# Category 8: Mutation Edge Cases (P0)
# =============================================================================


class TestMutationEdgeCases:
    """Tests for setitem and delitem behavior.

    2.0: Mutations go to front_layer/delete_layer, source layers unchanged.
    """

    def test_setitem_writes_to_front_layer(self) -> None:
        """2.0: Setting a value goes to front_layer, not source layers."""
        dcm = utils.DeepChainMap()
        assert len(dcm.layers) == 0

        dcm["a"] = 1

        # No source layers created
        assert len(dcm.layers) == 0
        # Value in front_layer
        assert dcm.front_layer == {"a": 1}
        assert dcm["a"] == 1

    def test_delitem_marks_in_delete_layer(self) -> None:
        """2.0: Deleting marks in delete_layer, source layers unchanged."""
        layer0 = {"a": 1}
        layer1 = {"b": 2}
        dcm = utils.DeepChainMap(layer0, layer1)

        del dcm["b"]

        # Source layer unchanged
        assert layer1["b"] == 2
        # Deleted via delete_layer
        assert "b" not in dcm
        assert "a" in dcm  # Unaffected

    def test_delitem_multiple_layers_unchanged(self) -> None:
        """2.0: Deleting key doesn't modify source layers."""
        layer0 = {"a": 1, "shared": "from_0"}
        layer1 = {"b": 2}
        layer2 = {"c": 3, "shared": "from_2"}
        dcm = utils.DeepChainMap(layer0, layer1, layer2)

        del dcm["shared"]

        # Source layers unchanged
        assert layer0["shared"] == "from_0"
        assert layer2["shared"] == "from_2"
        # But not visible through dcm
        assert "shared" not in dcm

    def test_delitem_clears_cache(self) -> None:
        """Deleting a key clears cache."""
        dcm = utils.DeepChainMap({"a": 1, "b": {"nested": "value"}})

        result_b = dcm["b"]
        del dcm["a"]

        # Cache cleared, new proxies returned
        new_b = dcm["b"]
        assert new_b == result_b  # Equal content
        # Different proxy objects (cache was cleared)
        assert new_b is not result_b, "Cache should be cleared after delitem"


# =============================================================================
# Category 4: List Behavior Edge Cases (P0)
# =============================================================================


class TestListBehaviorEdgeCases:
    """Tests for list handling in merge.

    Lists always replace (higher priority wins). Use list_* methods for
    explicit operations like extend, append, etc.
    """

    def test_list_replace_higher_priority_wins(self) -> None:
        """Higher priority list completely replaces lower priority."""
        dcm = utils.DeepChainMap(
            {"items": [4, 5]},
            {"items": [1, 2, 3]},
        )

        assert list(dcm["items"]) == [4, 5], (
            "Higher priority list should completely replace lower"
        )

    def test_list_replace_empty_list(self) -> None:
        """Empty list in high priority replaces non-empty."""
        dcm = utils.DeepChainMap(
            {"items": []},
            {"items": [1, 2, 3]},
        )

        assert list(dcm["items"]) == [], (
            "Empty list should replace non-empty"
        )

    def test_list_with_none_elements(self) -> None:
        """Lists with None elements are replaced correctly."""
        dcm = utils.DeepChainMap(
            {"items": [None, 1]},
            {"items": [2, 3]},
        )

        assert list(dcm["items"]) == [None, 1], (
            "Higher priority list with None should replace"
        )

    def test_nested_list_in_dict_replaces(self) -> None:
        """Nested lists also replace, not merge."""
        dcm = utils.DeepChainMap(
            {"config": {"plugins": ["new"]}},
            {"config": {"plugins": ["builtin"], "other": "value"}},
        )

        result = dcm["config"]
        assert list(result["plugins"]) == ["new"], (
            "Nested list should replace, not merge"
        )
        assert result["other"] == "value"

    def test_list_extend_via_list_ops(self) -> None:
        """Use list_extend for explicit concatenation."""
        dcm = utils.DeepChainMap({"items": [1, 2]})
        dcm.list_extend(("items",), [3, 4])

        assert list(dcm["items"]) == [1, 2, 3, 4], (
            "list_extend should append items"
        )

    def test_list_ops_on_nested_path(self) -> None:
        """list_* methods work on nested paths."""
        dcm = utils.DeepChainMap({"config": {"plugins": ["builtin"]}})
        dcm.list_append(("config", "plugins"), "user_plugin")

        result = dcm["config"]
        assert list(result["plugins"]) == ["builtin", "user_plugin"]


# =============================================================================
# Category 2: Type Coercion Edge Cases (P1)
# =============================================================================


class TestTypeCoercionEdgeCases:
    """Tests for type mismatch handling during merge.

    When types differ between layers, higher priority always wins.
    """

    def test_dict_over_string(self) -> None:
        """Dict in high priority replaces string."""
        dcm = utils.DeepChainMap(
            {"a": {"nested": 1}},
            {"a": "string_value"},
        )

        assert dcm["a"] == {"nested": 1}

    def test_string_over_dict(self) -> None:
        """String in high priority replaces dict."""
        dcm = utils.DeepChainMap(
            {"a": "string_value"},
            {"a": {"nested": 1}},
        )

        assert dcm["a"] == "string_value"

    def test_list_over_scalar(self) -> None:
        """List in high priority replaces scalar."""
        dcm = utils.DeepChainMap(
            {"a": [1, 2, 3]},
            {"a": 42},
        )

        assert dcm["a"] == [1, 2, 3]

    def test_scalar_over_list(self) -> None:
        """Scalar in high priority replaces list."""
        dcm = utils.DeepChainMap(
            {"a": 42},
            {"a": [1, 2, 3]},
        )

        assert dcm["a"] == 42

    def test_bool_vs_int(self) -> None:
        """Bool in high priority replaces int (not merged despite bool being int subclass)."""
        dcm = utils.DeepChainMap(
            {"a": True},
            {"a": 1},
        )

        result = dcm["a"]
        assert result is True
        assert type(result) is bool  # noqa: E721 - intentionally checking exact type

    def test_float_vs_int(self) -> None:
        """Float in high priority replaces int."""
        dcm = utils.DeepChainMap(
            {"a": 1.5},
            {"a": 1},
        )

        assert dcm["a"] == 1.5

    def test_nested_type_mismatch(self) -> None:
        """Type mismatch at nested level: high priority wins at that point."""
        dcm = utils.DeepChainMap(
            {"config": {"setting": "string_now"}},
            {"config": {"setting": {"deeply": "nested"}, "other": "preserved"}},
        )

        result = dcm["config"]
        assert result["setting"] == "string_now"
        assert result["other"] == "preserved"


# =============================================================================
# Category 5: Provenance Edge Cases (P1)
# =============================================================================


class TestProvenanceEdgeCases:
    """Tests for provenance tracking edge cases."""

    def test_provenance_deeply_nested(self) -> None:
        """Provenance tracks at all nesting levels."""
        dcm = utils.DeepChainMap(
            {"a": {"b": {"c": {"d": "override"}}}},
            {"a": {"b": {"c": {"d": "base", "e": "only_base"}}}},
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("a")

        assert value["b"]["c"]["d"] == "override"
        assert value["b"]["c"]["e"] == "only_base"
        # Provenance is nested matching the structure
        assert isinstance(prov, dict)
        assert "b" in prov

    def test_provenance_three_layers(self) -> None:
        """Provenance correctly identifies layer for each key."""
        dcm = utils.DeepChainMap(
            {"model": {"name": "user_override"}},        # layer 0
            {"model": {"size": "project_default"}},       # layer 1
            {"model": {"name": "builtin", "size": "7b", "base": True}},  # layer 2
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("model")

        assert value["name"] == "user_override"
        assert value["size"] == "project_default"
        assert value["base"] is True

        assert prov["name"] == 0  # From layer 0
        assert prov["size"] == 1  # From layer 1
        assert prov["base"] == 2  # From layer 2

    def test_provenance_for_scalar(self) -> None:
        """Scalar values use '.' as provenance key."""
        dcm = utils.DeepChainMap(
            {"value": 42},
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("value")

        assert value == 42
        assert prov == {".": 0}

    def test_provenance_for_list(self) -> None:
        """List values use '.' as provenance key."""
        dcm = utils.DeepChainMap(
            {"items": [1, 2, 3]},
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("items")

        assert value == [1, 2, 3]
        assert prov == {".": 0}

    def test_provenance_after_reload(self) -> None:
        """Provenance cache is cleared on reload."""
        data = {"model": {"name": "original"}}
        dcm = utils.DeepChainMap(data, track_provenance=True)

        value1, prov1 = dcm.get_with_provenance("model")
        assert value1["name"] == "original"

        data["model"]["name"] = "changed"
        dcm.reload()

        value2, prov2 = dcm.get_with_provenance("model")
        assert value2["name"] == "changed"
        assert value1 is not value2

    def test_provenance_missing_key(self) -> None:
        """get_with_provenance raises KeyError for missing key."""
        dcm = utils.DeepChainMap({"a": 1}, track_provenance=True)

        with _pytest.raises(KeyError):
            dcm.get_with_provenance("missing")


# =============================================================================
# Category 7: Layer Manipulation Edge Cases (P1)
# =============================================================================


class TestLayerManipulationEdgeCases:
    """Tests for add_layer and remove_layer edge cases."""

    def test_add_layer_to_empty(self) -> None:
        """Can add layer to empty DCM."""
        dcm = utils.DeepChainMap()
        assert len(dcm) == 0

        dcm.add_layer({"a": 1})

        assert dcm["a"] == 1
        assert len(dcm.layers) == 1

    def test_remove_all_layers(self) -> None:
        """Removing all layers leaves empty DCM."""
        dcm = utils.DeepChainMap({"a": 1}, {"b": 2})

        dcm.remove_layer(0)
        dcm.remove_layer(0)

        assert len(dcm.layers) == 0
        assert len(dcm) == 0
        with _pytest.raises(KeyError):
            _ = dcm["a"]

    def test_remove_invalid_index(self) -> None:
        """remove_layer with invalid index raises IndexError."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(IndexError):
            dcm.remove_layer(999)

    def test_remove_negative_index(self) -> None:
        """remove_layer with negative index removes from end."""
        layer0 = {"a": "first"}
        layer1 = {"a": "second"}
        layer2 = {"a": "third"}
        dcm = utils.DeepChainMap(layer0, layer1, layer2)

        removed = dcm.remove_layer(-1)

        # Returns the actual dict that was stored
        assert removed == layer2
        assert len(dcm.layers) == 2
        assert dcm.layers[-1] == layer1

    def test_add_layer_at_end(self) -> None:
        """add_layer at len(layers) adds as lowest priority."""
        dcm = utils.DeepChainMap({"a": "high"}, {"a": "low"})

        dcm.add_layer({"a": "lowest"}, priority=len(dcm.layers))

        assert dcm["a"] == "high"  # Still high priority
        assert dcm.layers[-1] == {"a": "lowest"}

    def test_layers_property_returns_frozen_copy(self) -> None:
        """layers property returns frozen wrappers, mutations blocked."""
        dcm = utils.DeepChainMap({"a": 1})

        layers = dcm.layers

        # Returns FrozenMapping wrappers
        assert isinstance(layers[0], FrozenMapping)

        # Appending to returned list doesn't affect DCM (it's a copy)
        layers.append({"b": 2})
        assert len(dcm.layers) == 1

        # Mutating FrozenMapping raises TypeError
        with _pytest.raises(TypeError):
            layers[0]["a"] = 999  # type: ignore[index]


# =============================================================================
# Category 3: Deep Nesting & Stress (P1)
# =============================================================================


class TestDeepNestingAndStress:
    """Tests for deeply nested structures and many layers."""

    def test_ten_level_nesting(self) -> None:
        """10 levels deep merge works correctly."""
        # Build 10-level nested structure
        base: dict[str, _typing.Any] = {"value": "base", "base_only": True}
        override: dict[str, _typing.Any] = {"value": "override"}

        for i in range(9):
            base = {f"level{9-i}": base}
            override = {f"level{9-i}": override}

        dcm = utils.DeepChainMap(override, base)

        # Navigate to deepest level
        result = dcm["level1"]
        for i in range(2, 10):
            result = result[f"level{i}"]

        assert result["value"] == "override"
        assert result["base_only"] is True

    def test_wide_dict_1000_keys_merges_correctly(self) -> None:
        """Dict with 1000 keys merges correctly."""
        base = {f"key_{i}": i for i in range(1000)}
        override = {"key_500": "overridden", "key_999": "also_overridden"}

        dcm = utils.DeepChainMap(override, base)

        assert dcm["key_0"] == 0
        assert dcm["key_500"] == "overridden"
        assert dcm["key_999"] == "also_overridden"
        assert len(dcm) == 1000

    def test_ten_layers(self) -> None:
        """10 layers with overlapping keys resolve correctly."""
        layers = [{"shared": f"layer{i}", f"unique{i}": i} for i in range(10)]

        dcm = utils.DeepChainMap(*layers)

        # Highest priority (layer 0) wins for shared key
        assert dcm["shared"] == "layer0"
        # All unique keys accessible
        for i in range(10):
            assert dcm[f"unique{i}"] == i

    def test_mixed_deep_wide_merges_correctly(self) -> None:
        """5 levels × 100 keys per level merges correctly."""

        def make_wide_nested(depth: int, value_prefix: str) -> dict[str, _typing.Any]:
            if depth == 0:
                return {f"key_{i}": f"{value_prefix}_{i}" for i in range(100)}
            return {
                f"level_{depth}_{i}": make_wide_nested(depth - 1, f"{value_prefix}_{i}")
                for i in range(5)
            }

        base = make_wide_nested(4, "base")
        override = {"level_4_0": {"level_3_0": {"level_2_0": {"level_1_0": {"key_50": "OVERRIDE"}}}}}

        dcm = utils.DeepChainMap(override, base)

        # Check override applied
        result = dcm["level_4_0"]["level_3_0"]["level_2_0"]["level_1_0"]
        assert result["key_50"] == "OVERRIDE"
        assert result["key_0"] == "base_0_0_0_0_0"  # Base value preserved


# =============================================================================
# Category 9: Copy/Deepcopy Behavior (P1)
# =============================================================================


class TestCopyBehavior:
    """Tests for copy and deepcopy behavior."""

    def test_copy_shares_internal_layers(self) -> None:
        """copy.copy creates shallow copy — internal layers are shared."""
        original = utils.DeepChainMap({"a": {"nested": 1}})

        copied = _copy.copy(original)

        # Internal _layers list is shared (shallow copy)
        # Both DCMs see the same source data
        assert original["a"]["nested"] == copied["a"]["nested"]

        # Note: layers property returns FrozenMapping, so direct mutation
        # is blocked. This tests internal sharing for performance.
        assert original._layers is copied._layers

    def test_deepcopy_copies_layers(self) -> None:
        """copy.deepcopy creates independent copy — layers are copied."""
        original = utils.DeepChainMap({"a": {"nested": 1}})

        copied = _copy.deepcopy(original)

        # Internal _layers are different objects
        assert copied._layers is not original._layers

        # Content is equal
        assert copied.layers[0] == original.layers[0]

        # Modifications to original's internal layers don't affect copy
        original._layers[0]["a"]["nested"] = 999
        original.reload()
        assert copied["a"]["nested"] == 1

    def test_deepcopy_creates_independent_cache(self) -> None:
        """deepcopy creates independent cache."""
        original = utils.DeepChainMap({"a": {"nested": 1}})

        # Populate cache
        _ = original["a"]

        copied = _copy.deepcopy(original)

        # Mutate original's cached value
        original["a"]["nested"] = 999

        # Copy should be unaffected (either has its own cache or cache was cleared)
        copied.reload()  # Ensure fresh lookup
        assert copied["a"]["nested"] == 1


# =============================================================================
# Category 10: Serialization (P1)
# =============================================================================


class TestSerialization:
    """Tests for pickle and JSON serialization."""

    def test_pickle_roundtrip(self) -> None:
        """pickle.dumps/loads preserves DCM functionality."""
        original = utils.DeepChainMap(
            {"a": 1, "b": {"nested": 2}},
            {"b": {"other": 3}, "c": 4},
        )

        pickled = _pickle.dumps(original)
        restored = _pickle.loads(pickled)

        # Verify all values accessible and correct
        assert restored["a"] == 1
        assert restored["b"] == {"nested": 2, "other": 3}
        assert restored["c"] == 4
        assert list(restored) == list(original)

    def test_to_dict_json_roundtrip_preserves_content(self) -> None:
        """to_dict() output survives JSON roundtrip."""
        dcm = utils.DeepChainMap(
            {"a": 1, "b": {"nested": [1, 2, 3]}},
            {"b": {"other": "value"}, "c": True},
        )

        original_dict = dcm.to_dict()
        json_str = _json.dumps(original_dict)
        restored_dict = _json.loads(json_str)

        assert restored_dict == original_dict

    def test_to_dict_returns_plain_dict(self) -> None:
        """to_dict() returns exactly dict type, not subclass."""
        dcm = utils.DeepChainMap({"a": 1})

        result = dcm.to_dict()

        assert type(result) is dict  # noqa: E721 - intentionally checking exact type
        assert not isinstance(result, utils.DeepChainMap)


# =============================================================================
# Category 11: Thread Safety (P2)
# =============================================================================


class TestThreadSafety:
    """Tests documenting thread safety behavior.

    DeepChainMap is NOT thread-safe for concurrent writes.
    These tests verify read-only concurrent access works.
    """

    def test_concurrent_reads_return_consistent_values(self) -> None:
        """Multiple threads reading same key get identical values."""
        import threading as _threading

        dcm = utils.DeepChainMap({"shared": {"nested": "value"}})

        results: list[dict[str, _typing.Any]] = []
        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(100):
                    results.append(dcm["shared"])
            except Exception as e:
                errors.append(e)

        threads = [_threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        # All results should be equal (same cached value)
        assert all(r == {"nested": "value"} for r in results)


# =============================================================================
# Category 12: Unicode and Special Characters (P2)
# =============================================================================


class TestUnicodeAndSpecialCharacters:
    """Tests for unicode keys and special characters."""

    def test_unicode_keys_accessible_and_merged(self) -> None:
        """Unicode keys work correctly in merge."""
        dcm = utils.DeepChainMap(
            {"键": {"nested": "override"}},
            {"键": {"nested": "base", "other": "value"}, "مفتاح": 42},
        )

        assert dcm["键"] == {"nested": "override", "other": "value"}
        assert dcm["مفتاح"] == 42

    def test_dotted_keys_not_interpreted_as_paths(self) -> None:
        """Dotted keys like 'a.b.c' are literal, not path expressions."""
        dcm = utils.DeepChainMap({"a.b.c": "value"})

        assert dcm["a.b.c"] == "value"
        assert "a" not in dcm  # Not interpreted as nested access

        with _pytest.raises(KeyError):
            _ = dcm["a"]

    def test_special_char_keys_preserved(self) -> None:
        """Keys with special characters work correctly."""
        special_keys = {
            "key:with:colons": 1,
            "key/with/slashes": 2,
            "key\nwith\nnewlines": 3,
            "key\twith\ttabs": 4,
        }
        dcm = utils.DeepChainMap(special_keys)

        for key, value in special_keys.items():
            assert dcm[key] == value
            assert key in dcm

        assert set(dcm) == set(special_keys.keys())


# =============================================================================
# Category 13: Memory Behavior (P2)
# =============================================================================


class TestMemoryBehavior:
    """Tests for memory-related edge cases."""

    def test_large_list_value_accessible(self) -> None:
        """Large list values work correctly."""
        large_list = list(range(100_000))
        dcm = utils.DeepChainMap({"data": large_list})

        result = dcm["data"]

        assert len(result) == 100_000
        assert result[0] == 0
        assert result[50_000] == 50_000
        assert result[-1] == 99_999

    def test_circular_reference_preserved_by_deepcopy(self) -> None:
        """Circular references handled by deepcopy."""
        d: dict[str, _typing.Any] = {"value": 1, "nested": {}}
        d["nested"]["self"] = d  # Circular reference

        dcm = utils.DeepChainMap(d)

        result = dcm["nested"]

        # Can traverse the circular structure
        assert result["self"]["value"] == 1
        assert result["self"]["nested"]["self"]["value"] == 1


# =============================================================================
# Additional Coverage Tests
# =============================================================================


class TestReprAndCoverage:
    """Tests for repr and remaining coverage gaps."""

    def test_repr(self) -> None:
        """__repr__ returns readable string."""
        dcm = utils.DeepChainMap({"a": 1}, {"b": 2})

        result = repr(dcm)

        assert "DeepChainMap" in result
        assert "{'a': 1}" in result
        assert "{'b': 2}" in result

