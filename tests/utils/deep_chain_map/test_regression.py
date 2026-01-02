"""
Regression tests for DCM bugs identified in code audits.

These tests verify that fixes for identified bugs remain in place.
Each test class corresponds to a specific audit issue with P0/P1/P2 severity.

Audit References:
- V1: workflow/chatgpt-5.2-pro-extended-dcm-audit.md
- V2: workflow/chatgpt-5.2-pro-extended-dcm-audit-v2.md
- V3: workflow/chatgpt-5.2-pro-extended-dcm-audit-v3.md

Improvement Plans:
- workflow/dcm-improvement-plan.md
- workflow/dcm-improvement-plan-v2.md
- workflow/dcm-improvement-plan-v3.md
"""

import collections as _collections
import contextlib as _contextlib
import copy as _copy

import pytest as _pytest
import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm
import brynhild.utils.deep_chain_map._frozen as _frozen
import brynhild.utils.deep_chain_map._proxy as _proxy

# =============================================================================
# AUDIT V1: P0 Issues (Critical)
# =============================================================================


class TestP0_1_MutableProxyLiveView:
    """
    P0-1: MutableProxy must be a live view.

    After setting a value through a proxy, reading through the SAME proxy
    should return the new value immediately.
    """

    def test_proxy_returns_live_data(self) -> None:
        """Proxy reads reflect mutations immediately."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        proxy = d["a"]

        proxy["x"] = 2
        assert proxy["x"] == 2

    def test_proxy_live_after_delete_and_modify(self) -> None:
        """All operations through proxy are live."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        proxy = d["a"]

        del proxy["x"]
        assert "x" not in proxy

        proxy["y"] = 99
        assert proxy["y"] == 99

    def test_proxy_live_iteration(self) -> None:
        """Proxy iteration reflects mutations."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        proxy = d["a"]

        proxy["y"] = 2
        assert set(proxy) == {"x", "y"}


class TestP0_2_ListOpsOrdering:
    """
    P0-2: List ops must apply AFTER front_layer.

    The workflow: own_list() → list_append() → read should include appended items.
    """

    def test_list_ops_work_after_own_list(self) -> None:
        """List ops are applied after front_layer override."""
        d = dcm.DeepChainMap({"items": [1, 2]})
        d.own_list(("items",))
        d.list_append(("items",), 3)

        assert list(d["items"]) == [1, 2, 3]

    def test_list_ops_apply_to_front_layer_value(self) -> None:
        """List ops apply to front_layer value, not source."""
        d = dcm.DeepChainMap({"items": [1, 2]})
        d["items"] = [10, 20]
        d.list_append(("items",), 30)

        assert list(d["items"]) == [10, 20, 30]


class TestP0_3_OwnListCopiesRaw:
    """
    P0-3: own_list() must copy raw elements, not frozen wrappers.
    """

    def test_own_list_copies_raw_elements(self) -> None:
        """Elements in front_layer are plain dicts, not FrozenMapping."""
        d = dcm.DeepChainMap({"items": [{"a": 1}]})
        d.own_list(("items",))

        front_data = d._front_layer._raw_data()
        first_item = front_data.get("items", [])[0]

        assert isinstance(first_item, dict)
        assert not isinstance(first_item, _frozen.FrozenMapping)


class TestP0_4_DcmMappingWrappedInProxy:
    """
    P0-4: DcmMapping values must be wrapped in MutableProxy.

    Ensures mutations route through front_layer.
    """

    def test_dcm_mapping_returns_proxy(self) -> None:
        """DcmMapping nested values are wrapped in MutableProxy."""
        source = dcm.DcmMapping({"nested": dcm.DcmMapping({"x": 1})})
        d = dcm.DeepChainMap(source)

        assert isinstance(d["nested"], _proxy.MutableProxy)

    def test_dcm_mapping_mutation_routes_to_front_layer(self) -> None:
        """Mutations go through front_layer."""
        yaml_content = "config:\n  setting: original"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        d["config"]["setting"] = "modified"

        front_raw = d._front_layer._raw_data()
        assert front_raw["config"]["setting"] == "modified"


# =============================================================================
# AUDIT V1: P1 Issues (Important)
# =============================================================================


class TestP1_5_ImmutableProperties:
    """
    P1-5: front_layer and list_ops properties must be immutable.
    """

    def test_front_layer_is_frozen(self) -> None:
        """front_layer property returns FrozenMapping."""
        d = dcm.DeepChainMap({"a": 1})
        front = d.front_layer

        assert isinstance(front, _frozen.FrozenMapping)
        with _pytest.raises(TypeError):
            front["x"] = 99  # type: ignore[index]

    def test_list_ops_is_immutable(self) -> None:
        """list_ops property returns immutable tuples."""
        d = dcm.DeepChainMap({"items": [1]})
        d.list_append(("items",), 2)

        ops = d.list_ops
        assert isinstance(ops[("items",)], tuple)


class TestP1_6_NoneValueCaching:
    """
    P1-6: to_dict() must handle None values correctly.
    """

    def test_to_dict_handles_none(self) -> None:
        """to_dict works correctly with cached None values."""
        d = dcm.DeepChainMap({"present": None, "other": 1})

        # Populate cache
        _ = d["present"]
        _ = d["other"]

        assert d.to_dict() == {"present": None, "other": 1}


class TestP1_7_ReplaceMarkerHashability:
    """
    P1-7: ReplaceMarker must be unhashable.
    """

    def test_replace_marker_is_unhashable(self) -> None:
        """ReplaceMarker cannot be hashed."""
        marker = dcm.ReplaceMarker({"key": "value"})

        with _pytest.raises(TypeError, match="unhashable"):
            hash(marker)

    def test_replace_marker_equality_works(self) -> None:
        """Equality comparison still works."""
        m1 = dcm.ReplaceMarker({"k": "v"})
        m2 = dcm.ReplaceMarker({"k": "v"})
        m3 = dcm.ReplaceMarker({"other": "v"})

        assert m1 == m2
        assert m1 != m3


# =============================================================================
# AUDIT V1: P2 Issues (Minor)
# =============================================================================


class TestP2_8_YamlScalarParsing:
    """
    P2-8: !replace must parse YAML scalars correctly.
    """

    def test_yaml_replace_boolean_true(self) -> None:
        """!replace true parses as Python True."""
        data = _yaml.load("v: !replace true", Loader=dcm.DcmLoader)
        assert data["v"] is True

    def test_yaml_replace_boolean_yes(self) -> None:
        """!replace yes parses as Python True (YAML 1.1)."""
        data = _yaml.load("v: !replace yes", Loader=dcm.DcmLoader)
        assert data["v"] is True

    def test_yaml_replace_null(self) -> None:
        """!replace ~ parses as None."""
        data = _yaml.load("v: !replace ~", Loader=dcm.DcmLoader)
        assert data["v"] is None

    def test_yaml_replace_number(self) -> None:
        """!replace 42 parses as int."""
        data = _yaml.load("v: !replace 42", Loader=dcm.DcmLoader)
        assert data["v"] == 42


class TestP2_9_DocstringAccuracy:
    """
    P2-9: Documentation examples must be correct.
    """

    def test_delete_key_not_in_mapping(self) -> None:
        """DELETE-marked keys appear absent."""
        data = _yaml.load("key: !delete", Loader=dcm.DcmLoader)

        assert "key" not in data
        with _pytest.raises(KeyError):
            _ = data["key"]


# =============================================================================
# AUDIT V1: Cache Invalidation Optimization
# =============================================================================


class TestCacheInvalidation:
    """Per-key cache invalidation optimization."""

    def test_per_key_invalidation_preserves_other_keys(self) -> None:
        """Cache invalidation is per-key."""
        d = dcm.DeepChainMap({"a": {"x": 1}, "b": {"y": 2}})

        _ = d["a"]
        _ = d["b"]
        assert "a" in d._cache and "b" in d._cache

        d["a"]["x"] = 99
        assert "a" not in d._cache
        assert "b" in d._cache  # Preserved

    def test_nested_mutation_invalidates_top_level_key(self) -> None:
        """Deeply nested mutation invalidates top-level key only."""
        d = dcm.DeepChainMap({"config": {"model": {"name": "llama"}}, "other": 1})

        _ = d["config"]
        _ = d["other"]

        d["config"]["model"]["name"] = "gpt"

        assert "config" not in d._cache
        assert "other" in d._cache


# =============================================================================
# AUDIT V2: P0-A freeze() must handle all Mapping types
# =============================================================================


class TestP0A_FreezeHandlesMappings:
    """
    P0-A: freeze() should handle all Mapping/Sequence types.
    """

    def test_freeze_dcm_mapping(self) -> None:
        """freeze() wraps DcmMapping in FrozenMapping."""
        mapping = dcm.DcmMapping({"a": 1})
        result = _frozen.freeze(mapping)

        assert isinstance(result, _frozen.FrozenMapping)

    def test_freeze_nested_dcm_mapping(self) -> None:
        """Nested DcmMapping is also frozen."""
        data = {"outer": dcm.DcmMapping({"inner": 1})}
        frozen = _frozen.FrozenMapping(data)

        assert isinstance(frozen["outer"], _frozen.FrozenMapping)

    def test_source_layers_immutable(self) -> None:
        """source_layers access is immutable."""
        yaml_content = "config:\n  nested:\n    value: original"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        source = d.source_layers[0]
        config = source["config"]

        with _pytest.raises(TypeError):
            config["nested"] = "modified"

    def test_freeze_ordered_dict(self) -> None:
        """freeze() handles OrderedDict."""
        ordered = _collections.OrderedDict([("a", 1)])
        result = _frozen.freeze(ordered)

        assert isinstance(result, _frozen.FrozenMapping)


# =============================================================================
# AUDIT V2: P1-C DcmMapping.__delitem__ consistency
# =============================================================================


class TestP1C_DcmMappingDelitem:
    """
    P1-C: DcmMapping.__delitem__ must raise KeyError for deleted keys.
    """

    def test_delitem_already_deleted_raises(self) -> None:
        """Deleting already-deleted key raises KeyError."""
        mapping = dcm.DcmMapping({"key": "value"})
        del mapping["key"]

        with _pytest.raises(KeyError):
            del mapping["key"]


# =============================================================================
# AUDIT V2: P0-D list_ops must recurse through Mappings
# =============================================================================


class TestP0D_ListOpsRecursion:
    """
    P0-D: _apply_all_list_ops must recurse through all Mapping types.
    """

    def test_list_ops_through_dcm_mapping(self) -> None:
        """List ops applied through DcmMapping structure."""
        source = dcm.DcmMapping({"config": dcm.DcmMapping({"items": [1, 2]})})
        d = dcm.DeepChainMap(source)

        d.list_append(("config", "items"), 3)

        assert list(d["config"]["items"]) == [1, 2, 3]


# =============================================================================
# AUDIT V2: P0-B Provenance must recurse for front_layer
# =============================================================================


class TestP0B_ProvenanceRecursion:
    """
    P0-B: _update_provenance_for_front must recurse for nested dicts.
    """

    def test_nested_provenance_from_front_layer(self) -> None:
        """Front layer nested dict has nested provenance structure."""
        d = dcm.DeepChainMap({"config": {"a": 1, "b": 2}}, track_provenance=True)
        d["config"]["b"] = 99

        _, prov = d.get_with_provenance("config")

        assert prov["a"] == 0  # From source
        assert prov["b"] == -1  # From front_layer


# =============================================================================
# AUDIT V2: P0-C Public path APIs
# =============================================================================


class TestP0C_PublicPathAPIs:
    """
    P0-C: Public path-based APIs (set_path, replace_path, delete_path).
    """

    def test_set_path_basic(self) -> None:
        """set_path() sets value at nested path."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        d.set_path(("a", "y"), 2)

        assert d["a"]["y"] == 2

    def test_set_path_merges_by_default(self) -> None:
        """set_path() merges dicts by default."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.set_path(("a",), {"y": 20, "z": 30})

        assert d["a"]["x"] == 1  # Preserved
        assert d["a"]["y"] == 20  # Updated

    def test_set_path_no_merge(self) -> None:
        """set_path(merge=False) replaces entirely."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        d.set_path(("a",), {"z": 3}, merge=False)

        assert "x" not in d["a"]
        assert d["a"]["z"] == 3

    def test_replace_path(self) -> None:
        """replace_path() replaces without merging."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        d.replace_path(("a",), {"z": 3})

        assert "x" not in d["a"]
        assert d["a"]["z"] == 3

    def test_delete_path(self) -> None:
        """delete_path() marks path as deleted."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.delete_path(("a", "x"))

        assert "x" not in d["a"]


