"""
Tests verifying DCM issues are fixed.

These tests were originally characterization tests asserting buggy behavior.
Now they verify the CORRECT behavior after fixes.

See: workflow/dcm-improvement-plan.md
See: workflow/chatgpt-5.2-pro-extended-dcm-audit.md
"""

import pytest as _pytest
import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm
import brynhild.utils.deep_chain_map._frozen as _frozen
import brynhild.utils.deep_chain_map._proxy as _proxy


class TestP0Issues:
    """P0 (Critical) issues - verified fixes."""

    def test_p0_1_mutableproxy_returns_live_data(self) -> None:
        """
        P0-1 FIX: MutableProxy is now a live view.

        After setting a value through a proxy, reading through the SAME proxy
        returns the new value immediately.
        """
        dcm_instance = dcm.DeepChainMap({"a": {"x": 1}})
        proxy = dcm_instance["a"]

        # Verify initial state
        assert proxy["x"] == 1

        # Mutate through proxy
        proxy["x"] = 2

        # FIXED: Reading through the SAME proxy returns live data
        assert proxy["x"] == 2

        # Fresh proxy also works
        assert dcm_instance["a"]["x"] == 2

    def test_p0_1_mutableproxy_live_after_delete_and_modify(self) -> None:
        """
        P0-1 FIX: All operations through proxy are live.
        """
        dcm_instance = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        proxy = dcm_instance["a"]

        # Delete works correctly
        del proxy["x"]
        assert "x" not in proxy

        # Mutations are live
        proxy["y"] = 99
        assert proxy["y"] == 99  # FIXED: live view

        # Fresh proxy sees the same
        assert dcm_instance["a"]["y"] == 99

    def test_p0_1_mutableproxy_live_iteration(self) -> None:
        """
        P0-1 FIX: Proxy iteration reflects mutations.
        """
        dcm_instance = dcm.DeepChainMap({"a": {"x": 1}})
        proxy = dcm_instance["a"]

        # Add a new key
        proxy["y"] = 2

        # FIXED: Iteration includes new key
        keys = set(proxy)
        assert keys == {"x", "y"}

    def test_p0_2_list_ops_work_after_own_list(self) -> None:
        """
        P0-2 FIX: List ops work after own_list().

        The workflow:
        1. own_list() - copy list to front_layer
        2. list_append() - add items
        3. Read - should include appended items
        """
        dcm_instance = dcm.DeepChainMap({"items": [1, 2]})

        # Step 1: Own the list
        dcm_instance.own_list(("items",))

        # Step 2: Append via list ops
        dcm_instance.list_append(("items",), 3)

        # FIXED: List ops are applied AFTER front_layer
        result = list(dcm_instance["items"])
        assert result == [1, 2, 3]

    def test_p0_2_list_ops_order_correct(self) -> None:
        """
        P0-2 FIX: List ops apply after front_layer.
        """
        dcm_instance = dcm.DeepChainMap({"items": [1, 2]})

        # Put a different list in front_layer
        dcm_instance["items"] = [10, 20]

        # Add list op
        dcm_instance.list_append(("items",), 30)

        # FIXED: List ops apply AFTER front_layer merge
        result = list(dcm_instance["items"])
        assert result == [10, 20, 30]

    def test_p0_3_own_list_copies_raw_elements(self) -> None:
        """
        P0-3 FIX: own_list() copies raw list from cache.

        Elements are plain dicts, not FrozenMapping wrappers.
        """
        dcm_instance = dcm.DeepChainMap({"items": [{"a": 1}, {"b": 2}]})

        # Own the list
        dcm_instance.own_list(("items",))

        # Check what's in front_layer
        front_data = dcm_instance._front_layer._raw_data()
        items_in_front = front_data.get("items", [])

        # FIXED: Elements are plain dict
        first_item = items_in_front[0]
        assert isinstance(first_item, dict)
        assert not isinstance(first_item, _frozen.FrozenMapping)

    def test_p0_4_dcm_mapping_wrapped_in_proxy(self) -> None:
        """
        P0-4 FIX: DcmMapping is wrapped in MutableProxy.

        When a source layer contains DcmMapping, it's properly wrapped
        so mutations route through front_layer.
        """
        # Create a source layer with DcmMapping
        source = dcm.DcmMapping({"nested": dcm.DcmMapping({"x": 1})})
        dcm_instance = dcm.DeepChainMap(source)

        # Get the nested value
        nested = dcm_instance["nested"]

        # FIXED: We get MutableProxy (wraps Mapping types)
        assert isinstance(nested, _proxy.MutableProxy)

    def test_p0_4_dcm_mapping_mutation_routes_to_front_layer(self) -> None:
        """
        P0-4 FIX: Mutations go through front_layer.
        """
        # Load YAML with DcmLoader - produces DcmMapping
        yaml_content = "config:\n  setting: original"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)

        dcm_instance = dcm.DeepChainMap(data)

        # Get config - should be MutableProxy
        config = dcm_instance["config"]

        # Mutate - should route to front_layer
        config["setting"] = "modified"

        # FIXED: front_layer got the write
        front_raw = dcm_instance._front_layer._raw_data()
        assert "config" in front_raw
        assert front_raw["config"]["setting"] == "modified"

        # Reading back shows the modification
        assert dcm_instance["config"]["setting"] == "modified"


