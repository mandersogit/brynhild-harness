"""
Tests for DeepChainMap YAML extensions.

This file tests:
- DELETE marker and !delete tag
- ReplaceMarker and !replace tag
- DcmMapping behavior
- DcmLoader parsing
- Integration with DeepChainMap layers
"""

import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm


class TestDeleteMarker:
    """Tests for the DELETE marker singleton."""

    def test_singleton_identity(self) -> None:
        """DELETE is always the same object."""
        marker1 = dcm.DELETE
        marker2 = dcm.DELETE
        assert marker1 is marker2

    def test_repr(self) -> None:
        """DELETE has a clear repr."""
        assert repr(dcm.DELETE) == "DELETE"

    def test_is_delete_helper(self) -> None:
        """is_delete() correctly identifies DELETE marker."""
        assert dcm.is_delete(dcm.DELETE) is True
        assert dcm.is_delete(None) is False
        assert dcm.is_delete("delete") is False
        assert dcm.is_delete({}) is False


class TestReplaceMarker:
    """Tests for ReplaceMarker wrapper."""

    def test_wraps_value(self) -> None:
        """ReplaceMarker stores and exposes value."""
        marker = dcm.ReplaceMarker({"key": "value"})
        assert marker.value == {"key": "value"}

    def test_wraps_list(self) -> None:
        """ReplaceMarker works with lists."""
        marker = dcm.ReplaceMarker([1, 2, 3])
        assert marker.value == [1, 2, 3]

    def test_wraps_scalar(self) -> None:
        """ReplaceMarker works with scalars."""
        marker = dcm.ReplaceMarker(42)
        assert marker.value == 42

    def test_wraps_none(self) -> None:
        """ReplaceMarker works with None."""
        marker = dcm.ReplaceMarker(None)
        assert marker.value is None

    def test_repr(self) -> None:
        """ReplaceMarker has informative repr."""
        marker = dcm.ReplaceMarker({"x": 1})
        assert "ReplaceMarker" in repr(marker)
        assert "x" in repr(marker)

    def test_equality(self) -> None:
        """ReplaceMarkers with same value are equal."""
        m1 = dcm.ReplaceMarker({"a": 1})
        m2 = dcm.ReplaceMarker({"a": 1})
        m3 = dcm.ReplaceMarker({"b": 2})
        assert m1 == m2
        assert m1 != m3

    def test_is_replace_helper(self) -> None:
        """is_replace() correctly identifies ReplaceMarker."""
        assert dcm.is_replace(dcm.ReplaceMarker("value")) is True
        assert dcm.is_replace(dcm.DELETE) is False
        assert dcm.is_replace(None) is False
        assert dcm.is_replace("replace") is False


class TestDcmMapping:
    """Tests for DcmMapping behavior."""

    def test_delete_key_raises_keyerror(self) -> None:
        """Accessing a DELETE key raises KeyError."""
        import pytest as _pytest

        data = dcm.DcmMapping({"key": dcm.DELETE, "other": "value"})
        assert "key" not in data
        with _pytest.raises(KeyError):
            _ = data["key"]
        assert data["other"] == "value"

    def test_raw_access_sees_delete(self) -> None:
        """Raw access methods can see DELETE markers."""
        data = dcm.DcmMapping({"key": dcm.DELETE})
        assert data._raw_contains("key")
        assert data._raw_getitem("key") is dcm.DELETE

    def test_replace_marker_unwrapped(self) -> None:
        """ReplaceMarker values are unwrapped on access."""
        data = dcm.DcmMapping({"key": dcm.ReplaceMarker({"inner": "value"})})
        assert data["key"] == {"inner": "value"}

    def test_iter_skips_deleted(self) -> None:
        """Iteration skips DELETE keys."""
        data = dcm.DcmMapping(
            {
                "a": "value_a",
                "b": dcm.DELETE,
                "c": "value_c",
            }
        )
        assert list(data.keys()) == ["a", "c"]

    def test_len_excludes_deleted(self) -> None:
        """Length excludes DELETE keys."""
        data = dcm.DcmMapping(
            {
                "a": "value_a",
                "b": dcm.DELETE,
                "c": "value_c",
            }
        )
        assert len(data) == 2

    def test_delitem_places_delete_marker(self) -> None:
        """del places DELETE marker instead of removing."""
        data = dcm.DcmMapping({"key": "value"})
        del data["key"]
        # Key appears gone
        assert "key" not in data
        # But raw data has DELETE marker
        assert data._raw_getitem("key") is dcm.DELETE

    def test_setitem_overwrites_delete(self) -> None:
        """Setting a value overwrites DELETE marker."""
        data = dcm.DcmMapping({"key": dcm.DELETE})
        data["key"] = "new_value"
        assert data["key"] == "new_value"

    def test_nested_dict_wrapped(self) -> None:
        """Nested dicts are wrapped in DcmMapping."""
        data = dcm.DcmMapping({"outer": {"inner": "value"}})
        inner = data["outer"]
        assert isinstance(inner, dcm.DcmMapping)
        assert inner["inner"] == "value"


