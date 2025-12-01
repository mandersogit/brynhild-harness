"""
Brynhild - AI Coding Assistant

A modular AI coding assistant for the terminal.
Named after the Norse valkyrie and shieldmaiden.
"""

__version__ = "0.1.0"
__author__ = "Brynhild Contributors"

from brynhild.config import Settings
from brynhild.session import Session, SessionManager

__all__ = ["__version__", "Settings", "Session", "SessionManager"]
