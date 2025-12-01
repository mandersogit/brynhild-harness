"""
Rules system for loading project-specific instructions.

Rules are discovered from multiple sources and concatenated:
- AGENTS.md - Standard multi-framework rules file
- rules.md / .brynhild/rules.md - Brynhild-specific rules
- .cursorrules - Cross-tool compatibility

Discovery walks from current directory to root, collecting
rules at each level. Global rules (~/.config/brynhild/rules/)
are loaded first, then project rules override.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

# Rule file names to search for, in priority order
RULE_FILES = [
    "AGENTS.md",
    ".cursorrules",
    "rules.md",
    ".brynhild/rules.md",
]

# Global rules directory
GLOBAL_RULES_DIR = _pathlib.Path.home() / ".config" / "brynhild" / "rules"


def get_global_rules_path() -> _pathlib.Path:
    """Get the path to global rules directory."""
    return GLOBAL_RULES_DIR


def discover_rule_files(
    start_dir: _pathlib.Path,
    stop_at: _pathlib.Path | None = None,
) -> list[_pathlib.Path]:
    """
    Discover rule files by walking from start_dir toward root.

    Walks up the directory tree, collecting all rule files found.
    Files closer to root are returned first (lower priority).

    Args:
        start_dir: Directory to start searching from.
        stop_at: Directory to stop at (e.g., git root). If None,
                 stops at filesystem root.

    Returns:
        List of rule file paths, ordered root-first (lower priority first).
    """
    found: list[_pathlib.Path] = []
    current = start_dir.resolve()
    stop_at_resolved = stop_at.resolve() if stop_at else None

    # Collect all paths from root to current
    paths_to_check: list[_pathlib.Path] = []
    while True:
        paths_to_check.append(current)

        if stop_at_resolved and current == stop_at_resolved:
            break
        if current == current.parent:
            # Reached filesystem root
            break

        current = current.parent

    # Reverse so we go root-first
    paths_to_check.reverse()

    # Check each directory for rule files
    for dir_path in paths_to_check:
        for rule_file in RULE_FILES:
            rule_path = dir_path / rule_file
            if rule_path.is_file():
                found.append(rule_path)

    return found


def load_global_rules() -> list[tuple[_pathlib.Path, str]]:
    """
    Load all global rules from ~/.config/brynhild/rules/.

    Returns:
        List of (path, content) tuples for each rule file.
    """
    rules: list[tuple[_pathlib.Path, str]] = []

    if not GLOBAL_RULES_DIR.is_dir():
        return rules

    for rule_file in sorted(GLOBAL_RULES_DIR.glob("*.md")):
        try:
            content = rule_file.read_text(encoding="utf-8")
            rules.append((rule_file, content))
        except OSError:
            continue

    return rules


def load_rule_file(path: _pathlib.Path) -> str | None:
    """
    Load a single rule file.

    Args:
        path: Path to rule file.

    Returns:
        File content, or None if file doesn't exist or can't be read.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class RulesManager:
    """
    Manager for discovering and loading rules.

    Handles:
    - Global rules from ~/.config/brynhild/rules/
    - Project rules (AGENTS.md, rules.md, .cursorrules)
    - Walk-to-root discovery
    - Rule concatenation
    """

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        *,
        include_global: bool = True,
    ) -> None:
        """
        Initialize the rules manager.

        Args:
            project_root: Project root directory. If None, uses cwd.
            include_global: Whether to include global rules.
        """
        self._project_root = project_root or _pathlib.Path.cwd()
        self._include_global = include_global

        # Cache for loaded rules
        self._cached_rules: str | None = None
        self._cache_key: tuple[_pathlib.Path, bool] | None = None

    def get_project_root(self) -> _pathlib.Path:
        """Get the configured project root."""
        return self._project_root

    def discover_rules(self) -> list[_pathlib.Path]:
        """
        Discover all rule files in priority order.

        Returns:
            List of rule file paths (global first, then project).
        """
        paths: list[_pathlib.Path] = []

        # Global rules first (lowest priority)
        if self._include_global:
            global_rules = load_global_rules()
            paths.extend(path for path, _ in global_rules)

        # Project rules (walk to root)
        project_rules = discover_rule_files(
            self._project_root,
            stop_at=None,  # Walk to filesystem root
        )
        paths.extend(project_rules)

        return paths

    def load_rules(self, *, force_reload: bool = False) -> str:
        """
        Load and concatenate all rules.

        Rules are concatenated in priority order:
        1. Global rules (lowest priority)
        2. Project rules from root to current dir (higher priority)

        Results are cached; use force_reload=True to refresh.

        Args:
            force_reload: Force reload from disk even if cached.

        Returns:
            Concatenated rules content.
        """
        cache_key = (self._project_root, self._include_global)

        if (
            not force_reload
            and self._cached_rules is not None
            and self._cache_key == cache_key
        ):
            return self._cached_rules

        parts: list[str] = []

        # Global rules first
        if self._include_global:
            for _, content in load_global_rules():
                parts.append(content.strip())

        # Project rules
        for rule_path in discover_rule_files(self._project_root):
            rule_content = load_rule_file(rule_path)
            if rule_content:
                parts.append(rule_content.strip())

        # Concatenate with separators
        result = "\n\n---\n\n".join(parts) if parts else ""

        # Cache the result
        self._cached_rules = result
        self._cache_key = cache_key

        return result

    def get_rules_for_prompt(self) -> str:
        """
        Get rules formatted for inclusion in system prompt.

        Returns:
            Rules content wrapped in appropriate markers.
        """
        rules = self.load_rules()
        if not rules:
            return ""

        return f"""<project_rules>
{rules}
</project_rules>"""

    def list_rule_files(self) -> list[dict[str, _typing.Any]]:
        """
        List all discovered rule files with metadata.

        Returns:
            List of dicts with path, size, and source info.
        """
        result: list[dict[str, _typing.Any]] = []

        # Global rules
        if self._include_global:
            for path, content in load_global_rules():
                result.append({
                    "path": str(path),
                    "source": "global",
                    "size": len(content),
                })

        # Project rules
        for path in discover_rule_files(self._project_root):
            rule_content = load_rule_file(path)
            result.append({
                "path": str(path),
                "source": "project",
                "size": len(rule_content) if rule_content else 0,
            })

        return result

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_root": str(self._project_root),
            "include_global": self._include_global,
            "files": self.list_rule_files(),
            "total_length": len(self.load_rules()),
        }