class TestDcmLoaderDeleteTag:
    """Tests for !delete tag parsing with DcmMapping."""

    def test_delete_simple(self) -> None:
        """!delete tag produces DELETE marker (key appears absent)."""
        data = _yaml.load("key: !delete", Loader=dcm.DcmLoader)
        assert "key" not in data
        assert data._raw_getitem("key") is dcm.DELETE

    def test_delete_with_null(self) -> None:
        """!delete with explicit null still produces DELETE."""
        data = _yaml.load("key: !delete ~", Loader=dcm.DcmLoader)
        assert "key" not in data
        assert data._raw_getitem("key") is dcm.DELETE

    def test_delete_with_empty_string(self) -> None:
        """!delete with empty string still produces DELETE."""
        data = _yaml.load("key: !delete ''", Loader=dcm.DcmLoader)
        assert "key" not in data

    def test_delete_in_nested_dict(self) -> None:
        """!delete works in nested structures."""
        content = """
        parent:
          child: !delete
          sibling: kept
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)
        assert "child" not in data["parent"]
        assert data["parent"]["sibling"] == "kept"


class TestDcmLoaderReplaceTag:
    """Tests for !replace tag parsing with DcmMapping."""

    def test_replace_dict(self) -> None:
        """!replace with dict is unwrapped on access."""
        content = """
        key: !replace
          only: this
          not_merged: true
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)
        # Value is unwrapped automatically
        assert data["key"] == {"only": "this", "not_merged": True}

    def test_replace_list(self) -> None:
        """!replace with list is unwrapped on access."""
        content = """
        key: !replace [a, b, c]
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)
        assert data["key"] == ["a", "b", "c"]

    def test_replace_scalar(self) -> None:
        """!replace with scalar is unwrapped on access."""
        data = _yaml.load("key: !replace 42", Loader=dcm.DcmLoader)
        assert data["key"] == 42

    def test_replace_nested_dict(self) -> None:
        """!replace preserves nested structure."""
        content = """
        outer: !replace
          level1:
            level2:
              deep: value
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)
        assert data["outer"]["level1"]["level2"]["deep"] == "value"

    def test_raw_access_sees_replace_marker(self) -> None:
        """Raw access can see ReplaceMarker."""
        data = _yaml.load("key: !replace value", Loader=dcm.DcmLoader)
        raw_value = data._raw_getitem("key")
        assert dcm.is_replace(raw_value)


class TestDcmLoaderMixedContent:
    """Tests for mixed regular and tagged content."""

    def test_mixed_tags_and_regular(self) -> None:
        """File with mixed content parses correctly."""
        content = """
        regular: value
        deleted: !delete
        replaced: !replace
          a: 1
          b: 2
        nested:
          also_regular: yes
          also_deleted: !delete
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)

        assert data["regular"] == "value"
        assert "deleted" not in data
        # replaced is unwrapped
        assert data["replaced"] == {"a": 1, "b": 2}
        assert data["nested"]["also_regular"] is True
        assert "also_deleted" not in data["nested"]

    def test_standard_yaml_types_preserved(self) -> None:
        """Standard YAML types work correctly with DcmLoader."""
        content = """
        string: hello
        integer: 42
        float: 3.14
        boolean: true
        null_value: null
        list: [1, 2, 3]
        nested:
          key: value
        """
        data = _yaml.load(content, Loader=dcm.DcmLoader)

        assert data["string"] == "hello"
        assert data["integer"] == 42
        assert data["float"] == 3.14
        assert data["boolean"] is True
        assert data["null_value"] is None
        assert data["list"] == [1, 2, 3]
        assert data["nested"]["key"] == "value"


class TestLoadConvenienceFunction:
    """Tests for dcm.load() convenience function."""

    def test_load_string(self) -> None:
        """load() works with string input."""
        data = dcm.load("key: !delete")
        assert "key" not in data

    def test_load_multiline(self) -> None:
        """load() works with multiline string."""
        content = """
        a: 1
        b: !replace [x, y]
        """
        data = dcm.load(content)
        assert data["a"] == 1
        # replaced is unwrapped
        assert data["b"] == ["x", "y"]


class TestLineTrackingLoaderInheritsTags:
    """Tests that _LineTrackingLoader inherits DCM tags."""

    def test_line_tracking_loader_has_delete(self) -> None:
        """_LineTrackingLoader supports !delete tag."""
        import brynhild.config.sources as sources

        content = """
        normal: value
        removed: !delete
        """
        loader = sources._LineTrackingLoader(content)
        try:
            data = loader.get_single_data()
        finally:
            loader.dispose()

        assert data["normal"] == "value"
        # _LineTrackingLoader produces plain dicts, not DcmMapping
        assert data["removed"] is dcm.DELETE

    def test_line_tracking_loader_has_replace(self) -> None:
        """_LineTrackingLoader supports !replace tag."""
        import brynhild.config.sources as sources

        content = """
        normal: value
        exact: !replace
          only: this
        """
        loader = sources._LineTrackingLoader(content)
        try:
            data = loader.get_single_data()
        finally:
            loader.dispose()

        assert data["normal"] == "value"
        assert dcm.is_replace(data["exact"])
        assert data["exact"].value == {"only": "this"}

    def test_line_tracking_still_tracks_lines(self) -> None:
        """_LineTrackingLoader still records line numbers."""
        import brynhild.config.sources as sources

        content = """normal: value