class TestP1Issues:
    """P1 (Important) issues - verified fixes."""

    def test_p1_5_front_layer_property_is_frozen(self) -> None:
        """
        P1-5 FIX: front_layer property returns frozen view.

        Cannot mutate through the property.
        """
        dcm_instance = dcm.DeepChainMap({"a": 1})

        # Get read-only front_layer
        front = dcm_instance.front_layer

        # FIXED: Mutation raises TypeError
        assert isinstance(front, _frozen.FrozenMapping)
        with _pytest.raises(TypeError):
            front["x"] = 99  # type: ignore[index]

    def test_p1_5_list_ops_property_is_immutable(self) -> None:
        """
        P1-5 FIX: list_ops property returns immutable view.
        """
        dcm_instance = dcm.DeepChainMap({"items": [1, 2]})
        dcm_instance.list_append(("items",), 3)

        # Get read-only list_ops
        ops = dcm_instance.list_ops

        # FIXED: The ops are tuples (immutable)
        assert isinstance(ops[("items",)], tuple)

        # Cannot append to tuple
        with _pytest.raises(AttributeError):
            ops[("items",)].append("fake_op")  # type: ignore[union-attr]

    def test_p1_6_to_dict_handles_none_correctly(self) -> None:
        """
        P1-6 FIX: to_dict() handles None values correctly.

        Uses 'key in cache' check instead of 'cache.get(key) is None'.
        """
        dcm_instance = dcm.DeepChainMap({"present": None, "other": 1})

        # Populate cache
        _ = dcm_instance["present"]
        _ = dcm_instance["other"]

        # Verify cache is populated with None
        assert "present" in dcm_instance._cache
        assert dcm_instance._cache["present"] is None

        # to_dict works correctly
        result = dcm_instance.to_dict()
        assert result == {"present": None, "other": 1}

    def test_p1_7_replace_marker_is_unhashable(self) -> None:
        """
        P1-7 FIX: ReplaceMarker is explicitly unhashable.

        Since wrapped values may be unhashable (dicts, lists), and the
        previous hash implementation violated the hash/equality contract,
        ReplaceMarker is now unhashable.
        """
        marker = dcm.ReplaceMarker({"key": "value"})

        # FIXED: ReplaceMarker is unhashable
        with _pytest.raises(TypeError, match="unhashable"):
            hash(marker)

    def test_p1_7_replace_marker_equality_still_works(self) -> None:
        """
        P1-7: Equality comparison still works correctly.
        """
        value1 = {"key": "value"}
        value2 = {"key": "value"}

        marker1 = dcm.ReplaceMarker(value1)
        marker2 = dcm.ReplaceMarker(value2)
        marker3 = dcm.ReplaceMarker({"different": "value"})

        assert marker1 == marker2
        assert marker1 != marker3


