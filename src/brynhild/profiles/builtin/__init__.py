"""
Builtin model profiles.

These profiles are bundled with Brynhild and provide optimized settings
for common models.
"""

from __future__ import annotations

import brynhild.profiles.types as types

# Import profile definitions
from brynhild.profiles.builtin.default import DEFAULT_PROFILE
from brynhild.profiles.builtin.gpt_oss import GPT_OSS_120B, GPT_OSS_120B_FAST


def get_all_profiles() -> list[types.ModelProfile]:
    """Get all builtin profiles."""
    return [
        DEFAULT_PROFILE,
        GPT_OSS_120B,
        GPT_OSS_120B_FAST,
    ]


__all__ = [
    "get_all_profiles",
    "DEFAULT_PROFILE",
    "GPT_OSS_120B",
    "GPT_OSS_120B_FAST",
]

