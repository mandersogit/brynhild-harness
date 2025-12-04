"""
Brynhild - AI Coding Assistant

A modular AI coding assistant for the terminal.
Named after the Norse valkyrie and shieldmaiden.
"""

import importlib.metadata as _metadata

# Version is defined in pyproject.toml - read it and parse into tuple (primary representation)
_raw_version = _metadata.version("brynhild")
__version_info__: tuple[int, int, int] = tuple(int(x) for x in _raw_version.split(".")[:3])  # type: ignore[assignment]
__version__: str = ".".join(str(x) for x in __version_info__)
__author__ = "Brynhild Contributors"

from brynhild.config import Settings  # noqa: E402
from brynhild.session import Session, SessionManager  # noqa: E402

__all__ = ["__version__", "__version_info__", "Settings", "Session", "SessionManager"]