# =============================================================================
# AUDIT V2: P1-A Unified merge logic
# =============================================================================


class TestP1A_UnifiedMergeLogic:
    """
    P1-A: _deep_merge_dicts delegates to _merge_value.
    """

    def test_deep_merge_handles_delete_marker(self) -> None:
        """DELETE markers work in _deep_merge_dicts."""
        d = dcm.DeepChainMap({})
        base = {"a": 1, "b": 2}
        override = dcm.DcmMapping({"a": dcm.DELETE})

        result = d._deep_merge_dicts(base, override)

        assert "a" not in result
        assert result["b"] == 2

    def test_deep_merge_handles_replace_marker(self) -> None:
        """ReplaceMarker works in _deep_merge_dicts."""
        d = dcm.DeepChainMap({})
        base = {"a": {"x": 1}}
        override = {"a": dcm.ReplaceMarker({"z": 3})}

        result = d._deep_merge_dicts(base, override)

        assert result["a"] == {"z": 3}


# =============================================================================
# AUDIT V3: P0-NEW-1 DcmMapping loses sibling keys
# =============================================================================


class TestP0New1_DcmMappingSiblingKeys:
    """
    P0-NEW-1: DcmMapping layer must preserve sibling keys on mutation.
    """

    def test_yaml_mapping_preserves_siblings(self) -> None:
        """Mutating one key preserves siblings."""
        yaml_content = "config:\n  setting1: original1\n  setting2: original2"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        d["config"]["setting1"] = "modified1"

        result = dict(d["config"])
        assert result["setting1"] == "modified1"
        assert result["setting2"] == "original2"

    def test_nested_dcm_mapping_preserves_structure(self) -> None:
        """Deeply nested DcmMapping preserves all siblings."""
        yaml_content = """
root:
  level1:
    a: 1
    b: 2
  level2:
    x: 10
"""
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        d["root"]["level1"]["a"] = 100

        assert d["root"]["level1"]["a"] == 100
        assert d["root"]["level1"]["b"] == 2
        assert d["root"]["level2"]["x"] == 10


