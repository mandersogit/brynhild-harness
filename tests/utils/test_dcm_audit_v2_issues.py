"""
Tests for issues identified in DCM audit v2.

These tests verify the bugs are fixed. They were originally written as
characterization tests (asserting buggy behavior) and updated to assert
correct behavior after fixes.

See: workflow/dcm-improvement-plan-v2.md
See: workflow/chatgpt-5.2-pro-extended-dcm-audit-v2.md
"""

import pytest as _pytest
import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm
import brynhild.utils.deep_chain_map._frozen as _frozen


class TestP0A_FreezeLeaksDcmMapping:
    """
    P0-A: freeze() should handle all Mapping/Sequence types, not just dict/list.

    When source_layers contain DcmMapping (from YAML loading), nested access
    through FrozenMapping should NOT return mutable DcmMapping objects.
    """

    def test_freeze_handles_dcm_mapping(self) -> None:
        """freeze() should wrap DcmMapping in FrozenMapping."""
        mapping = dcm.DcmMapping({"a": 1})

        result = _frozen.freeze(mapping)

        # FIXED: DcmMapping is wrapped in FrozenMapping
        assert isinstance(result, _frozen.FrozenMapping)

    def test_freeze_handles_nested_dcm_mapping(self) -> None:
        """Nested DcmMapping inside dict should be frozen."""
        data = {"outer": dcm.DcmMapping({"inner": 1})}

        frozen = _frozen.FrozenMapping(data)
        nested = frozen["outer"]

        # FIXED: Nested DcmMapping is also frozen
        assert isinstance(nested, _frozen.FrozenMapping)

    def test_source_layers_nested_access_is_immutable(self) -> None:
        """
        Accessing nested values through source_layers should be immutable.
        """
        yaml_content = """
        config:
          nested:
            value: original
        """
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        dcm_instance = dcm.DeepChainMap(data)

        # Get source layer
        source = dcm_instance.source_layers[0]
        config = source["config"]

        # FIXED: Attempting to mutate should raise TypeError
        with _pytest.raises(TypeError):
            config["nested"] = "modified"

    def test_front_layer_nested_access_is_immutable(self) -> None:
        """
        Accessing nested values through front_layer property should be immutable.
        """
        dcm_instance = dcm.DeepChainMap()
        dcm_instance["config"] = {"nested": {"value": 1}}

        # Get front_layer (read-only view)
        front = dcm_instance.front_layer
        config = front["config"]

        # FIXED: Attempting to mutate should raise TypeError
        with _pytest.raises(TypeError):
            config["new_key"] = "value"


class TestP1C_DcmMappingDelitemInconsistency:
    """
    P1-C: DcmMapping.__delitem__ should raise KeyError for already-deleted keys.

    Standard mapping semantics: del d["key"] twice should raise KeyError on second.
    """

    def test_delitem_already_deleted_raises_keyerror(self) -> None:
        """Deleting an already-deleted key should raise KeyError."""
        mapping = dcm.DcmMapping({"key": "value"})

        # First delete succeeds
        del mapping["key"]
        assert "key" not in mapping

        # FIXED: Second delete raises KeyError
        with _pytest.raises(KeyError):
            del mapping["key"]

    def test_delitem_nonexistent_raises_keyerror(self) -> None:
        """Deleting a nonexistent key should raise KeyError."""
        mapping = dcm.DcmMapping({"a": 1})

        with _pytest.raises(KeyError):
            del mapping["nonexistent"]


class TestP0D_ListOpsDictOnlyRecursion:
    """
    P0-D: _apply_all_list_ops should recurse through all Mappings, not just dict.

    If merged results contain DcmMapping subtrees, nested lists should still
    have their list ops applied.
    """

    def test_list_ops_applied_through_dcm_mapping(self) -> None:
        """
        List ops should be applied even when structure contains DcmMapping.
        """
        # Create a source with DcmMapping containing a nested list
        source = dcm.DcmMapping({
            "config": dcm.DcmMapping({
                "items": [1, 2, 3]
            })
        })
        dcm_instance = dcm.DeepChainMap(source)

        # Add a list op for the nested path
        dcm_instance.list_append(("config", "items"), 4)

        # FIXED: List op should be applied
        result = list(dcm_instance["config"]["items"])
        assert result == [1, 2, 3, 4]

    def test_list_ops_in_yaml_loaded_structure(self) -> None:
        """
        List ops should work in YAML-loaded DcmMapping structures.
        """
        yaml_content = """
        plugins:
          enabled:
            - plugin_a
            - plugin_b
        """
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        dcm_instance = dcm.DeepChainMap(data)

        # Add a list op
        dcm_instance.list_append(("plugins", "enabled"), "plugin_c")

        # FIXED: List op should be applied
        result = list(dcm_instance["plugins"]["enabled"])
        assert result == ["plugin_a", "plugin_b", "plugin_c"]


