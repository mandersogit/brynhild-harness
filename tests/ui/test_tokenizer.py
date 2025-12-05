"""
Tests for the tokenizer module (client-side token counting).

These tests verify:
1. Encoder selection works correctly for different models
2. Token counting produces reasonable values
3. TurnTokenCounter tracks per-turn tokens correctly
"""


import brynhild.ui.tokenizer as tokenizer


class TestEncoderSelection:
    """Tests for get_encoder() function."""

    def test_gpt_oss_120b_uses_o200k_harmony(self) -> None:
        """gpt-oss-120b should use o200k_harmony encoding."""
        encoder = tokenizer.get_encoder("gpt-oss-120b")
        assert encoder.name == "o200k_harmony"

    def test_gpt_oss_20b_uses_o200k_harmony(self) -> None:
        """gpt-oss-20b should use o200k_harmony encoding."""
        encoder = tokenizer.get_encoder("gpt-oss-20b")
        assert encoder.name == "o200k_harmony"

    def test_gpt_4_uses_cl100k_base(self) -> None:
        """gpt-4 should use cl100k_base encoding."""
        encoder = tokenizer.get_encoder("gpt-4")
        assert encoder.name == "cl100k_base"

    def test_gpt_4_turbo_uses_cl100k_base(self) -> None:
        """gpt-4-turbo variants should use cl100k_base."""
        encoder = tokenizer.get_encoder("gpt-4-turbo-preview")
        assert encoder.name == "cl100k_base"

    def test_unknown_model_falls_back_to_cl100k(self) -> None:
        """Unknown models should fall back to cl100k_base."""
        encoder = tokenizer.get_encoder("claude-3-sonnet")
        assert encoder.name == "cl100k_base"

    def test_totally_unknown_model_falls_back_to_cl100k(self) -> None:
        """Completely unknown models should fall back to cl100k_base."""
        encoder = tokenizer.get_encoder("some-random-model-xyz")
        assert encoder.name == "cl100k_base"


class TestTokenCounting:
    """Tests for count_tokens() function."""

    def test_counts_simple_text(self) -> None:
        """Should count tokens in simple text."""
        encoder = tokenizer.get_encoder("gpt-4")
        count = tokenizer.count_tokens(encoder, "Hello, world!")
        # "Hello, world!" is typically 4-5 tokens
        assert 3 <= count <= 6

    def test_empty_string_returns_zero(self) -> None:
        """Empty string should return 0 tokens."""
        encoder = tokenizer.get_encoder("gpt-4")
        count = tokenizer.count_tokens(encoder, "")
        assert count == 0

    def test_counts_code_text(self) -> None:
        """Should count tokens in code text."""
        encoder = tokenizer.get_encoder("gpt-4")
        code = "def hello():\n    print('world')"
        count = tokenizer.count_tokens(encoder, code)
        # Code typically has more tokens per character
        assert count > 0
        assert count <= len(code)  # Shouldn't exceed character count

    def test_gpt_oss_tokenizer_works(self) -> None:
        """gpt-oss tokenizer should count tokens correctly."""
        encoder = tokenizer.get_encoder("gpt-oss-120b")
        count = tokenizer.count_tokens(encoder, "Hello, world!")
        assert 3 <= count <= 6


class TestTurnTokenCounter:
    """Tests for TurnTokenCounter class."""

    def test_initial_count_is_zero(self) -> None:
        """Counter should start at zero."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        assert counter.count == 0

    def test_add_text_increments_count(self) -> None:
        """Adding text should increment the count."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        counter.add_text("Hello")
        assert counter.count > 0

    def test_add_text_returns_new_total(self) -> None:
        """add_text() should return the new total count."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        total1 = counter.add_text("Hello")
        total2 = counter.add_text(" world")
        assert total1 > 0
        assert total2 > total1
        assert total2 == counter.count

    def test_reset_clears_count(self) -> None:
        """reset() should clear the count to zero."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        counter.add_text("Hello world")
        assert counter.count > 0
        counter.reset()
        assert counter.count == 0

    def test_multiple_adds_accumulate(self) -> None:
        """Multiple add_text calls should accumulate."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        counter.add_text("Hello")
        count1 = counter.count
        counter.add_text(" world")
        count2 = counter.count
        counter.add_text("!")
        count3 = counter.count
        assert count1 < count2 < count3

    def test_encoder_name_exposed(self) -> None:
        """encoder_name property should expose the encoder name."""
        counter = tokenizer.TurnTokenCounter("gpt-oss-120b")
        assert counter.encoder_name == "o200k_harmony"

    def test_encoder_name_fallback_for_unknown_model(self) -> None:
        """Unknown models should show fallback encoder name."""
        counter = tokenizer.TurnTokenCounter("unknown-model-xyz")
        assert counter.encoder_name == "cl100k_base"


class TestTokenCountingAccuracy:
    """Tests to verify token counting produces reasonable values."""

    def test_short_text_reasonable_count(self) -> None:
        """Short text should have reasonable token count."""
        counter = tokenizer.TurnTokenCounter("gpt-4")
        # "Hello, how are you?" - typically 5-7 tokens
        total = counter.add_text("Hello, how are you?")
        assert 4 <= total <= 8

    def test_long_text_accumulates_correctly(self) -> None:
        """Long text added in chunks should accumulate to a reasonable total.

        Note: Chunked counting may differ slightly from single-pass counting
        because tokenization can depend on context (e.g., word boundaries).
        This is expected and acceptable for streaming UI feedback.
        """
        counter = tokenizer.TurnTokenCounter("gpt-4")

        # Add text in chunks
        text = "The quick brown fox jumps over the lazy dog. " * 10
        chunk_size = 50
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            counter.add_text(chunk)

        final_count = counter.count

        # Verify against single-pass counting
        encoder = tokenizer.get_encoder("gpt-4")
        single_pass = tokenizer.count_tokens(encoder, text)

        # Chunked counting may be slightly higher due to word boundary effects
        # but should be within ~10% for reasonable chunk sizes
        assert abs(final_count - single_pass) <= single_pass * 0.15, (
            f"Chunked count {final_count} differs too much from single-pass {single_pass}"
        )

    def test_streaming_simulation(self) -> None:
        """Simulate streaming by adding small chunks."""
        counter = tokenizer.TurnTokenCounter("gpt-oss-120b")

        # Simulate streaming word by word
        words = ["This", "is", "a", "test", "of", "streaming", "token", "counting"]
        for word in words:
            counter.add_text(word + " ")

        # Should have counted all words
        assert counter.count > 0
        # Roughly 1-2 tokens per word
        assert counter.count <= len(words) * 3

    def test_gpt_oss_vs_cl100k_similar_for_regular_text(self) -> None:
        """o200k_harmony and cl100k_base should be similar for regular text."""
        text = "Hello, how are you doing today? I hope you're having a great day!"

        oss_counter = tokenizer.TurnTokenCounter("gpt-oss-120b")
        gpt4_counter = tokenizer.TurnTokenCounter("gpt-4")

        oss_count = oss_counter.add_text(text)
        gpt4_count = gpt4_counter.add_text(text)

        # Counts should be in the same ballpark (within 50%)
        ratio = max(oss_count, gpt4_count) / min(oss_count, gpt4_count)
        assert ratio < 1.5, f"Token counts differ too much: {oss_count} vs {gpt4_count}"

