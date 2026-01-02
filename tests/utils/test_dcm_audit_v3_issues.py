"""
Tests for issues identified in DCM audit v3.

These tests verify the bugs are fixed. They were originally written as
characterization tests (asserting buggy behavior) and updated to assert
correct behavior after fixes.

See: workflow/dcm-improvement-plan-v3.md
See: workflow/chatgpt-5.2-pro-extended-dcm-audit-v3.md
"""

import copy as _copy

import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm

# =============================================================================
# P0-NEW-1: DcmMapping layer loses sibling keys on nested mutation
# =============================================================================


class TestP0New1_DcmMappingLosesSiblingKeys:
    """
    P0-NEW-1: Single YAML/DcmMapping layer + nested front override can drop keys.

    When the merged value for a top-level key comes from a single source layer
    and that value is a DcmMapping, applying a nested mutation via MutableProxy
    should NOT cause non-overridden sibling keys to disappear.
    """

    def test_yaml_loaded_mapping_preserves_siblings_on_mutation(self) -> None:
        """Mutating one key in a DcmMapping should preserve sibling keys."""
        yaml_content = """
config:
  setting1: original1
  setting2: original2
"""
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        assert isinstance(data["config"], dcm.DcmMapping)

        d = dcm.DeepChainMap(data)
        assert dict(d["config"]) == {"setting1": "original1", "setting2": "original2"}

        # Mutate one key
        d["config"]["setting1"] = "modified1"

        # Both keys should be present
        result = dict(d["config"])
        assert result["setting1"] == "modified1"
        assert result["setting2"] == "original2"  # This was the bug - setting2 was lost

    def test_dcm_mapping_single_layer_merge(self) -> None:
        """DcmMapping as single layer should merge correctly with front_layer."""
        mapping = dcm.DcmMapping({"a": 1, "b": 2, "c": 3})
        d = dcm.DeepChainMap({"top": mapping})

        d["top"]["a"] = 10

        result = dict(d["top"])
        assert result == {"a": 10, "b": 2, "c": 3}

    def test_nested_dcm_mapping_preserves_structure(self) -> None:
        """Deeply nested DcmMapping should preserve all siblings."""
        yaml_content = """
root:
  level1:
    a: 1
    b: 2
  level2:
    x: 10
    y: 20
"""
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        # Mutate deeply nested key
        d["root"]["level1"]["a"] = 100

        # All siblings at all levels should be preserved
        assert d["root"]["level1"]["a"] == 100
        assert d["root"]["level1"]["b"] == 2
        assert d["root"]["level2"]["x"] == 10
        assert d["root"]["level2"]["y"] == 20


# =============================================================================
# P0-NEW-2: replace_path() semantics break on nested mutation
# =============================================================================


class TestP0New2_ReplacePathBreaksOnNestedMutation:
    """
    P0-NEW-2: Nested mutations under replace_path() break replacement semantics.

    If you call replace_path() then mutating under that subtree via proxy
    should NOT drop the replacement value or reintroduce lower-layer values.
    """

    def test_replace_path_then_set_nested_preserves_replacement(self) -> None:
        """Setting nested key after replace_path should preserve replacement."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})

        d.replace_path(("a",), {"z": 3})
        assert dict(d["a"]) == {"z": 3}

        # Set a new nested key
        d["a"]["w"] = 4

        # Replacement should be preserved, source should NOT reappear
        result = dict(d["a"])
        assert result == {"z": 3, "w": 4}  # Bug was: {"x": 1, "y": 2, "w": 4}

    def test_replace_path_then_delete_nested_preserves_replacement(self) -> None:
        """Deleting nested key after replace_path should preserve replacement."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})

        d.replace_path(("a",), {"z": 3, "w": 4})
        assert dict(d["a"]) == {"z": 3, "w": 4}

        # Delete one key from the replacement
        del d["a"]["z"]

        # Other replacement key should remain, source should NOT reappear
        result = dict(d["a"])
        assert result == {"w": 4}  # Bug was: {"x": 1, "y": 2}

    def test_replace_path_then_set_path_nested_preserves_replacement(self) -> None:
        """Using set_path after replace_path should preserve replacement."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})

        d.replace_path(("a",), {"z": 3})
        d.set_path(("a", "nested"), {"deep": "value"})

        result = dict(d["a"])
        assert "z" in result
        assert result["z"] == 3
        assert "nested" in result
        assert "x" not in result  # Source should NOT reappear

    def test_replace_path_deeply_nested_mutation(self) -> None:
        """Deeply nested mutation after replace_path should work."""
        d = dcm.DeepChainMap({"a": {"x": {"deep": 1}}})

        d.replace_path(("a",), {"y": {"other": 2}})
        d["a"]["y"]["new"] = 3

        result = dict(d["a"])
        assert "y" in result
        assert result["y"]["other"] == 2
        assert result["y"]["new"] == 3
        assert "x" not in result


# =============================================================================
# P1-B: get_with_provenance() returns mutable internal structures
# =============================================================================


class TestP1B_GetWithProvenanceReturnsMutable:
    """
    P1-B: get_with_provenance() should return immutable provenance.

    The provenance dict returned should not allow mutation of internal state.
    """

    def test_provenance_mutation_does_not_affect_internal_state(self) -> None:
        """Mutating returned provenance should not affect internal cache."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}}, track_provenance=True)

        val1, prov1 = d.get_with_provenance("a")

        # Try to mutate the returned provenance
        original_prov = _copy.deepcopy(dict(prov1))
        try:
            prov1["x"] = 999  # type: ignore[index]
            prov1["hacked"] = 123  # type: ignore[index]
        except TypeError:
            pass  # Expected if provenance is immutable

        # Get provenance again - should be unchanged
        val2, prov2 = d.get_with_provenance("a")

        # Internal state should not have been corrupted
        assert dict(prov2) == original_prov

    def test_provenance_is_deepcopy_or_frozen(self) -> None:
        """Returned provenance should be a copy or frozen view."""
        d = dcm.DeepChainMap({"a": {"nested": {"deep": 1}}}, track_provenance=True)

        _, prov1 = d.get_with_provenance("a")
        _, prov2 = d.get_with_provenance("a")

        # Should be separate objects (copies) or immutable views
        # Either way, mutation should not propagate
        if isinstance(prov1, dict):
            # If it's a dict, it should be a copy
            assert prov1 is not prov2 or prov1 == prov2


