"""
Tests for frozen wrappers (FrozenMapping, FrozenSequence, freeze).

These wrappers provide read-only views of mutable containers to prevent
accidental mutation of cached values and source layers.
"""

import collections as _collections
import typing as _typing

import pytest as _pytest

import brynhild.utils.deep_chain_map._frozen as _frozen

# Re-export for convenience in tests
FrozenMapping = _frozen.FrozenMapping
FrozenSequence = _frozen.FrozenSequence
freeze = _frozen.freeze


class TestFrozenMapping:
    """Tests for FrozenMapping read-only dict wrapper."""

    def test_getitem_returns_value(self) -> None:
        """Can access values by key."""
        fm = FrozenMapping({"a": 1, "b": 2})

        assert fm["a"] == 1
        assert fm["b"] == 2

    def test_getitem_missing_raises_keyerror(self) -> None:
        """Missing key raises KeyError."""
        fm = FrozenMapping({"a": 1})

        with _pytest.raises(KeyError):
            _ = fm["missing"]

    def test_len(self) -> None:
        """len() returns number of keys."""
        fm = FrozenMapping({"a": 1, "b": 2, "c": 3})

        assert len(fm) == 3

    def test_iter(self) -> None:
        """Iteration yields all keys."""
        fm = FrozenMapping({"a": 1, "b": 2})

        assert set(fm) == {"a", "b"}

    def test_contains(self) -> None:
        """'in' operator works."""
        fm = FrozenMapping({"a": 1})

        assert "a" in fm
        assert "missing" not in fm

    def test_nested_dict_is_frozen(self) -> None:
        """Nested dicts are returned as FrozenMapping."""
        fm = FrozenMapping({"outer": {"inner": 1}})

        nested = fm["outer"]

        assert isinstance(nested, FrozenMapping)
        assert nested["inner"] == 1

    def test_nested_list_is_frozen(self) -> None:
        """Nested lists are returned as FrozenSequence."""
        fm = FrozenMapping({"items": [1, 2, 3]})

        items = fm["items"]

        assert isinstance(items, FrozenSequence)
        assert list(items) == [1, 2, 3]

    def test_scalar_values_unchanged(self) -> None:
        """Scalar values (int, str, etc.) returned as-is."""
        fm = FrozenMapping(
            {
                "int": 42,
                "str": "hello",
                "float": 3.14,
                "bool": True,
                "none": None,
            }
        )

        assert fm["int"] == 42
        assert fm["str"] == "hello"
        assert fm["float"] == 3.14
        assert fm["bool"] is True
        assert fm["none"] is None

    def test_repr(self) -> None:
        """repr shows FrozenMapping with content."""
        fm = FrozenMapping({"a": 1})

        result = repr(fm)

        assert "FrozenMapping" in result
        assert "'a'" in result

    def test_eq_with_dict(self) -> None:
        """FrozenMapping equals dict with same content."""
        fm = FrozenMapping({"a": 1, "b": 2})

        assert fm == {"a": 1, "b": 2}
        assert fm == {"a": 1, "b": 2}

    def test_eq_with_frozen_mapping(self) -> None:
        """FrozenMapping equals another FrozenMapping with same content."""
        fm1 = FrozenMapping({"a": 1})
        fm2 = FrozenMapping({"a": 1})

        assert fm1 == fm2

    def test_eq_different_content(self) -> None:
        """FrozenMapping not equal to dict with different content."""
        fm = FrozenMapping({"a": 1})

        assert fm != {"a": 2}
        assert fm != {"b": 1}

    def test_eq_with_non_mapping_returns_not_implemented(self) -> None:
        """Comparison with non-Mapping returns NotImplemented."""
        fm = FrozenMapping({"a": 1})

        # Comparing with non-Mapping types
        assert fm != 42
        assert fm != "string"
        assert fm != [1, 2, 3]

    def test_not_hashable(self) -> None:
        """FrozenMapping is not hashable."""
        fm = FrozenMapping({"a": 1})

        with _pytest.raises(TypeError, match="unhashable"):
            hash(fm)

    def test_immutable_no_setitem(self) -> None:
        """Cannot set items on FrozenMapping."""
        fm = FrozenMapping({"a": 1})

        with _pytest.raises(TypeError):
            fm["a"] = 2  # type: ignore[index]

    def test_immutable_no_delitem(self) -> None:
        """Cannot delete items from FrozenMapping."""
        fm = FrozenMapping({"a": 1})

        with _pytest.raises(TypeError):
            del fm["a"]  # type: ignore[attr-defined]

    def test_wraps_dict_directly(self) -> None:
        """Dict is used directly, not copied."""
        data = {"a": 1}
        fm = FrozenMapping(data)

        # Underlying data is same object
        assert fm._data is data

    def test_converts_non_dict_mapping(self) -> None:
        """Non-dict Mappings are converted to dict."""
        od = _collections.OrderedDict([("a", 1), ("b", 2)])
        fm = FrozenMapping(od)

        # Converted to plain dict
        assert isinstance(fm._data, dict)
        assert fm["a"] == 1


