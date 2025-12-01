"""
Sandbox utilities for restricting tool execution.

Provides:
- Path validation to restrict file operations to project directory
- Sensitive path blocklist (platform-aware)
- Seatbelt profile for macOS sandbox-exec
- Sandbox wrapper for command execution (platform-aware)
"""

from __future__ import annotations

import os as _os
import pathlib as _pathlib
import platform as _platform
import tempfile as _tempfile
import typing as _typing


def _get_sensitive_paths() -> tuple[list[str], list[str]]:
    """Get platform-specific sensitive paths.

    Returns:
        Tuple of (read_blocklist, write_blocklist)
    """
    system = _platform.system()

    if system == "Darwin":
        # macOS paths
        read_blocklist = [
            "/Users",       # All user home directories
            "/Volumes",     # All mounted drives, disk images, network mounts
        ]
        write_blocklist = [
            "/Users",       # All user home directories
            "/Volumes",     # All mounted drives, disk images, network mounts
            "/System",      # macOS system files
            "/Library",     # System-wide libraries and preferences
            "/Applications",  # Installed applications
            "/private",     # macOS: /tmp, /var, /etc are symlinks to /private/*
            "/cores",       # Core dumps
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/var",
            "/opt",
        ]
    elif system == "Linux":
        # Linux paths
        read_blocklist = [
            "/home",        # All user home directories
            "/root",        # Root user home
            "/mnt",         # Mount points
            "/media",       # Removable media
            "/run/media",   # User-mounted media (systemd)
        ]
        write_blocklist = [
            "/home",        # All user home directories
            "/root",        # Root user home
            "/mnt",         # Mount points
            "/media",       # Removable media
            "/run/media",   # User-mounted media (systemd)
            "/etc",         # System configuration
            "/usr",         # User programs
            "/bin",         # Essential binaries
            "/sbin",        # System binaries
            "/var",         # Variable data
            "/opt",         # Optional packages
            "/boot",        # Boot files
            "/lib",         # Essential libraries
            "/lib64",       # 64-bit libraries
            "/lib32",       # 32-bit libraries
            "/srv",         # Service data
        ]
    else:
        # Windows or unknown - minimal protection
        read_blocklist = []
        write_blocklist = []

    return (read_blocklist, write_blocklist)


# Initialize platform-specific paths at module load time
_SENSITIVE_READ_PATHS, _SENSITIVE_WRITE_PATHS = _get_sensitive_paths()

# Paths that should never be READ from by tools
# Block all user data, with exceptions for project directory
SENSITIVE_READ_PATHS: list[str] = _SENSITIVE_READ_PATHS

# Paths that should never be WRITTEN to by tools
# The project directory and /tmp are exceptions (checked first in validation)
SENSITIVE_WRITE_PATHS: list[str] = _SENSITIVE_WRITE_PATHS


class PathValidationError(Exception):
    """Raised when a path fails validation."""

    pass