removed: !delete"""
        loader = sources._LineTrackingLoader(content)
        try:
            _ = loader.get_single_data()
            registry = loader._line_registry
        finally:
            loader.dispose()

        # Lines are tracked
        assert ("normal",) in registry
        assert ("removed",) in registry
        # Line numbers are correct (1-indexed)
        assert registry[("normal",)][0] == 1
        assert registry[("removed",)][0] == 2


class TestDcmMappingCopyAndPickle:
    """Tests for DcmMapping copy and serialization."""

    def test_copy_preserves_values(self) -> None:
        """copy() preserves normal values."""
        original = dcm.DcmMapping({"a": 1, "b": {"nested": 2}})
        copied = original.copy()

        assert copied["a"] == 1
        assert copied["b"] == {"nested": 2}
        assert copied is not original

    def test_copy_preserves_delete_markers(self) -> None:
        """copy() preserves DELETE markers."""
        original = dcm.DcmMapping({"a": dcm.DELETE, "b": "value"})
        copied = original.copy()

        assert "a" not in copied
        assert copied._raw_getitem("a") is dcm.DELETE
        assert copied["b"] == "value"

    def test_copy_preserves_replace_markers(self) -> None:
        """copy() preserves ReplaceMarker."""
        original = dcm.DcmMapping({"a": dcm.ReplaceMarker({"x": 1})})
        copied = original.copy()

        # User sees unwrapped value
        assert copied["a"] == {"x": 1}
        # Raw access shows marker
        assert dcm.is_replace(copied._raw_getitem("a"))

    def test_copy_is_shallow(self) -> None:
        """copy() is shallow - nested objects are shared."""
        nested = {"inner": "value"}
        original = dcm.DcmMapping({"outer": nested})
        copied = original.copy()

        # Nested dict is same object (shallow copy)
        assert original._raw_data()["outer"] is copied._raw_data()["outer"]

    def test_deepcopy_preserves_delete_markers(self) -> None:
        """deepcopy preserves DELETE markers."""
        import copy as _copy

        original = dcm.DcmMapping({"a": dcm.DELETE, "b": "value"})
        copied = _copy.deepcopy(original)

        assert "a" not in copied
        assert copied._raw_getitem("a") is dcm.DELETE
        assert copied["b"] == "value"

    def test_deepcopy_preserves_replace_markers(self) -> None:
        """deepcopy preserves ReplaceMarker (value is deep copied)."""
        import copy as _copy

        inner = {"x": [1, 2, 3]}
        original = dcm.DcmMapping({"a": dcm.ReplaceMarker(inner)})
        copied = _copy.deepcopy(original)

        # User sees unwrapped value
        assert copied["a"] == {"x": [1, 2, 3]}
        # Modification doesn't affect original
        copied["a"]["x"].append(4)
        assert inner["x"] == [1, 2, 3]  # Original unchanged

    def test_deepcopy_is_deep(self) -> None:
        """deepcopy creates independent nested objects."""
        import copy as _copy

        original = dcm.DcmMapping({"outer": {"inner": [1, 2]}})
        copied = _copy.deepcopy(original)

        # Modify copy
        copied._raw_data()["outer"]["inner"].append(3)

        # Original unchanged
        assert original._raw_data()["outer"]["inner"] == [1, 2]

    def test_pickle_roundtrip(self) -> None:
        """DcmMapping survives pickle roundtrip."""
        import pickle as _pickle

        original = dcm.DcmMapping(
            {
                "normal": "value",
                "deleted": dcm.DELETE,
                "replaced": dcm.ReplaceMarker({"x": 1}),
            }
        )

        pickled = _pickle.dumps(original)
        restored = _pickle.loads(pickled)

        assert restored["normal"] == "value"
        assert "deleted" not in restored
        assert restored._raw_getitem("deleted") is dcm.DELETE
        assert restored["replaced"] == {"x": 1}

    def test_delete_marker_pickle_singleton(self) -> None:
        """DELETE marker remains singleton after pickle."""
        import pickle as _pickle

        original = dcm.DELETE
        restored = _pickle.loads(_pickle.dumps(original))

        assert restored is dcm.DELETE


class TestDcmMappingDeleteSetCycles:
    """Tests for delete/set operation cycles."""

    def test_delete_then_set(self) -> None:
        """Setting after delete overwrites DELETE marker."""
        data = dcm.DcmMapping({"key": "original"})

        del data["key"]
        assert "key" not in data

        data["key"] = "restored"
        assert data["key"] == "restored"
        assert data._raw_getitem("key") == "restored"

    def test_set_then_delete(self) -> None:
        """Deleting after set places DELETE marker."""
        data = dcm.DcmMapping({})

        data["key"] = "value"
        assert data["key"] == "value"

        del data["key"]
        assert "key" not in data
        assert data._raw_getitem("key") is dcm.DELETE

    def test_delete_set_delete_cycle(self) -> None:
        """Multiple delete/set cycles work correctly."""
        data = dcm.DcmMapping({"key": "v1"})

        # Cycle 1: delete
        del data["key"]
        assert "key" not in data

        # Cycle 1: set
        data["key"] = "v2"
        assert data["key"] == "v2"

        # Cycle 2: delete
        del data["key"]
        assert "key" not in data

        # Cycle 2: set
        data["key"] = "v3"
        assert data["key"] == "v3"

    def test_multiple_keys_independent(self) -> None:
        """Delete/set on one key doesn't affect others."""
        data = dcm.DcmMapping({"a": 1, "b": 2, "c": 3})

        del data["b"]
        data["a"] = 10

        assert data["a"] == 10
        assert "b" not in data
        assert data["c"] == 3


