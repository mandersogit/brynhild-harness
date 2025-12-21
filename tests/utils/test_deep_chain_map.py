"""Tests for DeepChainMap."""

import pytest as _pytest

import brynhild.utils as utils


class TestDeepChainMapBasic:
    """Basic functionality tests."""

    def test_single_layer_access(self) -> None:
        """Single layer behaves like a regular dict."""
        data = {"a": 1, "b": {"c": 2}}
        dcm = utils.DeepChainMap(data)

        assert dcm["a"] == 1
        assert dcm["b"] == {"c": 2}

    def test_missing_key_raises(self) -> None:
        """Missing key raises KeyError."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(KeyError):
            _ = dcm["missing"]

    def test_len_counts_unique_keys(self) -> None:
        """len() returns count of unique keys across layers."""
        dcm = utils.DeepChainMap(
            {"a": 1, "b": 2},  # layer 0
            {"b": 3, "c": 4},  # layer 1
        )

        assert len(dcm) == 3  # a, b, c

    def test_contains(self) -> None:
        """__contains__ checks all layers."""
        dcm = utils.DeepChainMap(
            {"a": 1},
            {"b": 2},
        )

        assert "a" in dcm
        assert "b" in dcm
        assert "c" not in dcm

    def test_iter_yields_unique_keys(self) -> None:
        """Iteration yields each key once."""
        dcm = utils.DeepChainMap(
            {"a": 1, "b": 2},
            {"b": 3, "c": 4},
        )

        keys = list(dcm)
        assert sorted(keys) == ["a", "b", "c"]


class TestDeepChainMapMerging:
    """Deep merge behavior tests."""

    def test_scalar_override(self) -> None:
        """Higher priority scalar overrides lower."""
        dcm = utils.DeepChainMap(
            {"value": "high"},  # priority 0
            {"value": "low"},   # priority 1
        )

        assert dcm["value"] == "high"

    def test_nested_dict_merge(self) -> None:
        """Nested dicts are merged, not replaced."""
        builtin = {
            "model": {
                "name": "llama",
                "size": "7b",
                "context": 4096,
            }
        }
        user = {
            "model": {
                "size": "70b",  # Override just this
            }
        }
        dcm = utils.DeepChainMap(user, builtin)

        result = dcm["model"]
        assert result["name"] == "llama"      # From builtin
        assert result["size"] == "70b"        # From user (overridden)
        assert result["context"] == 4096      # From builtin

    def test_deeply_nested_merge(self) -> None:
        """Deep nesting merges correctly."""
        base = {
            "a": {
                "b": {
                    "c": 1,
                    "d": 2,
                }
            }
        }
        override = {
            "a": {
                "b": {
                    "c": 100,  # Override
                    "e": 3,    # Add new
                }
            }
        }
        dcm = utils.DeepChainMap(override, base)

        result = dcm["a"]["b"]
        assert result["c"] == 100  # Overridden
        assert result["d"] == 2    # From base
        assert result["e"] == 3    # Added

    def test_type_mismatch_replaces(self) -> None:
        """If types differ, higher priority replaces entirely."""
        base = {"value": {"nested": "dict"}}
        override = {"value": "string now"}

        dcm = utils.DeepChainMap(override, base)
        assert dcm["value"] == "string now"


class TestDeepChainMapListBehavior:
    """List merge behavior tests."""

    def test_lists_replace_not_merge(self) -> None:
        """Higher priority list completely replaces lower priority list."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}

        dcm = utils.DeepChainMap(override, base)

        # Higher priority wins, no merging
        assert list(dcm["items"]) == [4, 5]

    def test_list_extend_via_list_ops(self) -> None:
        """Use list_extend for explicit concatenation."""
        base = {"items": [1, 2, 3]}

        dcm = utils.DeepChainMap(base)
        dcm.list_extend(("items",), [4, 5])

        assert list(dcm["items"]) == [1, 2, 3, 4, 5]

    def test_list_append_via_list_ops(self) -> None:
        """Use list_append for adding single items."""
        base = {"items": [1, 2, 3]}

        dcm = utils.DeepChainMap(base)
        dcm.list_append(("items",), 4)

        assert list(dcm["items"]) == [1, 2, 3, 4]