class SandboxConfig:
    """Configuration for sandbox behavior."""

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        allowed_paths: list[_pathlib.Path] | None = None,
        blocked_paths: list[str] | None = None,
        allow_network: bool = False,
        dry_run: bool = False,
        skip_sandbox: bool = False,
    ) -> None:
        """
        Initialize sandbox configuration.

        Args:
            project_root: Root directory for the project (writes restricted here)
            allowed_paths: Additional paths where writes are allowed
            blocked_paths: Additional paths to block (beyond defaults)
            allow_network: Whether to allow network access
            dry_run: If True, don't actually execute commands
            skip_sandbox: If True, skip OS-level sandbox (DANGEROUS)
        """
        self.project_root = project_root or _pathlib.Path.cwd()
        self.allowed_paths = allowed_paths or []
        self.blocked_paths = blocked_paths or []
        self.allow_network = allow_network
        self.dry_run = dry_run
        self.skip_sandbox = skip_sandbox

        # Build allowed write paths
        # Include /tmp and system temp dir, handling macOS /tmp -> /private/tmp symlink
        tmp_paths = self._get_tmp_paths()
        self._allowed_write_paths = (
            [self.project_root.resolve()]
            + tmp_paths
            + [p.resolve() for p in self.allowed_paths]
        )

        # Expand and resolve blocked paths (separate for read and write)
        self._blocked_read_paths = self._expand_paths(
            SENSITIVE_READ_PATHS + self.blocked_paths
        )
        self._blocked_write_paths = self._expand_paths(
            SENSITIVE_WRITE_PATHS + self.blocked_paths
        )

    def _get_tmp_paths(self) -> list[_pathlib.Path]:
        """Get temp directory paths, handling symlinks."""
        paths: list[_pathlib.Path] = []

        # Standard /tmp
        tmp = _pathlib.Path("/tmp")
        if tmp.exists():
            paths.append(tmp.resolve())

        # macOS /private/tmp (in case /tmp doesn't exist or isn't a symlink)
        private_tmp = _pathlib.Path("/private/tmp")
        if private_tmp.exists():
            resolved = private_tmp.resolve()
            if resolved not in paths:
                paths.append(resolved)

        # System temp directory
        system_tmp = _pathlib.Path(_tempfile.gettempdir())
        if system_tmp.exists():
            resolved = system_tmp.resolve()
            if resolved not in paths:
                paths.append(resolved)

        return paths

    def _expand_paths(self, patterns: list[str]) -> list[_pathlib.Path]:
        """Expand ~ in paths and resolve them."""
        result: list[_pathlib.Path] = []
        for pattern in patterns:
            expanded = _os.path.expanduser(pattern)
            path = _pathlib.Path(expanded)
            if path.exists():
                result.append(path.resolve())
            else:
                # Still add it so we can block attempts to create it
                result.append(_pathlib.Path(expanded))
        return result


def validate_path(
    path: _pathlib.Path | str,
    config: SandboxConfig,
    operation: _typing.Literal["read", "write"] = "write",
) -> _pathlib.Path:
    """
    Validate a path for sandbox compliance.

    For writes, the logic is:
    1. Check if path is in an ALLOWED directory (project, /tmp) -> ALLOW
    2. Check if path is in a BLOCKED directory (~, /etc, etc.) -> BLOCK
    3. Otherwise -> BLOCK (writes must be to an allowed path)

    This allows the project directory to "punch through" the home directory block.

    Args:
        path: The path to validate
        config: Sandbox configuration
        operation: The type of operation (read or write)

    Returns:
        The resolved, validated path

    Raises:
        PathValidationError: If the path is not allowed
    """
    if isinstance(path, str):
        path = _pathlib.Path(path)

    # Resolve the path (handles .., symlinks, etc.)
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        raise PathValidationError(f"Cannot resolve path: {path} ({e})") from e

    # For WRITES: Check allowed paths FIRST (allows project to punch through ~ block)
    if operation == "write":
        is_allowed = False
        for allowed in config._allowed_write_paths:
            try:
                resolved.relative_to(allowed)
                is_allowed = True
                break
            except ValueError:
                continue

        if is_allowed:
            # Path is in an allowed directory - permit it
            return resolved

        # Path is not in allowed directory - check if it's blocked
        for blocked in config._blocked_write_paths:
            try:
                resolved.relative_to(blocked)
                raise PathValidationError(
                    f"Write access denied: {path} is in a protected location. "
                    f"Writes are only allowed to: {config.project_root}, /tmp"
                )
            except ValueError:
                pass

        # Not in allowed and not explicitly blocked - still deny writes
        raise PathValidationError(
            f"Write access denied: {path} is outside allowed directories. "
            f"Writes are only allowed to: {config.project_root}, /tmp"
        )

    # For READS: Check allowed paths FIRST (allows project to punch through)
    for allowed in config._allowed_write_paths:
        try:
            resolved.relative_to(allowed)
            # Path is in an allowed directory - permit read
            return resolved
        except ValueError:
            continue

    # Not in allowed directory - check if blocked
    for blocked in config._blocked_read_paths:
        try:
            resolved.relative_to(blocked)
            raise PathValidationError(
                f"Read access denied: {path} is in a protected location. "
                f"Reads are only allowed from: project directory, /tmp, system paths"
            )
        except ValueError:
            pass

    # Not in allowed AND not in blocked - allow (needed for /usr, /bin, /System, etc.)
    return resolved


