"""Tests for model identity types.

Phase 4 types:
- ModelDescriptor: structured model attributes
- ProviderBinding: provider-specific bindings
- ModelIdentity: complete identity with bindings and descriptor
"""


import pydantic as _pydantic
import pytest as _pytest

import brynhild.config.types as types

# =============================================================================
# ModelDescriptor Tests
# =============================================================================


class TestModelDescriptor:
    """Tests for ModelDescriptor type."""

    def test_minimal_descriptor_requires_family(self) -> None:
        """family is the only required field."""
        desc = types.ModelDescriptor(family="llama")

        assert desc.family == "llama"
        assert desc.series is None
        assert desc.size is None
        assert desc.active_size is None
        assert desc.architecture is None
        assert desc.context_size is None
        assert desc.variant is None
        assert desc.extra == {}

    def test_full_dense_model_descriptor(self) -> None:
        """Dense model with all fields populated."""
        desc = types.ModelDescriptor(
            family="llama",
            series="3.3",
            size="70b",
            active_size=None,
            architecture="dense",
            context_size=131072,
            variant="instruct",
            extra={"tool_use": True},
        )

        assert desc.family == "llama"
        assert desc.series == "3.3"
        assert desc.size == "70b"
        assert desc.active_size is None
        assert desc.architecture == "dense"
        assert desc.context_size == 131072
        assert desc.variant == "instruct"
        assert desc.extra == {"tool_use": True}

    def test_moe_model_descriptor(self) -> None:
        """MoE model with active_size for sparse activation."""
        desc = types.ModelDescriptor(
            family="qwen",
            series="3",
            size="235b",
            active_size="22b",
            architecture="moe",
            context_size=131072,
        )

        assert desc.size == "235b"
        assert desc.active_size == "22b"
        assert desc.architecture == "moe"

    def test_effective_size_returns_size_for_dense(self) -> None:
        """effective_size returns size for dense models."""
        desc = types.ModelDescriptor(
            family="llama",
            size="70b",
            architecture="dense",
        )

        assert desc.effective_size == "70b"

    def test_effective_size_returns_active_size_for_moe(self) -> None:
        """effective_size returns active_size for MoE models."""
        desc = types.ModelDescriptor(
            family="qwen",
            size="235b",
            active_size="22b",
            architecture="moe",
        )

        assert desc.effective_size == "22b"

    def test_effective_size_returns_size_when_moe_without_active(self) -> None:
        """effective_size falls back to size if MoE has no active_size."""
        desc = types.ModelDescriptor(
            family="unknown",
            size="100b",
            architecture="moe",
            # active_size not set
        )

        assert desc.effective_size == "100b"

    def test_effective_size_returns_size_when_architecture_unknown(self) -> None:
        """effective_size returns size when architecture is None."""
        desc = types.ModelDescriptor(
            family="claude",
            size="unknown",
        )

        assert desc.effective_size == "unknown"

    def test_effective_size_returns_none_when_no_sizes(self) -> None:
        """effective_size returns None if no size fields set."""
        desc = types.ModelDescriptor(family="minimal")

        assert desc.effective_size is None

    def test_descriptor_is_immutable(self) -> None:
        """ModelDescriptor is frozen (immutable)."""
        desc = types.ModelDescriptor(family="llama", size="70b")

        with _pytest.raises(_pydantic.ValidationError):
            desc.family = "changed"  # type: ignore[misc]

    def test_architecture_validates_literal(self) -> None:
        """architecture only accepts 'dense', 'moe', or None."""
        with _pytest.raises(_pydantic.ValidationError):
            types.ModelDescriptor(family="test", architecture="transformer")  # type: ignore[arg-type]

    def test_missing_family_raises_validation_error(self) -> None:
        """ModelDescriptor requires family field."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ModelDescriptor()  # type: ignore[call-arg]

        # Verify the error mentions family
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("family",) for e in errors)

    def test_deepseek_v3_moe_example(self) -> None:
        """Real-world example: DeepSeek V3 (671b total, ~37b active)."""
        desc = types.ModelDescriptor(
            family="deepseek",
            series="v3",
            size="671b",
            active_size="37b",
            architecture="moe",
            context_size=131072,
            variant="chat",
        )

        # For performance estimation, effective_size is the active params
        assert desc.effective_size == "37b"


# =============================================================================
# ProviderBinding Tests
# =============================================================================


class TestProviderBinding:
    """Tests for ProviderBinding type."""

    def test_minimal_binding_requires_model_id(self) -> None:
        """model_id is the only required field."""
        binding = types.ProviderBinding(model_id="meta-llama/llama-3.1-8b-instruct")

        assert binding.model_id == "meta-llama/llama-3.1-8b-instruct"
        assert binding.max_context is None
        assert binding.pricing_tiers is None
        assert binding.alternatives == []
        assert binding.extra == {}

    def test_full_binding_with_all_fields(self) -> None:
        """ProviderBinding with all optional fields."""
        binding = types.ProviderBinding(
            model_id="llama3.1:8b-instruct-q4_K_M",
            max_context=65536,
            pricing_tiers={"per_1k": {"input": 0.001, "output": 0.002}},
            alternatives=["llama3.1:8b-instruct-q8_0", "llama3.1:8b-instruct-fp16"],
            extra={"quant": "q4_K_M"},
        )

        assert binding.model_id == "llama3.1:8b-instruct-q4_K_M"
        assert binding.max_context == 65536
        assert binding.pricing_tiers == {"per_1k": {"input": 0.001, "output": 0.002}}
        assert binding.alternatives == ["llama3.1:8b-instruct-q8_0", "llama3.1:8b-instruct-fp16"]
        assert binding.extra == {"quant": "q4_K_M"}

    def test_binding_is_immutable(self) -> None:
        """ProviderBinding is frozen (immutable)."""
        binding = types.ProviderBinding(model_id="test-model")

        with _pytest.raises(_pydantic.ValidationError):
            binding.model_id = "changed"  # type: ignore[misc]

    def test_openrouter_binding(self) -> None:
        """OpenRouter-style binding."""
        binding = types.ProviderBinding(
            model_id="anthropic/claude-sonnet-4",
            max_context=200000,
        )

        assert binding.model_id == "anthropic/claude-sonnet-4"
        assert binding.max_context == 200000

    def test_ollama_binding_with_quant(self) -> None:
        """Ollama-style binding with quantization in model_id."""
        binding = types.ProviderBinding(
            model_id="llama3.1:70b-instruct-q4_K_M",
            max_context=131072,
            alternatives=["llama3.1:70b-instruct-q8_0"],
        )

        assert "q4_K_M" in binding.model_id
        assert len(binding.alternatives) == 1

    def test_missing_model_id_raises_validation_error(self) -> None:
        """ProviderBinding requires model_id field."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ProviderBinding()  # type: ignore[call-arg]

        # Verify the error mentions model_id
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("model_id",) for e in errors)