class TestFrozenSequence:
    """Tests for FrozenSequence read-only list wrapper."""

    def test_getitem_returns_value(self) -> None:
        """Can access values by index."""
        fs = FrozenSequence([1, 2, 3])

        assert fs[0] == 1
        assert fs[1] == 2
        assert fs[-1] == 3

    def test_getitem_out_of_bounds_raises(self) -> None:
        """Out of bounds index raises IndexError."""
        fs = FrozenSequence([1, 2])

        with _pytest.raises(IndexError):
            _ = fs[99]

    def test_len(self) -> None:
        """len() returns number of items."""
        fs = FrozenSequence([1, 2, 3, 4])

        assert len(fs) == 4

    def test_iter(self) -> None:
        """Iteration yields all items."""
        fs = FrozenSequence([1, 2, 3])

        assert list(fs) == [1, 2, 3]

    def test_contains(self) -> None:
        """'in' operator works."""
        fs = FrozenSequence([1, 2, 3])

        assert 2 in fs
        assert 99 not in fs

    def test_slice_returns_frozen_sequence(self) -> None:
        """Slicing returns a new FrozenSequence."""
        fs = FrozenSequence([1, 2, 3, 4, 5])

        sliced = fs[1:4]

        assert isinstance(sliced, FrozenSequence)
        assert list(sliced) == [2, 3, 4]

    def test_nested_dict_is_frozen(self) -> None:
        """Nested dicts are returned as FrozenMapping."""
        fs = FrozenSequence([{"a": 1}, {"b": 2}])

        item = fs[0]

        assert isinstance(item, FrozenMapping)
        assert item["a"] == 1

    def test_nested_list_is_frozen(self) -> None:
        """Nested lists are returned as FrozenSequence."""
        fs = FrozenSequence([[1, 2], [3, 4]])

        nested = fs[0]

        assert isinstance(nested, FrozenSequence)
        assert list(nested) == [1, 2]

    def test_scalar_values_unchanged(self) -> None:
        """Scalar values returned as-is."""
        fs = FrozenSequence([42, "hello", 3.14, True, None])

        assert fs[0] == 42
        assert fs[1] == "hello"
        assert fs[2] == 3.14
        assert fs[3] is True
        assert fs[4] is None

    def test_repr(self) -> None:
        """repr shows FrozenSequence with content."""
        fs = FrozenSequence([1, 2, 3])

        result = repr(fs)

        assert "FrozenSequence" in result
        assert "1" in result

    def test_eq_with_list(self) -> None:
        """FrozenSequence equals list with same content."""
        fs = FrozenSequence([1, 2, 3])

        assert fs == [1, 2, 3]
        assert fs == [1, 2, 3]

    def test_eq_with_frozen_sequence(self) -> None:
        """FrozenSequence equals another FrozenSequence with same content."""
        fs1 = FrozenSequence([1, 2])
        fs2 = FrozenSequence([1, 2])

        assert fs1 == fs2

    def test_eq_different_content(self) -> None:
        """FrozenSequence not equal to list with different content."""
        fs = FrozenSequence([1, 2, 3])

        assert fs != [1, 2]
        assert fs != [3, 2, 1]

    def test_eq_with_string_returns_not_implemented(self) -> None:
        """Comparison with string doesn't match (string is a Sequence)."""
        fs = FrozenSequence(["a", "b", "c"])

        # Should not equal the string "abc" even though both are sequences
        assert fs != "abc"

    def test_eq_with_non_sequence_returns_not_implemented(self) -> None:
        """Comparison with non-Sequence returns NotImplemented."""
        fs = FrozenSequence([1, 2, 3])

        # Comparing with non-Sequence types
        assert fs != 42
        assert fs != {"a": 1}

    def test_not_hashable(self) -> None:
        """FrozenSequence is not hashable."""
        fs = FrozenSequence([1, 2, 3])

        with _pytest.raises(TypeError, match="unhashable"):
            hash(fs)

    def test_immutable_no_setitem(self) -> None:
        """Cannot set items on FrozenSequence."""
        fs = FrozenSequence([1, 2, 3])

        with _pytest.raises(TypeError):
            fs[0] = 99  # type: ignore[index]

    def test_immutable_no_delitem(self) -> None:
        """Cannot delete items from FrozenSequence."""
        fs = FrozenSequence([1, 2, 3])

        with _pytest.raises(TypeError):
            del fs[0]  # type: ignore[attr-defined]

    def test_immutable_no_append(self) -> None:
        """Cannot append to FrozenSequence."""
        fs = FrozenSequence([1, 2, 3])

        with _pytest.raises(AttributeError):
            fs.append(4)  # type: ignore[attr-defined]

    def test_wraps_list_directly(self) -> None:
        """List is used directly, not copied."""
        data = [1, 2, 3]
        fs = FrozenSequence(data)

        assert fs._data is data

    def test_converts_non_list_sequence(self) -> None:
        """Non-list Sequences are converted to list."""
        fs = FrozenSequence((1, 2, 3))  # tuple

        assert isinstance(fs._data, list)
        assert fs[0] == 1


