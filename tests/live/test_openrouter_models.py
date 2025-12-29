"""
Live tests that verify model registry entries exist on OpenRouter.

These tests hit the OpenRouter API (no cost - just the models endpoint)
to verify that our curated registry contains valid model IDs.

This catches:
- Typos in model IDs
- Deprecated/removed models
- Made-up model IDs that don't exist
"""

import os as _os
import typing as _typing

import httpx as _httpx
import pytest as _pytest

import brynhild.config.settings as settings_module
import brynhild.config.types as types

# Mark all tests in this module as live (requires network)
pytestmark = [_pytest.mark.live]

# OpenRouter API endpoint for listing models (free, no auth required for public list)
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@_pytest.fixture(scope="module")
def openrouter_models() -> set[str]:
    """
    Fetch all available model IDs from OpenRouter.

    This is cached at module scope since it's the same for all tests.
    """
    response = _httpx.get(OPENROUTER_MODELS_URL, timeout=30.0)
    response.raise_for_status()

    data = response.json()
    # OpenRouter returns {"data": [{"id": "model-id", ...}, ...]}
    return {model["id"] for model in data.get("data", [])}


@_pytest.fixture
def clean_env(monkeypatch: _pytest.MonkeyPatch) -> _typing.Generator[None, None, None]:
    """Clear all BRYNHILD env vars for isolated tests."""
    env_keys = [k for k in _os.environ if k.startswith("BRYNHILD")]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BRYNHILD_SKIP_MIGRATION_CHECK", "1")
    yield


class TestRegistryModelsExistOnOpenRouter:
    """Verify all models with OpenRouter bindings actually exist."""

    def test_all_openrouter_bindings_exist(
        self,
        clean_env: None,
        openrouter_models: set[str],
    ) -> None:
        """
        Every model in our registry with an OpenRouter binding must exist.

        This test will FAIL if we have:
        - Typos in model IDs
        - Made-up model IDs
        - Deprecated models that no longer exist
        """
        settings = settings_module.Settings(_env_file=None)

        missing_models: list[str] = []

        for canonical_id, identity in settings.models.registry.items():
            # Get the OpenRouter binding (could be string or ProviderBinding)
            openrouter_binding = identity.bindings.get("openrouter")

            if openrouter_binding is None:
                continue  # No OpenRouter binding, skip

            # Extract model_id from binding
            if isinstance(openrouter_binding, str):
                openrouter_id = openrouter_binding
            elif isinstance(openrouter_binding, types.ProviderBinding):
                openrouter_id = openrouter_binding.model_id
            else:
                continue

            # Check if this model exists on OpenRouter
            if openrouter_id not in openrouter_models:
                missing_models.append(
                    f"  {canonical_id} -> {openrouter_id}"
                )

        if missing_models:
            # Provide helpful error with all missing models
            _pytest.fail(
                "The following registry models do NOT exist on OpenRouter:\n"
                + "\n".join(missing_models)
                + f"\n\nAvailable models can be found at: {OPENROUTER_MODELS_URL}"
            )

    def test_default_model_exists(
        self,
        clean_env: None,
        openrouter_models: set[str],
    ) -> None:
        """
        The default model should exist on OpenRouter.

        If the default model doesn't exist, users will get errors on first use.
        """
        settings = settings_module.Settings(_env_file=None)
        default_model = settings.models.default

        # The default might be an alias or a canonical ID
        # Try to get its OpenRouter binding
        resolved = settings.resolve_model_alias(default_model)
        identity = settings.get_model_identity(resolved)

        if identity is None:
            # Default model not in registry - check if it's a valid OpenRouter ID directly
            if default_model not in openrouter_models:
                _pytest.fail(
                    f"Default model '{default_model}' does not exist on OpenRouter "
                    f"and is not in the registry"
                )
            return

        # Get OpenRouter binding
        openrouter_binding = identity.bindings.get("openrouter")
        if openrouter_binding is None:
            _pytest.skip(f"Default model '{default_model}' has no OpenRouter binding")

        if isinstance(openrouter_binding, str):
            openrouter_id = openrouter_binding
        else:
            openrouter_id = openrouter_binding.model_id

        if openrouter_id not in openrouter_models:
            _pytest.fail(
                f"Default model '{default_model}' has OpenRouter binding '{openrouter_id}' "
                f"which does NOT exist on OpenRouter"
            )


