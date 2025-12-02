"""
Builtin skills that ship with brynhild.

These skills are discovered automatically and available in all projects.
They have the lowest priority - project-local and global user skills
override them.
"""

import pathlib as _pathlib


def get_builtin_skills_path() -> _pathlib.Path:
    """Get the path to builtin skills directory."""
    return _pathlib.Path(__file__).parent

