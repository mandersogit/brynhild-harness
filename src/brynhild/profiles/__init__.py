"""
Model profiles for Brynhild.

Provides model-specific configurations that optimize prompting, tool use,
and behavioral settings for different LLMs.
"""

from brynhild.profiles.manager import ProfileManager
from brynhild.profiles.types import ModelProfile

__all__ = [
    "ModelProfile",
    "ProfileManager",
]