# =============================================================================
# YAML Integration with DeepChainMap Layers
# =============================================================================


def load_layer(yaml_str: str) -> dict:
    """Load YAML string using DcmLoader."""
    return _yaml.load(yaml_str, Loader=dcm.DcmLoader)


def make_dcm(*yaml_strings: str) -> dcm.DeepChainMap:
    """Create DCM from YAML strings (first = highest priority)."""
    layers = [load_layer(s) for s in yaml_strings]
    return dcm.DeepChainMap(*layers)


# =============================================================================
# DELETE in Different Layer Positions
# =============================================================================


class TestDeleteFrontLayer:
    """DELETE in the highest priority layer."""

    def test_delete_removes_key_from_lower_layer(self) -> None:
        """DELETE in front layer removes key that exists in back layer."""
        front = "removed_key: !delete"
        back = """
        removed_key: should_disappear
        other_key: still_here
        """
        result = make_dcm(front, back)

        assert "removed_key" not in result
        assert result["other_key"] == "still_here"

    def test_delete_removes_nested_dict_from_lower_layer(self) -> None:
        """DELETE removes entire nested structure."""
        front = """
        settings:
          debug: !delete
        """
        back = """
        settings:
          debug:
            level: verbose
            file: /var/log/debug.log
          production: true
        """
        result = make_dcm(front, back)

        assert "debug" not in result["settings"]
        assert result["settings"]["production"] is True

    def test_delete_deeply_nested_key(self) -> None:
        """DELETE works at arbitrary nesting depth."""
        front = """
        a:
          b:
            c:
              d: !delete
        """
        back = """
        a:
          b:
            c:
              d: deep_value
              e: sibling_value
            f: uncle_value
        """
        result = make_dcm(front, back)

        assert "d" not in result["a"]["b"]["c"]
        assert result["a"]["b"]["c"]["e"] == "sibling_value"
        assert result["a"]["b"]["f"] == "uncle_value"


class TestDeleteMiddleLayer:
    """DELETE in a middle priority layer."""

    def test_delete_in_middle_removes_from_back(self) -> None:
        """DELETE in middle layer removes key from back layer."""
        front = """
        unrelated: front_value
        """
        middle = """
        removed: !delete
        """
        back = """
        removed: back_value
        other: back_other
        """
        result = make_dcm(front, middle, back)

        assert "removed" not in result
        assert result["other"] == "back_other"
        assert result["unrelated"] == "front_value"

    def test_front_can_restore_key_deleted_in_middle(self) -> None:
        """Front layer can provide value for key deleted in middle."""
        front = """
        restored: front_restored_value
        """
        middle = """
        restored: !delete
        """
        back = """
        restored: back_value
        """
        result = make_dcm(front, middle, back)

        # Front layer value should appear (it's higher priority than the delete)
        assert result["restored"] == "front_restored_value"

    def test_delete_in_middle_nested(self) -> None:
        """DELETE in middle layer affects nested keys."""
        front = """
        config:
          added_by_front: "yes"
        """
        middle = """
        config:
          removed_section: !delete
        """
        back = """
        config:
          removed_section:
            setting1: value1
            setting2: value2
          kept_section:
            data: preserved
        """
        result = make_dcm(front, middle, back)

        assert "removed_section" not in result["config"]
        assert result["config"]["kept_section"]["data"] == "preserved"
        assert result["config"]["added_by_front"] == "yes"