class TestDeepChainMapCaching:
    """Cache behavior tests."""

    def test_results_are_cached(self) -> None:
        """Same key returns proxies wrapping same cached data."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})

        result1 = dcm["a"]
        result2 = dcm["a"]

        # 2.0: Returns MutableProxy each time, but underlying data is cached
        assert result1 == result2  # Same content
        assert result1["b"] == result2["b"] == 1

    def test_reload_clears_cache(self) -> None:
        """reload() forces re-merge."""
        data = {"a": {"b": 1}}
        dcm = utils.DeepChainMap(data)

        result1 = dcm["a"]
        data["a"]["b"] = 2  # Modify in place
        dcm.reload()
        result2 = dcm["a"]

        assert result1["b"] == 1
        assert result2["b"] == 2
        assert result1 is not result2


class TestDeepChainMapProvenance:
    """Provenance tracking tests."""

    def test_provenance_not_enabled_raises(self) -> None:
        """get_with_provenance raises if tracking disabled."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(RuntimeError, match="not enabled"):
            dcm.get_with_provenance("a")

    def test_provenance_single_layer(self) -> None:
        """Provenance from single layer."""
        dcm = utils.DeepChainMap(
            {"model": {"name": "test"}},
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("model")
        assert value == {"name": "test"}
        assert prov["name"] == 0  # From layer 0

    def test_provenance_merged_layers(self) -> None:
        """Provenance tracks which layer each value came from."""
        builtin = {"model": {"name": "default", "size": "7b"}}
        user = {"model": {"size": "70b"}}

        dcm = utils.DeepChainMap(
            user,     # layer 0 (highest priority)
            builtin,  # layer 1
            track_provenance=True,
        )

        value, prov = dcm.get_with_provenance("model")
        assert value["name"] == "default"
        assert value["size"] == "70b"
        assert prov["name"] == 1   # From builtin (layer 1)
        assert prov["size"] == 0   # From user (layer 0)


class TestDeepChainMapMutation:
    """Mutation tests."""

    def test_setitem_modifies_front_layer(self) -> None:
        """2.0: Setting a value goes to front_layer, not source layers."""
        layer0 = {"a": 1}
        layer1 = {"b": 2}
        dcm = utils.DeepChainMap(layer0, layer1)

        dcm["c"] = 3

        # Source layers unchanged
        assert "c" not in layer0
        assert "c" not in layer1
        # Value in front_layer
        assert dcm.front_layer["c"] == 3
        # Visible through dcm
        assert dcm["c"] == 3

    def test_setitem_clears_cache(self) -> None:
        """Setting a value clears the cache."""
        dcm = utils.DeepChainMap({"a": {"b": 1}})
        _ = dcm["a"]  # Populate cache

        dcm["a"] = {"b": 2}

        assert dcm["a"]["b"] == 2

    def test_delitem_marks_deleted(self) -> None:
        """2.0: Deleting marks in delete_layer, source layers unchanged."""
        layer0 = {"a": 1}
        layer1 = {"a": 2}
        dcm = utils.DeepChainMap(layer0, layer1)

        del dcm["a"]

        # Source layers unchanged
        assert layer0["a"] == 1
        assert layer1["a"] == 2
        # Deleted via delete_layer
        assert "a" not in dcm

    def test_delitem_missing_raises(self) -> None:
        """Deleting missing key raises KeyError."""
        dcm = utils.DeepChainMap({"a": 1})

        with _pytest.raises(KeyError):
            del dcm["missing"]


class TestDeepChainMapLayers:
    """Layer manipulation tests."""

    def test_add_layer_default_priority(self) -> None:
        """add_layer with no priority inserts at index 0."""
        dcm = utils.DeepChainMap({"a": "low"})
        dcm.add_layer({"a": "high"})

        assert dcm["a"] == "high"

    def test_add_layer_specific_priority(self) -> None:
        """add_layer with priority inserts at that index."""
        dcm = utils.DeepChainMap({"a": "first"}, {"a": "third"})
        dcm.add_layer({"a": "second"}, priority=1)

        # Layer order: first (0), second (1), third (2)
        # first has highest priority
        assert dcm["a"] == "first"

    def test_remove_layer(self) -> None:
        """remove_layer removes and returns the layer."""
        layer0 = {"a": "first"}
        layer1 = {"a": "second"}
        dcm = utils.DeepChainMap(layer0, layer1)

        removed = dcm.remove_layer(0)

        assert removed is layer0
        assert dcm["a"] == "second"

    def test_layers_property(self) -> None:
        """layers property returns frozen views of source data."""
        from brynhild.utils.deep_chain_map._frozen import FrozenMapping

        layer0 = {"a": 1}
        layer1 = {"b": 2}
        dcm = utils.DeepChainMap(layer0, layer1)

        # Returns FrozenMapping wrappers, not original dicts
        assert isinstance(dcm.layers[0], FrozenMapping)
        assert isinstance(dcm.layers[1], FrozenMapping)
        # Content is equal
        assert dcm.layers[0] == layer0
        assert dcm.layers[1] == layer1


class TestDeepChainMapToDict:
    """to_dict tests."""

    def test_to_dict_merges_everything(self) -> None:
        """to_dict returns fully merged plain dict."""
        dcm = utils.DeepChainMap(
            {"a": 1, "b": {"c": 2}},
            {"b": {"d": 3}, "e": 4},
        )

        result = dcm.to_dict()

        assert result == {
            "a": 1,
            "b": {"c": 2, "d": 3},
            "e": 4,
        }
        assert isinstance(result, dict)
        assert not isinstance(result, utils.DeepChainMap)



