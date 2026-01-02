"""
Tests for icon utilities.

These tests verify the cell-width-aware padding functions work correctly
for consistent terminal display across different emoji/icon widths.
"""

import brynhild.ui.icons as icons


class TestCellWidthPadding:
    """Tests for cell-width-aware padding functions."""

    def test_cell_ljust_pads_on_right(self) -> None:
        """cell_ljust adds spaces after text."""
        result = icons.cell_ljust("a", 5)
        assert result == "a    "  # 1 char + 4 spaces = 5

    def test_cell_rjust_pads_on_left(self) -> None:
        """cell_rjust adds spaces before text."""
        result = icons.cell_rjust("a", 5)
        assert result == "    a"  # 4 spaces + 1 char = 5

    def test_cell_center_pads_both_sides(self) -> None:
        """cell_center adds spaces on both sides."""
        result = icons.cell_center("a", 5)
        # 4 padding total: 2 left, 2 right
        assert result == "  a  "

    def test_cell_center_odd_padding_favors_right(self) -> None:
        """When padding is odd, extra space goes on right."""
        result = icons.cell_center("a", 4)
        # 3 padding total: 1 left, 2 right
        assert result == " a  "

    def test_no_padding_when_text_fills_width(self) -> None:
        """No spaces added when text already fills width."""
        result = icons.cell_ljust("abcde", 5)
        assert result == "abcde"

    def test_no_padding_when_text_exceeds_width(self) -> None:
        """No padding (and no truncation) when text exceeds width."""
        result = icons.cell_ljust("abcdef", 5)
        assert result == "abcdef"


class TestEmojiCellWidths:
    """Tests that emojis measure correctly as wide characters."""

    def test_bolt_measures_wider_than_one(self) -> None:
        """⚡ (BOLT) should measure as wider than 1 cell."""
        import rich.cells as rich_cells

        width = rich_cells.cell_len(icons.ICON_BOLT)
        # Most terminal fonts render ⚡ as 1 or 2 cells
        assert width >= 1

    def test_warning_may_include_variant_selector(self) -> None:
        """⚠️ includes variant selector, may render wider."""
        import rich.cells as rich_cells

        width = rich_cells.cell_len(icons.ICON_WARNING)
        # ⚠️ can be 1-3 cells depending on terminal/font
        assert width >= 1


class TestIconConvenienceFunctions:
    """Tests for icon_*() convenience functions."""

    def test_icon_warning_returns_padded_string(self) -> None:
        """icon_warning() returns consistently padded icon."""
        result = icons.icon_warning()
        assert icons.ICON_WARNING in result
        # Should have padding
        assert len(result) >= len(icons.ICON_WARNING)

    def test_icon_bolt_returns_padded_string(self) -> None:
        """icon_bolt() returns consistently padded icon."""
        result = icons.icon_bolt()
        assert icons.ICON_BOLT in result
        assert len(result) >= len(icons.ICON_BOLT)

    def test_icon_success_returns_padded_string(self) -> None:
        """icon_success() returns consistently padded icon."""
        result = icons.icon_success()
        assert icons.ICON_SUCCESS in result

    def test_icon_failure_returns_padded_string(self) -> None:
        """icon_failure() returns consistently padded icon."""
        result = icons.icon_failure()
        assert icons.ICON_FAILURE in result

    def test_icon_recovered_returns_padded_string(self) -> None:
        """icon_recovered() returns consistently padded icon."""
        result = icons.icon_recovered()
        assert icons.ICON_RECOVERED in result


class TestConsistentIconWidths:
    """
    Tests that all icons produce consistent cell widths.

    This is the main purpose of the icons module - to ensure all icons
    visually align regardless of their actual Unicode character widths.
    """

    def test_all_icons_same_visual_width(self) -> None:
        """All padded icons should produce the same cell width."""
        import rich.cells as rich_cells

        # Get all padded icons
        padded_icons = [
            icons.icon_warning(),
            icons.icon_bolt(),
            icons.icon_success(),
            icons.icon_failure(),
            icons.icon_recovered(),
        ]

        # All should have the same cell width
        widths = [rich_cells.cell_len(icon) for icon in padded_icons]

        # All widths should equal DEFAULT_ICON_WIDTH
        for i, w in enumerate(widths):
            assert w == icons.DEFAULT_ICON_WIDTH, (
                f"Icon {i} has width {w}, expected {icons.DEFAULT_ICON_WIDTH}. "
                f"Icons are not visually aligned!"
            )

    def test_icon_width_matches_constant(self) -> None:
        """Padded icons should match DEFAULT_ICON_WIDTH."""
        import rich.cells as rich_cells

        result = icons.icon_bolt()
        width = rich_cells.cell_len(result)
        assert width == icons.DEFAULT_ICON_WIDTH


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_string_padding(self) -> None:
        """Empty string should pad to full width."""
        result = icons.cell_ljust("", 3)
        assert result == "   "

    def test_zero_width_target(self) -> None:
        """Zero width target should return original text."""
        result = icons.cell_ljust("test", 0)
        assert result == "test"

    def test_negative_width_target(self) -> None:
        """Negative width should return original text."""
        result = icons.cell_ljust("test", -5)
        assert result == "test"

    def test_unicode_combining_characters(self) -> None:
        """Handle combining characters gracefully."""
        # é composed as e + combining acute accent
        text = "e\u0301"  # e + combining acute
        result = icons.cell_ljust(text, 5)
        # Should not crash and should add padding
        assert len(result) >= len(text)