class TestDeleteBackLayer:
    """DELETE in the lowest priority layer (edge case)."""

    def test_delete_in_back_has_no_effect_on_key_from_front(self) -> None:
        """DELETE in back layer doesn't affect key set in front layer."""
        front = """
        key: front_value
        """
        back = """
        key: !delete
        """
        result = make_dcm(front, back)

        # Front layer wins, delete in back is irrelevant
        assert result["key"] == "front_value"

    def test_delete_in_back_layer_alone_removes_nothing(self) -> None:
        """DELETE in back layer with no other layers just means key absent."""
        layer = """
        present: value
        absent: !delete
        """
        result = make_dcm(layer)

        assert result["present"] == "value"
        assert "absent" not in result

    def test_delete_in_back_for_key_not_in_any_layer(self) -> None:
        """DELETE for key that doesn't exist elsewhere is benign."""
        front = """
        existing: value
        """
        back = """
        phantom: !delete
        """
        result = make_dcm(front, back)

        assert result["existing"] == "value"
        assert "phantom" not in result


# =============================================================================
# REPLACE in Different Layer Positions
# =============================================================================


class TestReplaceFrontLayer:
    """REPLACE in the highest priority layer."""

    def test_replace_dict_prevents_deep_merge(self) -> None:
        """!replace dict completely replaces, no deep merge."""
        front = """
        settings: !replace
          only: this
        """
        back = """
        settings:
          merged: normally
          deep:
            nested: value
        """
        result = make_dcm(front, back)

        # Back layer settings should be completely replaced
        assert result["settings"] == {"only": "this"}
        assert "merged" not in result["settings"]
        assert "deep" not in result["settings"]

    def test_replace_nested_dict(self) -> None:
        """!replace on nested dict replaces just that branch."""
        front = """
        outer:
          inner: !replace
            replaced: "yes"
        """
        back = """
        outer:
          inner:
            original: data
            more: stuff
          sibling: preserved
        """
        result = make_dcm(front, back)

        assert result["outer"]["inner"] == {"replaced": "yes"}
        assert result["outer"]["sibling"] == "preserved"

    def test_replace_list_explicit(self) -> None:
        """!replace list is explicit replacement (lists already replace by default)."""
        front = """
        items: !replace [a, b, c]
        """
        back = """
        items: [x, y, z]
        """
        result = make_dcm(front, back)

        # Lists already replace, but !replace makes intent explicit
        assert list(result["items"]) == ["a", "b", "c"]

    def test_replace_deeply_nested(self) -> None:
        """!replace works at arbitrary depth."""
        front = """
        level1:
          level2:
            level3: !replace
              fresh: start
        """
        back = """
        level1:
          level2:
            level3:
              old: data
              complex:
                nested: structure
            level3_sibling: kept
          level2_sibling: also_kept
        """
        result = make_dcm(front, back)

        assert result["level1"]["level2"]["level3"] == {"fresh": "start"}
        assert result["level1"]["level2"]["level3_sibling"] == "kept"
        assert result["level1"]["level2_sibling"] == "also_kept"


class TestReplaceMiddleLayer:
    """REPLACE in a middle priority layer."""

    def test_replace_in_middle_replaces_back(self) -> None:
        """!replace in middle replaces back layer value."""
        front = """
        other: front
        """
        middle = """
        config: !replace
          middle_only: true
        """
        back = """
        config:
          back_data: value
          nested:
            deep: structure
        """
        result = make_dcm(front, middle, back)

        # Middle's replace should have wiped back's config
        assert result["config"] == {"middle_only": True}

    def test_front_can_merge_onto_replaced_middle(self) -> None:
        """Front layer deep-merges onto middle's replaced dict."""
        front = """
        config:
          from_front: added
        """
        middle = """
        config: !replace
          base: middle
        """
        back = """
        config:
          from_back: ignored
        """
        result = make_dcm(front, middle, back)

        # Middle replaces back, then front merges onto that
        assert result["config"]["base"] == "middle"
        assert result["config"]["from_front"] == "added"
        assert "from_back" not in result["config"]

    def test_replace_in_middle_nested(self) -> None:
        """!replace in middle on nested key."""
        front = """
        root:
          branch:
            leaf: front_leaf
        """
        middle = """
        root:
          branch: !replace
            clean: slate
        """
        back = """
        root:
          branch:
            old: data
            deep:
              nested: stuff
        """
        result = make_dcm(front, middle, back)

        # Middle replaces branch, front merges leaf into it
        assert result["root"]["branch"]["clean"] == "slate"
        assert result["root"]["branch"]["leaf"] == "front_leaf"
        assert "old" not in result["root"]["branch"]
        assert "deep" not in result["root"]["branch"]


class TestReplaceBackLayer:
    """REPLACE in the lowest priority layer."""

    def test_replace_in_back_still_allows_merge_from_front(self) -> None:
        """!replace in back just sets the base, front still merges."""
        front = """
        data:
          added: by_front
        """
        back = """
        data: !replace
          base: value
        """
        result = make_dcm(front, back)

        # Back's replace sets base, front merges on top
        assert result["data"]["base"] == "value"
        assert result["data"]["added"] == "by_front"

    def test_replace_in_back_alone(self) -> None:
        """!replace in single layer just unwraps the value."""
        layer = """
        config: !replace
          setting: value
        """
        result = make_dcm(layer)

        assert result["config"] == {"setting": "value"}


