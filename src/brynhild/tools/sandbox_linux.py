"""
Linux sandbox implementation using bubblewrap.

Provides OS-level process isolation on Linux systems using bubblewrap (bwrap).
This is the primary sandbox mechanism for Linux, as Landlock requires kernel 5.13+
and RHEL8/Rocky8 use kernel 4.18.
"""

from __future__ import annotations

import pathlib as _pathlib
import shlex as _shlex
import shutil as _shutil
import subprocess as _subprocess


class BubblewrapNotFoundError(Exception):
    """Raised when bubblewrap is required but not installed."""

    pass


class BubblewrapNotFunctionalError(Exception):
    """Raised when bubblewrap is installed but cannot create sandboxes."""

    pass


# Cache the result of the functionality test
_bwrap_functional: bool | None = None


def is_bwrap_available() -> bool:
    """Check if bubblewrap is installed and in PATH."""
    return _shutil.which("bwrap") is not None


def is_bwrap_functional() -> bool:
    """Check if bubblewrap can actually create sandboxes.

    On some systems (e.g., Ubuntu 24.04 with AppArmor restrictions),
    bwrap may be installed but unable to create user namespaces.

    Returns:
        True if bwrap can create sandboxes, False otherwise.
    """
    global _bwrap_functional

    if _bwrap_functional is not None:
        return _bwrap_functional

    if not is_bwrap_available():
        _bwrap_functional = False
        return False

    # Try a minimal bwrap invocation
    try:
        result = _subprocess.run(
            [
                "bwrap",
                "--ro-bind", "/", "/",
                "--dev", "/dev",
                "--proc", "/proc",
                "/bin/true",
            ],
            capture_output=True,
            timeout=5,
        )
        _bwrap_functional = result.returncode == 0
    except (OSError, _subprocess.TimeoutExpired):
        _bwrap_functional = False

    return _bwrap_functional


def require_bwrap() -> None:
    """Raise if bubblewrap is not available or not functional.

    Call this at startup to fail fast if sandbox protection is unavailable.

    Raises:
        BubblewrapNotFoundError: If bwrap is not in PATH.
        BubblewrapNotFunctionalError: If bwrap cannot create sandboxes.
    """
    if not is_bwrap_available():
        raise BubblewrapNotFoundError(
            "bubblewrap (bwrap) is required for sandbox protection on Linux.\n"
            "\n"
            "The 'bwrap' command was not found in PATH.\n"
            "\n"
            "If bubblewrap is installed but not in PATH, ensure the directory\n"
            "containing 'bwrap' is in your PATH environment variable.\n"
            "\n"
            "If bubblewrap is not installed, contact your system administrator\n"
            "or install it locally (e.g., to an NFS-mounted location).\n"
            "\n"
            "To run without sandbox protection (DANGEROUS - for testing only):\n"
            "  --dangerously-skip-sandbox\n"
            "or set:\n"
            "  BRYNHILD_DANGEROUSLY_SKIP_SANDBOX=true"
        )

    if not is_bwrap_functional():
        raise BubblewrapNotFunctionalError(
            "bubblewrap (bwrap) is installed but cannot create sandboxes.\n"
            "\n"
            "This typically happens when:\n"
            "- User namespaces are disabled or restricted by the kernel\n"
            "- AppArmor or SELinux is blocking namespace creation\n"
            "- Running inside a container without namespace privileges\n"
            "\n"
            "On Ubuntu 24.04, AppArmor restricts unprivileged user namespaces.\n"
            "You may need to adjust kernel.apparmor_restrict_unprivileged_userns\n"
            "or use a bwrap with appropriate AppArmor profile.\n"
            "\n"
            "To run without sandbox protection (DANGEROUS - for testing only):\n"
            "  --dangerously-skip-sandbox\n"
            "or set:\n"
            "  BRYNHILD_DANGEROUSLY_SKIP_SANDBOX=true"
        )


def get_bwrap_command(
    command: str,
    project_root: _pathlib.Path,
    allowed_paths: list[_pathlib.Path] | None = None,
    allow_network: bool = False,
) -> str:
    """Wrap a command with bubblewrap sandbox.

    Creates a sandboxed environment where:
    - The filesystem is read-only by default
    - The project directory is writable
    - /tmp is writable
    - Additional paths can be made writable
    - Network is isolated (unless allow_network=True)

    Args:
        command: The shell command to execute
        project_root: Project directory (will be writable)
        allowed_paths: Additional paths to make writable
        allow_network: If True, allow network access

    Returns:
        The wrapped command string ready for shell execution
    """
    allowed_paths = allowed_paths or []

    args: list[str] = [
        "bwrap",
        # Mount the entire filesystem read-only
        "--ro-bind", "/", "/",
        # Essential virtual filesystems
        "--dev", "/dev",
        "--proc", "/proc",
        # Make project directory writable
        "--bind", str(project_root), str(project_root),
        # Make /tmp writable (needed for many operations)
        "--bind", "/tmp", "/tmp",
        # Clean up child processes when parent exits
        "--die-with-parent",
    ]

    # Add additional writable paths
    for path in allowed_paths:
        path_str = str(path)
        args.extend(["--bind", path_str, path_str])

    # Network isolation
    if not allow_network:
        args.append("--unshare-net")

    # The command to execute inside the sandbox
    args.extend(["/bin/bash", "-c", command])

    return " ".join(_shlex.quote(arg) for arg in args)