class TestFreeze:
    """Tests for the freeze() helper function."""

    def test_freeze_dict_returns_frozen_mapping(self) -> None:
        """freeze(dict) returns FrozenMapping."""
        result = freeze({"a": 1})

        assert isinstance(result, FrozenMapping)
        assert result["a"] == 1

    def test_freeze_list_returns_frozen_sequence(self) -> None:
        """freeze(list) returns FrozenSequence."""
        result = freeze([1, 2, 3])

        assert isinstance(result, FrozenSequence)
        assert list(result) == [1, 2, 3]

    def test_freeze_scalar_returns_unchanged(self) -> None:
        """freeze(scalar) returns the value unchanged."""
        assert freeze(42) == 42
        assert freeze("hello") == "hello"
        assert freeze(3.14) == 3.14
        assert freeze(True) is True
        assert freeze(None) is None

    def test_freeze_already_frozen_mapping(self) -> None:
        """freeze(FrozenMapping) wraps it again (consistent behavior)."""
        fm = FrozenMapping({"a": 1})
        result = freeze(fm)

        # FrozenMapping is a Mapping, not a dict, so it gets wrapped
        # This is intentional for simplicity
        assert isinstance(result, FrozenMapping)

    def test_freeze_deeply_nested(self) -> None:
        """freeze() on nested structure creates fully frozen view."""
        data: dict[str, _typing.Any] = {"level1": {"level2": {"items": [1, 2, {"deep": "value"}]}}}

        frozen = freeze(data)

        assert isinstance(frozen, FrozenMapping)
        level1 = frozen["level1"]
        assert isinstance(level1, FrozenMapping)
        level2 = level1["level2"]
        assert isinstance(level2, FrozenMapping)
        items = level2["items"]
        assert isinstance(items, FrozenSequence)
        deep_dict = items[2]
        assert isinstance(deep_dict, FrozenMapping)
        assert deep_dict["deep"] == "value"