def is_path_safe(
    path: _pathlib.Path | str,
    config: SandboxConfig,
    operation: _typing.Literal["read", "write"] = "write",
) -> bool:
    """
    Check if a path is safe for the given operation.

    Non-throwing version of validate_path.
    """
    try:
        validate_path(path, config, operation)
        return True
    except PathValidationError:
        return False


def resolve_and_validate(
    path: str,
    base_dir: _pathlib.Path,
    config: SandboxConfig,
    operation: _typing.Literal["read", "write"],
) -> _pathlib.Path:
    """
    Resolve a relative path and validate it against sandbox rules.

    This is a convenience function that combines path expansion,
    resolution, and validation in a single call.

    Args:
        path: The path string (may be relative, may contain ~)
        base_dir: Base directory for relative paths
        config: Sandbox configuration
        operation: The type of operation (read or write)

    Returns:
        The resolved, validated absolute path

    Raises:
        PathValidationError: If the path is not allowed
    """
    import os as _os_local  # Local import to avoid module-level dependency

    # Expand ~ to home directory
    expanded = _os_local.path.expanduser(path)
    resolved = _pathlib.Path(expanded)

    # Make relative paths absolute using base_dir
    if not resolved.is_absolute():
        resolved = base_dir / resolved

    # Validate against sandbox rules
    return validate_path(resolved, config, operation)


def generate_seatbelt_profile(config: SandboxConfig) -> str:
    """
    Generate a macOS Seatbelt profile for sandbox-exec.

    The profile:
    - Allows read access to most of the filesystem
    - Restricts writes to project directory and /tmp
    - Blocks network access (unless allow_network is True)
    - Blocks access to sensitive paths
    """
    # Build list of allowed write paths for the profile
    write_paths = []
    for path in config._allowed_write_paths:
        # Seatbelt uses regex, so escape special characters
        path_str = str(path).replace("\\", "\\\\").replace('"', '\\"')
        write_paths.append(path_str)

    # Build blocked path patterns (use read paths for read blocking,
    # write paths control is done via allowed list)
    blocked_patterns = []
    for path in config._blocked_read_paths:
        path_str = str(path).replace("\\", "\\\\").replace('"', '\\"')
        blocked_patterns.append(path_str)

    profile = f'''\
;; Brynhild sandbox profile
;; Generated for project: {config.project_root}
;;
;; This profile restricts:
;; - File writes to project directory and /tmp only
;; - Network access (blocked)
;; - Access to sensitive paths

(version 1)

;; Start with deny-all
(deny default)

;; Allow basic process operations
(allow process-fork)
(allow process-exec)
(allow signal)

;; Allow reading from most places
(allow file-read*)

;; Block reads from sensitive locations
'''

    for blocked in blocked_patterns:
        profile += f'(deny file-read* (subpath "{blocked}"))\n'

    # Re-allow reads for allowed paths (punches through /Users block)
    # This must come AFTER the deny rules since later rules take precedence
    profile += '''
;; Re-allow reads for project and allowed directories (overrides blocks above)
'''
    for write_path in write_paths:
        profile += f'(allow file-read* (subpath "{write_path}"))\n'

    profile += '''
;; Allow writes only to specific directories
'''

    for write_path in write_paths:
        profile += f'(allow file-write* (subpath "{write_path}"))\n'

    if config.allow_network:
        profile += '''
;; Network access allowed
(allow network*)
'''
    else:
        profile += '''
;; Network access blocked
(deny network*)
'''

    profile += '''
;; Allow basic system operations
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix-shm-read*)
(allow ipc-posix-shm-write-create)
(allow ipc-posix-shm-write-data)
'''

    return profile


