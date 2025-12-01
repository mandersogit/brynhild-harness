"""
Configuration module for Brynhild.

Uses pydantic-settings for environment variable loading.
"""

from brynhild.config.settings import (
    ProjectRootTooWideError,
    Settings,
    find_git_root,
    find_project_root,
)

__all__ = ["ProjectRootTooWideError", "Settings", "find_git_root", "find_project_root"]