# =============================================================================
# AUDIT V3: P0-NEW-2 replace_path() breaks on nested mutation
# =============================================================================


class TestP0New2_ReplacePathNestedMutation:
    """
    P0-NEW-2: Nested mutations under replace_path() must work correctly.
    """

    def test_replace_path_then_set_nested(self) -> None:
        """Setting nested key after replace_path preserves replacement."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.replace_path(("a",), {"z": 3})
        d["a"]["w"] = 4

        result = dict(d["a"])
        assert result == {"z": 3, "w": 4}
        assert "x" not in result

    def test_replace_path_then_delete_nested(self) -> None:
        """Deleting nested key after replace_path preserves replacement."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        d.replace_path(("a",), {"z": 3, "w": 4})
        del d["a"]["z"]

        result = dict(d["a"])
        assert result == {"w": 4}
        assert "x" not in result


# =============================================================================
# AUDIT V3: P1-B get_with_provenance() returns mutable internal state
# =============================================================================


class TestP1B_ProvenanceImmutability:
    """
    P1-B: get_with_provenance() must return immutable provenance.
    """

    def test_provenance_mutation_does_not_affect_internal(self) -> None:
        """Mutating returned provenance doesn't affect cache."""
        d = dcm.DeepChainMap({"a": {"x": 1}}, track_provenance=True)

        _, prov1 = d.get_with_provenance("a")
        original = _copy.deepcopy(dict(prov1))

        with _contextlib.suppress(TypeError):
            prov1["hacked"] = 123  # type: ignore[index]

        _, prov2 = d.get_with_provenance("a")
        assert dict(prov2) == original


