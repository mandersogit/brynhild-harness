"""
Default profile - minimal configuration for unknown models.
"""

import brynhild.profiles.types as types

DEFAULT_PROFILE = types.ModelProfile(
    name="default",
    family="",
    description="Default profile for unknown models - minimal configuration",
    default_temperature=0.7,
    default_max_tokens=8192,
    supports_tools=True,
    supports_reasoning=False,
    supports_streaming=True,
    # No special prompt patterns for default
    prompt_patterns={},
    enabled_patterns=[],
    # Conservative tool settings
    tool_parallelization=True,
    max_tools_per_turn=10,
    # Balanced behavior
    eagerness="medium",
    verbosity="medium",
    thoroughness="balanced",
    # Enable stuck detection
    stuck_detection_enabled=True,
    max_similar_tool_calls=3,
)