class TestP0B_ShallowProvenanceForFrontLayer:
    """
    P0-B: _update_provenance_for_front should recurse for nested dicts.

    When front_layer overrides nested dict values, provenance should reflect
    the nesting structure with -1 for front_layer keys at all levels.
    """

    def test_nested_provenance_from_front_layer(self) -> None:
        """
        Front layer nested dict should have nested provenance structure.
        """
        source = {"config": {"a": 1, "b": 2, "c": 3}}
        dcm_instance = dcm.DeepChainMap(source, track_provenance=True)

        # Override nested key via front_layer
        dcm_instance["config"]["b"] = 99

        _, prov = dcm_instance.get_with_provenance("config")

        # FIXED: Provenance should show nested structure
        # a and c from source (layer 0), b from front_layer (-1)
        assert prov["a"] == 0
        assert prov["c"] == 0
        assert prov["b"] == -1

    def test_deeply_nested_provenance_from_front_layer(self) -> None:
        """
        Deeply nested front_layer override should have correct provenance.
        """
        source = {"level1": {"level2": {"a": 1, "b": 2}}}
        dcm_instance = dcm.DeepChainMap(source, track_provenance=True)

        # Override deeply nested key
        dcm_instance["level1"]["level2"]["b"] = 99

        _, prov = dcm_instance.get_with_provenance("level1")

        # FIXED: Nested provenance structure
        assert prov["level2"]["a"] == 0
        assert prov["level2"]["b"] == -1

    def test_front_only_nested_dict_provenance(self) -> None:
        """
        Dict only in front_layer should have recursive provenance.
        """
        dcm_instance = dcm.DeepChainMap(track_provenance=True)
        dcm_instance["config"] = {"nested": {"deep": 1}}

        _, prov = dcm_instance.get_with_provenance("config")

        # FIXED: All nested keys should have -1 provenance
        assert isinstance(prov["nested"], dict)
        assert prov["nested"]["deep"] == -1


class TestFreezeFunctionExpanded:
    """Additional tests for expanded freeze() function."""

    def test_freeze_already_frozen_mapping(self) -> None:
        """freeze() should return FrozenMapping as-is."""
        frozen = _frozen.FrozenMapping({"a": 1})

        result = _frozen.freeze(frozen)

        assert result is frozen  # Same object, not re-wrapped

    def test_freeze_already_frozen_sequence(self) -> None:
        """freeze() should return FrozenSequence as-is."""
        frozen = _frozen.FrozenSequence([1, 2, 3])

        result = _frozen.freeze(frozen)

        assert result is frozen

    def test_freeze_generic_mapping(self) -> None:
        """freeze() should handle generic Mapping types."""
        import collections as _collections

        ordered = _collections.OrderedDict([("a", 1), ("b", 2)])
        result = _frozen.freeze(ordered)

        assert isinstance(result, _frozen.FrozenMapping)
        assert result["a"] == 1

    def test_freeze_tuple_not_frozen(self) -> None:
        """freeze() should not freeze tuples (already immutable)."""
        t = (1, 2, 3)
        result = _frozen.freeze(t)

        # Tuples are immutable, no need to wrap
        assert result is t


# =============================================================================
# P0-C: Public path-based APIs (set_path, replace_path, delete_path)
# =============================================================================


