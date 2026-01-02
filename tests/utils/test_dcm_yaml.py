"""Tests for DeepChainMap YAML extensions (!delete, !replace) and DcmMapping."""

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