# =============================================================================
# DELETE and REPLACE Interactions
# =============================================================================


class TestDeleteReplaceInteractions:
    """Interactions between DELETE and REPLACE markers."""

    def test_delete_key_that_was_replaced_below(self) -> None:
        """DELETE can remove a key that was !replace'd in a lower layer."""
        front = """
        removed: !delete
        """
        back = """
        removed: !replace
          complex: structure
          should: disappear
        """
        result = make_dcm(front, back)

        assert "removed" not in result

    def test_replace_key_that_was_deleted_below(self) -> None:
        """!replace can provide value for key deleted in lower layer."""
        front = """
        restored: !replace
          new: value
        """
        back = """
        restored: !delete
        """
        result = make_dcm(front, back)

        # Front's replace wins over back's delete
        assert result["restored"] == {"new": "value"}

    def test_mixed_delete_and_replace_in_same_dict(self) -> None:
        """Same layer can have both DELETE and REPLACE on different keys."""
        front = """
        removed: !delete
        replaced: !replace
          only: this
        normal: value
        """
        back = """
        removed: should_go
        replaced:
          should: be_replaced
          entirely: gone
        normal: back_normal
        extra: back_extra
        """
        result = make_dcm(front, back)

        assert "removed" not in result
        assert result["replaced"] == {"only": "this"}
        assert result["normal"] == "value"
        assert result["extra"] == "back_extra"

    def test_replace_then_delete_nested(self) -> None:
        """!replace in one branch, !delete in another at same level."""
        front = """
        settings:
          logging: !delete
          database: !replace
            host: localhost
        """
        back = """
        settings:
          logging:
            level: debug
            file: /var/log/app.log
          database:
            host: production.db
            port: 5432
            credentials:
              user: admin
          cache:
            enabled: true
        """
        result = make_dcm(front, back)

        assert "logging" not in result["settings"]
        assert result["settings"]["database"] == {"host": "localhost"}
        assert result["settings"]["cache"]["enabled"] is True


# =============================================================================
# Complex Multi-Layer Scenarios
# =============================================================================