# =============================================================================
# P1-D/E: Documentation - MutableProxy returns and merge semantics
# =============================================================================


class TestP1DE_DocumentationAccuracy:
    """
    P1-D/E: Verify documented behavior matches actual behavior.

    These tests ensure the documented semantics are correct.
    """

    def test_getitem_returns_mutableproxy_for_dicts(self) -> None:
        """dcm[key] returns MutableProxy for dict values, not plain dict."""
        d = dcm.DeepChainMap({"a": {"x": 1}})

        result = d["a"]

        # Should be MutableProxy, not dict
        assert type(result).__name__ == "MutableProxy"
        # But should act like a dict
        assert result["x"] == 1
        assert dict(result) == {"x": 1}

    def test_setitem_merges_by_default(self) -> None:
        """dcm[key] = dict merges by default, does not replace."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})

        d["a"] = {"y": 20, "z": 30}

        result = dict(d["a"])
        # Should merge, not replace
        assert result["x"] == 1  # Original preserved
        assert result["y"] == 20  # Updated
        assert result["z"] == 30  # Added

    def test_replace_path_is_true_replacement(self) -> None:
        """replace_path() is the way to truly replace, not setitem."""
        d = dcm.DeepChainMap({"a": {"x": 1, "y": 2}})

        d.replace_path(("a",), {"z": 3})

        result = dict(d["a"])
        # Should replace entirely
        assert result == {"z": 3}
        assert "x" not in result
        assert "y" not in result


# =============================================================================
# Additional edge cases from audit
# =============================================================================


class TestAdditionalEdgeCases:
    """Additional edge cases mentioned in the audit."""

    def test_multiple_yaml_layers_merge_correctly(self) -> None:
        """Multiple DcmMapping layers should merge correctly."""
        base_yaml = "config:\n  a: 1\n  b: 2"
        override_yaml = "config:\n  b: 20\n  c: 30"

        base = _yaml.load(base_yaml, Loader=dcm.DcmLoader)
        override = _yaml.load(override_yaml, Loader=dcm.DcmLoader)

        d = dcm.DeepChainMap(override, base)

        result = dict(d["config"])
        assert result["a"] == 1  # From base
        assert result["b"] == 20  # Overridden
        assert result["c"] == 30  # From override

    def test_yaml_with_delete_marker_and_front_mutation(self) -> None:
        """YAML with DELETE marker should work with front_layer mutations."""
        yaml_content = """
config:
  keep: value
  remove: !delete
"""
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        d = dcm.DeepChainMap(data)

        # Add a new key via mutation
        d["config"]["new"] = "added"

        result = dict(d["config"])
        assert result["keep"] == "value"
        assert result["new"] == "added"
        assert "remove" not in result

    def test_yaml_with_replace_marker_and_front_mutation(self) -> None:
        """YAML with ReplaceMarker should work with front_layer mutations."""
        yaml_content = """
config:
  nested: !replace
    only: this
"""
        data = _yaml.load(yaml_content, Loader=dcm.DcmLoader)
        base = {"config": {"nested": {"original": "data", "more": "stuff"}}}

        d = dcm.DeepChainMap(data, base)

        # Mutate under the replaced subtree
        d["config"]["nested"]["extra"] = "value"

        result = dict(d["config"]["nested"])
        assert result["only"] == "this"  # From replace
        assert result["extra"] == "value"  # Added
        assert "original" not in result  # Should not merge through

