"""
Shared fixtures for DeepChainMap tests.
"""

import pytest as _pytest

import brynhild.utils.deep_chain_map as dcm


@_pytest.fixture
def simple_dcm() -> dcm.DeepChainMap:
    """Simple two-layer DCM for basic tests."""
    return dcm.DeepChainMap(
        {"a": 1, "b": {"c": 2}},  # layer 0 (higher priority)
        {"b": {"c": 9, "d": 3}, "e": 4},  # layer 1 (lower priority)
    )


@_pytest.fixture
def nested_dcm() -> dcm.DeepChainMap:
    """DCM with deeply nested structure for merge tests."""
    return dcm.DeepChainMap(
        {"root": {"level1": {"level2": {"override": "high"}}}},
        {"root": {"level1": {"level2": {"override": "low", "preserved": True}}}},
    )


@_pytest.fixture
def dcm_with_provenance() -> dcm.DeepChainMap:
    """DCM with provenance tracking enabled."""
    return dcm.DeepChainMap(
        {"a": {"x": 1}},
        {"a": {"y": 2}},
        track_provenance=True,
    )