class TestComplexScenarios:
    """Complex real-world-like scenarios with multiple layers."""

    def test_three_layer_override_chain(self) -> None:
        """Builtin -> User -> Project override chain with markers."""
        builtin = """
        model:
          name: default-model
          parameters:
            temperature: 0.7
            max_tokens: 1000
        tools:
          - read
          - write
        debug: false
        """
        user = """
        model:
          name: user-preferred-model
          parameters:
            max_tokens: 2000
        features:
          experimental: !delete
        """
        project = """
        model:
          parameters: !replace
            temperature: 0.0
            deterministic: true
        tools: !replace [read]
        features:
          experimental: true
        debug: true
        """
        # Priority: project > user > builtin
        result = make_dcm(project, user, builtin)

        # Model name from user (project didn't set it)
        assert result["model"]["name"] == "user-preferred-model"
        # Parameters completely replaced by project
        assert result["model"]["parameters"] == {"temperature": 0.0, "deterministic": True}
        assert "max_tokens" not in result["model"]["parameters"]
        # Tools replaced
        assert list(result["tools"]) == ["read"]
        # experimental: user deleted, but project (higher priority) sets it
        assert result["features"]["experimental"] is True
        # debug from project
        assert result["debug"] is True

    def test_profile_inheritance_simulation(self) -> None:
        """Simulate profile inheritance with modes."""
        base_mode = """
        system_prompt: |
          You are a helpful assistant.
        max_tokens: 4096
        api_params:
          temperature: 0.7
        patterns:
          - persistence
          - clarity
        """
        storytelling_mode = """
        system_prompt: !replace |
          You are a creative storyteller.
        api_params:
          temperature: 1.2
          top_p: 0.95
        patterns: !replace
          - creativity
          - narrative_flow
        """
        model_specific = """
        max_tokens: 8192
        api_params:
          model_quirk: enabled
        patterns:
          - +model_specific_pattern
        """
        # model_specific > storytelling_mode > base_mode
        result = make_dcm(model_specific, storytelling_mode, base_mode)

        # System prompt replaced by storytelling
        assert "creative storyteller" in result["system_prompt"]
        # max_tokens from model_specific
        assert result["max_tokens"] == 8192
        # api_params merges: model_specific + storytelling (storytelling replaced base)
        assert result["api_params"]["temperature"] == 1.2
        assert result["api_params"]["top_p"] == 0.95
        assert result["api_params"]["model_quirk"] == "enabled"
        # patterns replaced by storytelling, then model-specific can't add (lists replace)
        # Note: with current list semantics, model_specific's patterns would replace
        # This test documents current behavior; we might want different list semantics
        assert "+model_specific_pattern" in list(result["patterns"])

    def test_delete_entire_section_restore_partially(self) -> None:
        """Delete entire section then selectively restore parts."""
        base = """
        features:
          alpha:
            enabled: true
            config:
              level: 1
          beta:
            enabled: true
            config:
              level: 2
          gamma:
            enabled: true
        """
        middle = """
        features: !delete
        """
        top = """
        features:
          alpha:
            enabled: true
            config:
              level: 10
        """
        result = make_dcm(top, middle, base)

        # Middle deleted all features, top restored only alpha
        assert result["features"]["alpha"]["enabled"] is True
        assert result["features"]["alpha"]["config"]["level"] == 10
        assert "beta" not in result["features"]
        assert "gamma" not in result["features"]

    def test_surgical_nested_operations(self) -> None:
        """Precise surgical operations at different nesting levels."""
        layer1 = """
        database:
          primary:
            host: prod.db
            port: 5432
            credentials:
              user: admin
              password: secret
          replica:
            host: replica.db
            port: 5432
        cache:
          redis:
            host: cache.local
            port: 6379
        """
        layer2 = """
        database:
          primary:
            credentials: !delete
          replica: !replace
            host: new-replica.db
        cache:
          redis:
            ttl: 3600
        """
        result = make_dcm(layer2, layer1)

        # Primary host/port preserved, credentials deleted
        assert result["database"]["primary"]["host"] == "prod.db"
        assert result["database"]["primary"]["port"] == 5432
        assert "credentials" not in result["database"]["primary"]

        # Replica entirely replaced
        assert result["database"]["replica"] == {"host": "new-replica.db"}
        assert "port" not in result["database"]["replica"]

        # Cache merged normally
        assert result["cache"]["redis"]["host"] == "cache.local"
        assert result["cache"]["redis"]["port"] == 6379
        assert result["cache"]["redis"]["ttl"] == 3600


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_delete_nonexistent_key_benign(self) -> None:
        """DELETE for key that doesn't exist anywhere is fine."""
        front = """
        ghost: !delete
        """
        back = """
        real: value
        """
        result = make_dcm(front, back)

        assert result["real"] == "value"
        assert "ghost" not in result

    def test_replace_with_empty_dict(self) -> None:
        """!replace with empty dict is valid."""
        front = """
        config: !replace {}
        """
        back = """
        config:
          lots: of
          nested: data
        """
        result = make_dcm(front, back)

        assert result["config"] == {}

    def test_replace_with_empty_list(self) -> None:
        """!replace with empty list is valid."""
        front = """
        items: !replace []
        """
        back = """
        items: [a, b, c, d, e]
        """
        result = make_dcm(front, back)

        assert list(result["items"]) == []

    def test_replace_with_null(self) -> None:
        """!replace with null sets the value to None."""
        front = """
        value: !replace ~
        """
        back = """
        value:
          complex: data
        """
        result = make_dcm(front, back)

        # The value should be None (null)
        assert result["value"] is None

    def test_delete_at_root_level(self) -> None:
        """DELETE can remove top-level keys."""
        front = """
        keep: "yes"
        remove: !delete
        """
        back = """
        keep: back
        remove: back_remove
        also_keep: back_also
        """
        result = make_dcm(front, back)

        assert result["keep"] == "yes"
        assert "remove" not in result
        assert result["also_keep"] == "back_also"

    def test_replace_scalar_with_dict(self) -> None:
        """!replace can change type from scalar to dict."""
        front = """
        setting: !replace
          now_a: dict
        """
        back = """
        setting: was_a_string
        """
        result = make_dcm(front, back)

        assert result["setting"] == {"now_a": "dict"}

    def test_replace_dict_with_scalar(self) -> None:
        """!replace can change type from dict to scalar."""
        front = """
        setting: !replace simple_string
        """
        back = """
        setting:
          was: a_dict
        """
        result = make_dcm(front, back)

        assert result["setting"] == "simple_string"

    def test_many_layers_with_markers(self) -> None:
        """Multiple layers all with markers."""
        layer1 = "a: l1"
        layer2 = "a: !delete"
        layer3 = "a: l3"
        layer4 = """
        a: !replace
          from: l4
        """
        layer5 = "a: l5"

        # Priority: layer1 > layer2 > layer3 > layer4 > layer5
        result = make_dcm(layer1, layer2, layer3, layer4, layer5)

        # layer1 wins with "l1"
        assert result["a"] == "l1"

    def test_only_deletes(self) -> None:
        """Layers that only delete things."""
        front = """
        removed1: !delete
        """
        middle = """
        removed2: !delete
        """
        back = """
        removed1: value1
        removed2: value2
        kept: value3
        """
        result = make_dcm(front, middle, back)

        assert "removed1" not in result
        assert "removed2" not in result
        assert result["kept"] == "value3"

    def test_only_replaces(self) -> None:
        """Layers that only replace things."""
        front = """
        data: !replace
          front_only: true
        """
        back = """
        data:
          back: data
          nested:
            deep: structure
        """
        result = make_dcm(front, back)

        assert result["data"] == {"front_only": True}