def get_sandbox_command(
    command: str,
    config: SandboxConfig,
    profile_path: _pathlib.Path | None = None,
) -> tuple[str, _pathlib.Path | None]:
    """
    Wrap a command for sandbox execution.

    Uses platform-appropriate sandbox mechanism:
    - macOS: sandbox-exec with Seatbelt profiles
    - Linux: bubblewrap (bwrap)

    Args:
        command: The command to execute
        config: Sandbox configuration
        profile_path: Optional path to save the profile (macOS only, temporary if None)

    Returns:
        Tuple of (wrapped_command, profile_path_if_created)

    Raises:
        BubblewrapNotFoundError: On Linux if bwrap not installed and
            skip_sandbox is False.
    """
    if config.dry_run:
        return f"echo '[DRY RUN] Would execute: {command}'", None

    # Skip sandbox if explicitly disabled (dangerous!)
    if config.skip_sandbox:
        return command, None

    system = _platform.system()

    if system == "Darwin":
        return _get_seatbelt_command(command, config, profile_path)
    elif system == "Linux":
        return _get_linux_sandbox_command(command, config)
    else:
        # Unsupported platform - warn and run unsandboxed
        import warnings as _warnings

        _warnings.warn(
            f"No sandbox available for {system}. "
            "Running command without OS-level protection.",
            RuntimeWarning,
            stacklevel=2,
        )
        return command, None


def _get_seatbelt_command(
    command: str,
    config: SandboxConfig,
    profile_path: _pathlib.Path | None = None,
) -> tuple[str, _pathlib.Path | None]:
    """macOS sandbox-exec implementation."""
    # Generate profile
    profile = generate_seatbelt_profile(config)

    # Create temporary file for profile
    if profile_path is None:
        fd, temp_path = _tempfile.mkstemp(suffix=".sb", prefix="brynhild_")
        profile_path = _pathlib.Path(temp_path)
        _os.close(fd)

    profile_path.write_text(profile)

    # Build sandboxed command
    # Note: We escape the command for shell safety
    escaped_command = command.replace("'", "'\"'\"'")
    wrapped = f"sandbox-exec -f '{profile_path}' /bin/bash -c '{escaped_command}'"

    return wrapped, profile_path


def _get_linux_sandbox_command(
    command: str,
    config: SandboxConfig,
) -> tuple[str, _pathlib.Path | None]:
    """Linux sandbox implementation using bubblewrap.

    Raises:
        BubblewrapNotFoundError: If bwrap not installed.
    """
    import brynhild.tools.sandbox_linux as sandbox_linux

    # This raises BubblewrapNotFoundError if not available
    sandbox_linux.require_bwrap()

    # Build list of additional allowed paths (exclude project_root since it's passed separately)
    additional_paths = [
        p for p in config._allowed_write_paths
        if p != config.project_root.resolve()
    ]

    wrapped = sandbox_linux.get_bwrap_command(
        command=command,
        project_root=config.project_root,
        allowed_paths=additional_paths,
        allow_network=config.allow_network,
    )
    return wrapped, None


def cleanup_sandbox_profile(profile_path: _pathlib.Path | None) -> None:
    """Clean up a temporary sandbox profile."""
    import contextlib as _contextlib

    if profile_path and profile_path.exists():
        with _contextlib.suppress(OSError):
            profile_path.unlink()


# Convenience function for quick path checking
def check_write_path(
    path: _pathlib.Path | str,
    project_root: _pathlib.Path | None = None,
) -> _pathlib.Path:
    """
    Validate a path for write access.

    Convenience wrapper that creates a temporary SandboxConfig.

    Args:
        path: The path to validate
        project_root: Project root directory (default: cwd)

    Returns:
        The resolved, validated path

    Raises:
        PathValidationError: If the path is not allowed
    """
    config = SandboxConfig(project_root=project_root)
    return validate_path(path, config, operation="write")


def check_read_path(
    path: _pathlib.Path | str,
    project_root: _pathlib.Path | None = None,
) -> _pathlib.Path:
    """
    Validate a path for read access.

    Convenience wrapper that creates a temporary SandboxConfig.

    Args:
        path: The path to validate
        project_root: Project root directory (default: cwd)

    Returns:
        The resolved, validated path

    Raises:
        PathValidationError: If the path is not allowed
    """
    config = SandboxConfig(project_root=project_root)
    return validate_path(path, config, operation="read")