# =============================================================================
# ModelIdentity Tests
# =============================================================================


class TestModelIdentity:
    """Tests for ModelIdentity type."""

    def test_minimal_identity_requires_canonical_id(self) -> None:
        """canonical_id is the only required field."""
        identity = types.ModelIdentity(canonical_id="meta-llama/llama-3.1-8b-instruct")

        assert identity.canonical_id == "meta-llama/llama-3.1-8b-instruct"
        assert identity.bindings == {}
        assert identity.descriptor is None
        assert identity.aliases == {}
        assert identity.confidence == "curated"
        assert identity.notes is None

    def test_full_identity_with_all_fields(self) -> None:
        """ModelIdentity with all fields populated."""
        descriptor = types.ModelDescriptor(
            family="llama",
            series="3.1",
            size="8b",
            architecture="dense",
            context_size=131072,
            variant="instruct",
        )

        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={
                "openrouter": "meta-llama/llama-3.1-8b-instruct",
                "ollama": types.ProviderBinding(
                    model_id="llama3.1:8b-instruct-q4_K_M",
                    max_context=65536,
                ),
            },
            descriptor=descriptor,
            aliases={
                "llama3.1:8b": True,
                "llama-3.1-8b": True,
                "old-name": False,  # Disabled alias
            },
            confidence="curated",
            notes="Popular instruct model with good tool use",
        )

        assert identity.canonical_id == "meta-llama/llama-3.1-8b-instruct"
        assert len(identity.bindings) == 2
        assert identity.descriptor is not None
        assert identity.descriptor.family == "llama"
        assert identity.aliases["llama3.1:8b"] is True
        assert identity.aliases["old-name"] is False
        assert identity.confidence == "curated"
        assert "tool use" in identity.notes  # type: ignore[operator]

    def test_identity_is_immutable(self) -> None:
        """ModelIdentity is frozen (immutable)."""
        identity = types.ModelIdentity(canonical_id="test/model")

        with _pytest.raises(_pydantic.ValidationError):
            identity.canonical_id = "changed"  # type: ignore[misc]

    def test_confidence_validates_literal(self) -> None:
        """confidence only accepts valid values."""
        with _pytest.raises(_pydantic.ValidationError):
            types.ModelIdentity(canonical_id="test/model", confidence="unknown")  # type: ignore[arg-type]

    def test_missing_canonical_id_raises_validation_error(self) -> None:
        """ModelIdentity requires canonical_id field."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ModelIdentity()  # type: ignore[call-arg]

        # Verify the error mentions canonical_id
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("canonical_id",) for e in errors)


class TestModelIdentityGetBinding:
    """Tests for ModelIdentity.get_binding() method."""

    def test_get_binding_returns_none_for_missing_provider(self) -> None:
        """get_binding returns None for unknown provider."""
        identity = types.ModelIdentity(
            canonical_id="test/model",
            bindings={"openrouter": "test/model"},
        )

        assert identity.get_binding("ollama") is None

    def test_get_binding_normalizes_string_to_provider_binding(self) -> None:
        """String binding is normalized to ProviderBinding."""
        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={"openrouter": "meta-llama/llama-3.1-8b-instruct"},
        )

        binding = identity.get_binding("openrouter")

        assert binding is not None
        assert isinstance(binding, types.ProviderBinding)
        assert binding.model_id == "meta-llama/llama-3.1-8b-instruct"
        assert binding.max_context is None

    def test_get_binding_returns_provider_binding_directly(self) -> None:
        """ProviderBinding objects are returned as-is."""
        rich_binding = types.ProviderBinding(
            model_id="llama3.1:8b-instruct-q4_K_M",
            max_context=65536,
        )

        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={"ollama": rich_binding},
        )

        binding = identity.get_binding("ollama")

        assert binding is not None
        assert binding.model_id == "llama3.1:8b-instruct-q4_K_M"
        assert binding.max_context == 65536


class TestModelIdentityGetNativeId:
    """Tests for ModelIdentity.get_native_id() method."""

    def test_get_native_id_returns_none_for_missing_provider(self) -> None:
        """get_native_id returns None for unknown provider."""
        identity = types.ModelIdentity(canonical_id="test/model")

        assert identity.get_native_id("ollama") is None

    def test_get_native_id_extracts_from_string_binding(self) -> None:
        """get_native_id extracts model_id from string binding."""
        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={"openrouter": "meta-llama/llama-3.1-8b-instruct"},
        )

        native_id = identity.get_native_id("openrouter")

        assert native_id == "meta-llama/llama-3.1-8b-instruct"

    def test_get_native_id_extracts_from_provider_binding(self) -> None:
        """get_native_id extracts model_id from ProviderBinding."""
        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={
                "ollama": types.ProviderBinding(model_id="llama3.1:8b-instruct-q4_K_M"),
            },
        )

        native_id = identity.get_native_id("ollama")

        assert native_id == "llama3.1:8b-instruct-q4_K_M"


class TestModelIdentityEffectiveContext:
    """Tests for ModelIdentity.effective_context() method."""

    def test_effective_context_returns_none_for_missing_provider(self) -> None:
        """effective_context returns None for unknown provider."""
        identity = types.ModelIdentity(canonical_id="test/model")

        assert identity.effective_context("unknown") is None

    def test_effective_context_returns_provider_max_context(self) -> None:
        """effective_context returns provider's max_context if set."""
        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={
                "ollama": types.ProviderBinding(
                    model_id="llama3.1:8b",
                    max_context=65536,  # Provider limits to 64K
                ),
            },
            descriptor=types.ModelDescriptor(
                family="llama",
                context_size=131072,  # Model supports 128K
            ),
        )

        # Provider limit (65536) takes precedence
        context = identity.effective_context("ollama")

        assert context == 65536

    def test_effective_context_falls_back_to_descriptor(self) -> None:
        """effective_context falls back to descriptor.context_size."""
        identity = types.ModelIdentity(
            canonical_id="meta-llama/llama-3.1-8b-instruct",
            bindings={
                "openrouter": "meta-llama/llama-3.1-8b-instruct",  # String, no max_context
            },
            descriptor=types.ModelDescriptor(
                family="llama",
                context_size=131072,
            ),
        )

        context = identity.effective_context("openrouter")

        assert context == 131072

    def test_effective_context_returns_none_when_no_context_info(self) -> None:
        """effective_context returns None if no context info available."""
        identity = types.ModelIdentity(
            canonical_id="test/model",
            bindings={"openrouter": "test/model"},  # String binding, no max_context
            # No descriptor
        )

        assert identity.effective_context("openrouter") is None