class TestReplaceContainingDelete:
    """Tests for REPLACE values that contain DELETE markers inside."""

    def test_replace_dict_with_delete_inside(self) -> None:
        """REPLACE dict containing !delete - delete is preserved inside."""
        front = """
        settings: !replace
          enabled: true
          legacy_option: !delete
        """
        back = """
        settings:
          enabled: false
          legacy_option: old_value
          other: data
        """
        result = make_dcm(front, back)

        # REPLACE means no merge with back
        assert result["settings"]["enabled"] is True
        # DELETE inside REPLACE removes the key from the replaced dict
        assert "legacy_option" not in result["settings"]
        # "other" from back is NOT merged (REPLACE prevents merge)
        assert "other" not in result["settings"]

    def test_replace_nested_with_delete(self) -> None:
        """Nested REPLACE with DELETE inside."""
        front = """
        config:
          database: !replace
            host: newhost
            credentials: !delete
        """
        back = """
        config:
          database:
            host: oldhost
            port: 5432
            credentials:
              user: admin
              pass: secret
        """
        result = make_dcm(front, back)

        # database is replaced entirely
        db = result["config"]["database"]
        assert db["host"] == "newhost"
        assert "credentials" not in db  # DELETE inside REPLACE
        assert "port" not in db  # REPLACE prevents merge

    def test_delete_inside_replace_affects_iteration(self) -> None:
        """DELETE inside REPLACE affects iteration of the replaced value."""
        front = """
        items: !replace
          a: 1
          b: !delete
          c: 3
        """
        result = make_dcm(front)

        items = result["items"]
        keys = list(items.keys())
        assert sorted(keys) == ["a", "c"]
        assert "b" not in items


class TestProvenanceWithDcmMapping:
    """Tests for provenance tracking with DcmMapping layers."""

    def test_provenance_with_dcm_mapping_layers(self) -> None:
        """Provenance works with DcmMapping source layers."""
        import brynhild.utils.deep_chain_map as dcm

        layer0 = dcm.load("""
        model:
          name: from_layer_0
        """)
        layer1 = dcm.load("""
        model:
          name: from_layer_1
          extra: data
        """)

        chain = dcm.DeepChainMap(layer0, layer1, track_provenance=True)
        value, provenance = chain.get_with_provenance("model")

        # name comes from layer 0 (higher priority)
        assert value["name"] == "from_layer_0"
        assert provenance.get("name") == 0

        # extra comes from layer 1, but provenance only tracks at the top dict level
        assert value["extra"] == "data"
        # The dict itself has provenance 1 (first found in layer 1), name override is tracked
        assert provenance.get(".") == 1

    def test_provenance_with_delete_in_layer(self) -> None:
        """Provenance handles DELETE in source layers."""
        import brynhild.utils.deep_chain_map as dcm

        layer0 = dcm.load("""
        config:
          removed: !delete
          kept: from_front
        """)
        layer1 = dcm.load("""
        config:
          removed: was_here
          kept: from_back
          extra: value
        """)

        chain = dcm.DeepChainMap(layer0, layer1, track_provenance=True)
        value, provenance = chain.get_with_provenance("config")

        # removed is deleted
        assert "removed" not in value
        # kept comes from layer 0
        assert value["kept"] == "from_front"
        # extra comes from layer 1
        assert value["extra"] == "value"


class TestDcmDeleteSetCyclesIntegration:
    """Tests for delete/set cycles through DCM (not just DcmMapping)."""

    def test_dcm_delete_then_set_cycle(self) -> None:
        """Delete then set through DCM works correctly."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"key": "original"}
        chain = dcm.DeepChainMap(source)

        # Delete
        del chain["key"]
        assert "key" not in chain

        # Set
        chain["key"] = "restored"
        assert chain["key"] == "restored"

    def test_dcm_multiple_cycles(self) -> None:
        """Multiple delete/set cycles through DCM."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"key": "v0"}
        chain = dcm.DeepChainMap(source)

        for i in range(1, 5):
            del chain["key"]
            assert "key" not in chain

            chain["key"] = f"v{i}"
            assert chain["key"] == f"v{i}"

        assert chain["key"] == "v4"

    def test_dcm_nested_delete_set_cycle(self) -> None:
        """Delete/set cycles on nested keys."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"outer": {"inner": "original"}}
        chain = dcm.DeepChainMap(source)

        # Delete nested
        del chain["outer"]["inner"]
        assert "inner" not in chain["outer"]

        # Set nested
        chain["outer"]["inner"] = "restored"
        assert chain["outer"]["inner"] == "restored"

        # Delete again
        del chain["outer"]["inner"]
        assert "inner" not in chain["outer"]