class TestP2Issues:
    """P2 (Minor) issues - verified fixes."""

    def test_p2_8_yaml_replace_scalar_parsing_correct(self) -> None:
        """
        P2-8 FIX: YAML !replace uses PyYAML's proper scalar construction.

        All YAML 1.1 scalar types are handled correctly.
        """
        # Standard YAML boolean
        data1 = _yaml.load("value: !replace true", Loader=dcm.DcmLoader)
        assert data1["value"] is True

        # YAML 1.1 "yes" - correctly parsed as True
        data2 = _yaml.load("value: !replace yes", Loader=dcm.DcmLoader)
        assert data2["value"] is True

        # YAML 1.1 "no" - correctly parsed as False
        data3 = _yaml.load("value: !replace no", Loader=dcm.DcmLoader)
        assert data3["value"] is False

        # YAML null variations
        data4 = _yaml.load("value: !replace ~", Loader=dcm.DcmLoader)
        assert data4["value"] is None

        data5 = _yaml.load("value: !replace null", Loader=dcm.DcmLoader)
        assert data5["value"] is None

        # Numbers
        data6 = _yaml.load("value: !replace 42", Loader=dcm.DcmLoader)
        assert data6["value"] == 42

        data7 = _yaml.load("value: !replace 3.14", Loader=dcm.DcmLoader)
        assert data7["value"] == 3.14

        # Strings
        data8 = _yaml.load("value: !replace hello", Loader=dcm.DcmLoader)
        assert data8["value"] == "hello"

    def test_p2_9_docstring_example_correct(self) -> None:
        """
        P2-9 FIX: Documentation example is now correct.

        The __init__.py docstring was fixed to show correct behavior.
        """
        data = _yaml.load("key: !delete", Loader=dcm.DcmLoader)

        # DELETE-marked keys appear absent
        assert "key" not in data

        # Accessing raises KeyError
        with _pytest.raises(KeyError):
            _ = data["key"]

        # Raw access for internal use
        assert data._raw_getitem("key") is dcm.DELETE


class TestInteractionBugs:
    """Tests for interactions between multiple fixes."""

    def test_proxy_live_through_nested_chain(self) -> None:
        """
        P0-1 FIX: Deep proxy chains are live.
        """
        dcm_instance = dcm.DeepChainMap({"a": {"b": {"c": 1}}})

        # Get nested proxies
        proxy_a = dcm_instance["a"]
        proxy_b = proxy_a["b"]

        # Mutate through deepest proxy
        proxy_b["c"] = 99

        # FIXED: All proxies in the chain see the change
        assert proxy_b["c"] == 99
        assert proxy_a["b"]["c"] == 99
        assert dcm_instance["a"]["b"]["c"] == 99

    def test_dcm_mapping_yaml_layer_properly_wrapped(self) -> None:
        """
        P0-4 FIX: DcmLoader layers are properly wrapped.
        """
        yaml_content = """
        level1:
          level2:
            level3:
              value: deep
        """
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)

        # The loaded data is DcmMapping
        assert isinstance(data, dcm.DcmMapping)

        dcm_instance = dcm.DeepChainMap(data)

        # Access nested value - should be MutableProxy
        level1 = dcm_instance["level1"]
        assert isinstance(level1, _proxy.MutableProxy)

        level2 = level1["level2"]
        assert isinstance(level2, _proxy.MutableProxy)

        level3 = level2["level3"]
        assert isinstance(level3, _proxy.MutableProxy)

        # Can mutate through the chain
        level3["value"] = "modified"
        assert dcm_instance["level1"]["level2"]["level3"]["value"] == "modified"


class TestCacheInvalidation:
    """Tests for per-key cache invalidation optimization."""

    def test_per_key_invalidation_preserves_other_keys(self) -> None:
        """
        Cache invalidation is per-key, not global.
        """
        dcm_instance = dcm.DeepChainMap({"a": {"x": 1}, "b": {"y": 2}})

        # Populate cache for both keys
        _ = dcm_instance["a"]
        _ = dcm_instance["b"]
        assert "a" in dcm_instance._cache
        assert "b" in dcm_instance._cache

        # Mutate key "a"
        dcm_instance["a"]["x"] = 99

        # Only "a" should be invalidated, "b" should remain cached
        # (This is an implementation detail we're verifying)
        assert "a" not in dcm_instance._cache  # Invalidated
        assert "b" in dcm_instance._cache  # Still cached

    def test_nested_mutation_invalidates_top_level_key(self) -> None:
        """
        Mutating nested path invalidates the top-level key only.
        """
        dcm_instance = dcm.DeepChainMap(
            {"config": {"model": {"name": "llama"}}, "other": 1}
        )

        # Populate cache
        _ = dcm_instance["config"]
        _ = dcm_instance["other"]
        assert "config" in dcm_instance._cache
        assert "other" in dcm_instance._cache

        # Mutate deeply nested path
        dcm_instance["config"]["model"]["name"] = "gpt"

        # "config" invalidated, "other" preserved
        assert "config" not in dcm_instance._cache
        assert "other" in dcm_instance._cache

        # Fresh read works
        assert dcm_instance["config"]["model"]["name"] == "gpt"