# =============================================================================
# YAML Parsing Tests (simulated via dict)
# =============================================================================


class TestYAMLParsing:
    """Tests that model identity types parse correctly from dict (like YAML)."""

    def test_parse_simple_binding_from_dict(self) -> None:
        """Simple string binding parses correctly."""
        data = {
            "canonical_id": "meta-llama/llama-3.1-8b-instruct",
            "bindings": {
                "openrouter": "meta-llama/llama-3.1-8b-instruct",
            },
        }

        identity = types.ModelIdentity(**data)

        assert identity.canonical_id == "meta-llama/llama-3.1-8b-instruct"
        assert identity.bindings["openrouter"] == "meta-llama/llama-3.1-8b-instruct"

    def test_parse_rich_binding_from_dict(self) -> None:
        """Rich ProviderBinding parses from nested dict."""
        data = {
            "canonical_id": "meta-llama/llama-3.1-8b-instruct",
            "bindings": {
                "ollama": {
                    "model_id": "llama3.1:8b-instruct-q4_K_M",
                    "max_context": 65536,
                    "alternatives": ["llama3.1:8b-instruct-q8_0"],
                },
            },
        }

        identity = types.ModelIdentity(**data)

        binding = identity.bindings["ollama"]
        assert isinstance(binding, types.ProviderBinding)
        assert binding.model_id == "llama3.1:8b-instruct-q4_K_M"
        assert binding.max_context == 65536
        assert binding.alternatives == ["llama3.1:8b-instruct-q8_0"]

    def test_parse_descriptor_from_dict(self) -> None:
        """ModelDescriptor parses from nested dict."""
        data = {
            "canonical_id": "qwen/qwen3-235b-a22b",
            "descriptor": {
                "family": "qwen",
                "series": "3",
                "size": "235b",
                "active_size": "22b",
                "architecture": "moe",
                "context_size": 131072,
            },
        }

        identity = types.ModelIdentity(**data)

        assert identity.descriptor is not None
        assert identity.descriptor.family == "qwen"
        assert identity.descriptor.size == "235b"
        assert identity.descriptor.active_size == "22b"
        assert identity.descriptor.architecture == "moe"
        assert identity.descriptor.effective_size == "22b"

    def test_parse_mixed_bindings_from_dict(self) -> None:
        """Mix of simple and rich bindings parse correctly."""
        data = {
            "canonical_id": "meta-llama/llama-3.1-70b-instruct",
            "bindings": {
                "openrouter": "meta-llama/llama-3.1-70b-instruct",  # Simple
                "ollama": {  # Rich
                    "model_id": "llama3.1:70b-instruct-q4_K_M",
                    "max_context": 32768,
                },
            },
        }

        identity = types.ModelIdentity(**data)

        # Simple binding stays as string
        assert identity.bindings["openrouter"] == "meta-llama/llama-3.1-70b-instruct"

        # Rich binding becomes ProviderBinding
        ollama_binding = identity.bindings["ollama"]
        assert isinstance(ollama_binding, types.ProviderBinding)
        assert ollama_binding.max_context == 32768

        # get_binding normalizes both
        or_binding = identity.get_binding("openrouter")
        assert or_binding is not None
        assert or_binding.model_id == "meta-llama/llama-3.1-70b-instruct"


class TestAliasResolution:
    """Tests for alias dict behavior."""

    def test_aliases_are_dict_not_list(self) -> None:
        """Aliases use dict for DCM mergeability."""
        identity = types.ModelIdentity(
            canonical_id="test/model",
            aliases={
                "alias1": True,
                "alias2": True,
                "disabled-alias": False,
            },
        )

        # Dict allows selective override via DCM
        assert identity.aliases["alias1"] is True
        assert identity.aliases["disabled-alias"] is False

    def test_enabled_aliases_can_be_filtered(self) -> None:
        """Can filter to only enabled aliases."""
        identity = types.ModelIdentity(
            canonical_id="test/model",
            aliases={
                "good": True,
                "also-good": True,
                "disabled": False,
            },
        )

        enabled = [name for name, enabled in identity.aliases.items() if enabled]

        assert set(enabled) == {"good", "also-good"}