class TestPublicPathAPIs:
    """
    Tests for the public path-based mutation APIs.

    These APIs provide a cleaner interface for path-based operations
    that were previously only available as private methods.
    """

    def test_set_path_basic(self) -> None:
        """set_path() should set a value at a nested path."""
        d = dcm.DeepChainMap({"a": {"x": 1}})
        d.set_path(("a", "y"), 2)

        assert d["a"]["y"] == 2
        assert d["a"]["x"] == 1  # Original value preserved

    def test_set_path_creates_intermediate_dicts(self) -> None:
        """set_path() should create intermediate dicts as needed."""
        d = dcm.DeepChainMap({})
        d.set_path(("a", "b", "c"), 42)

        assert d["a"]["b"]["c"] == 42

    def test_set_path_merges_by_default(self) -> None:
        """set_path() should merge dicts by default."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.set_path(("a",), {"y": 20, "z": 30})

        assert d["a"]["x"] == 1  # Preserved from original
        assert d["a"]["y"] == 20  # Updated
        assert d["a"]["z"] == 30  # Added

    def test_set_path_no_merge(self) -> None:
        """set_path(merge=False) should replace entirely."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.set_path(("a",), {"z": 3}, merge=False)

        assert d["a"]["z"] == 3
        assert "x" not in d["a"]
        assert "y" not in d["a"]

    def test_set_path_clears_delete_marker(self) -> None:
        """set_path() should clear any DELETE marker at that path."""
        d = dcm.DeepChainMap({"a": 1})
        del d["a"]  # Mark as deleted
        assert "a" not in d

        d.set_path(("a",), 2)
        assert "a" in d
        assert d["a"] == 2

    def test_set_path_empty_path_raises(self) -> None:
        """set_path() should raise ValueError for empty path."""
        d = dcm.DeepChainMap({})

        with _pytest.raises(ValueError, match="cannot be empty"):
            d.set_path((), 42)

    def test_set_path_invalid_path_component_raises(self) -> None:
        """set_path() should raise TypeError for non-string path components."""
        d = dcm.DeepChainMap({})

        with _pytest.raises(TypeError, match="must be strings"):
            d.set_path(("a", 123), 42)  # type: ignore[arg-type]

    def test_replace_path_basic(self) -> None:
        """replace_path() should replace without merging."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.replace_path(("a",), {"z": 3})

        assert d["a"]["z"] == 3
        assert "x" not in d["a"]

    def test_replace_path_empty_path_raises(self) -> None:
        """replace_path() should raise ValueError for empty path."""
        d = dcm.DeepChainMap({})

        with _pytest.raises(ValueError, match="cannot be empty"):
            d.replace_path((), 42)

    def test_delete_path_basic(self) -> None:
        """delete_path() should mark a path as deleted."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})
        d.delete_path(("a", "x"))

        assert "x" not in d["a"]
        assert d["a"]["y"] == 2

    def test_delete_path_clears_list_ops(self) -> None:
        """delete_path() should clear list_ops for that path."""
        d = dcm.DeepChainMap({"items": [1, 2, 3]})
        d.list_append(("items",), 4)
        assert d["items"] == [1, 2, 3, 4]

        d.delete_path(("items",))
        assert "items" not in d
        assert ("items",) not in d.list_ops

    def test_delete_path_empty_path_raises(self) -> None:
        """delete_path() should raise ValueError for empty path."""
        d = dcm.DeepChainMap({})

        with _pytest.raises(ValueError, match="cannot be empty"):
            d.delete_path(())

    def test_delete_path_invalid_path_component_raises(self) -> None:
        """delete_path() should raise TypeError for non-string path components."""
        d = dcm.DeepChainMap({"a": 1})

        with _pytest.raises(TypeError, match="must be strings"):
            d.delete_path(("a", 123))  # type: ignore[arg-type]


# =============================================================================
# P1-A: Unified merge logic verification
# =============================================================================


class TestUnifiedMergeLogic:
    """
    Tests verifying that _deep_merge_dicts delegates to _merge_value.

    This ensures bug fixes in _merge_value automatically apply to
    _deep_merge_dicts (used by set_path for merging).
    """

    def test_deep_merge_handles_delete_marker(self) -> None:
        """_deep_merge_dicts should handle DELETE markers via unified logic."""
        d = dcm.DeepChainMap({})

        base = {"a": 1, "b": 2}
        override = dcm.DcmMapping({"a": dcm.DELETE, "c": 3})

        result = d._deep_merge_dicts(base, override)

        assert "a" not in result  # Deleted
        assert result["b"] == 2  # Preserved
        assert result["c"] == 3  # Added

    def test_deep_merge_handles_replace_marker(self) -> None:
        """_deep_merge_dicts should handle ReplaceMarker via unified logic."""
        d = dcm.DeepChainMap({})

        base = {"a": {"x": 1, "y": 2}}
        override = {"a": dcm.ReplaceMarker({"z": 3})}

        result = d._deep_merge_dicts(base, override)

        # ReplaceMarker prevents merge, replaces entirely
        assert result["a"] == {"z": 3}
        assert "x" not in result["a"]

    def test_deep_merge_recursive_mapping(self) -> None:
        """_deep_merge_dicts should recursively merge nested dicts."""
        d = dcm.DeepChainMap({})

        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 20, "z": 30}}

        result = d._deep_merge_dicts(base, override)

        assert result["a"]["x"] == 1  # Preserved
        assert result["a"]["y"] == 20  # Updated
        assert result["a"]["z"] == 30  # Added