# =============================================================================
# AUDIT V3: P1-D/E Documentation accuracy
# =============================================================================


class TestP1DE_DocumentedBehavior:
    """
    P1-D/E: Documented behavior matches actual behavior.
    """

    def test_getitem_returns_mutableproxy(self) -> None:
        """dcm[key] returns MutableProxy for dict values."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        result = d["a"]

        assert type(result).__name__ == "MutableProxy"

    def test_setitem_merges_by_default(self) -> None:
        """dcm[key] = dict merges by default."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d["a"] = {"y": 20, "z": 30}

        result = dict(d["a"])
        assert result["x"] == 1  # Original preserved
        assert result["y"] == 20
        assert result["z"] == 30


# =============================================================================
# AUDIT V3: Additional edge cases
# =============================================================================


class TestAdditionalEdgeCases:
    """Additional edge cases from audits."""

    def test_multiple_yaml_layers_merge(self) -> None:
        """Multiple DcmMapping layers merge correctly."""
        base = _yaml.load("config:\n  a: 1", Loader=dcm.DcmLoader)
        override = _yaml.load("config:\n  b: 2", Loader=dcm.DcmLoader)

        d = dcm.DeepChainMap(override, base)

        assert d["config"]["a"] == 1
        assert d["config"]["b"] == 2

    def test_yaml_delete_with_front_mutation(self) -> None:
        """DELETE marker works with front_layer mutations."""
        yaml_content = "config:\n  keep: value\n  remove: !delete"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        d["config"]["new"] = "added"

        result = dict(d["config"])
        assert result["keep"] == "value"
        assert result["new"] == "added"
        assert "remove" not in result

    def test_yaml_replace_with_front_mutation(self) -> None:
        """ReplaceMarker works with front_layer mutations."""
        yaml_content = "config:\n  nested: !replace\n    only: this"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        base = {"config": {"nested": {"original": "data"}}}

        d = dcm.DeepChainMap(data, base)
        d["config"]["nested"]["extra"] = "value"

        result = dict(d["config"]["nested"])
        assert result["only"] == "this"
        assert result["extra"] == "value"
        assert "original" not in result


# =============================================================================
# Interaction tests
# =============================================================================


class TestInteractionBugs:
    """Tests for interactions between multiple fixes."""

    def test_proxy_live_through_nested_chain(self) -> None:
        """Deep proxy chains are live."""
        d = dcm.DeepChainMap({"a": {"b": {"c": 1}}})

        proxy_a = d["a"]
        proxy_b = proxy_a["b"]
        proxy_b["c"] = 99

        assert proxy_b["c"] == 99
        assert proxy_a["b"]["c"] == 99
        assert d["a"]["b"]["c"] == 99

    def test_dcm_mapping_yaml_properly_wrapped(self) -> None:
        """DcmLoader layers are properly wrapped."""
        yaml_content = "level1:\n  level2:\n    value: deep"
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        level1 = d["level1"]
        assert isinstance(level1, _proxy.MutableProxy)

        level2 = level1["level2"]
        assert isinstance(level2, _proxy.MutableProxy)

        level2["value"] = "modified"
        assert d["level1"]["level2"]["value"] == "modified"

