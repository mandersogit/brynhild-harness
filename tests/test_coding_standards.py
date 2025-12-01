"""
Tests that enforce coding standards.

These tests verify that the codebase follows our import conventions.
"""

import pathlib as _pathlib

import pytest as _pytest

# Directories to check
SRC_DIR = _pathlib.Path(__file__).parent.parent / "src" / "brynhild"
TESTS_DIR = _pathlib.Path(__file__).parent.parent / "tests"


def _get_python_files(directory: _pathlib.Path) -> list[_pathlib.Path]:
    """Get all Python files in a directory, recursively."""
    return list(directory.rglob("*.py"))


def _is_init_file(path: _pathlib.Path) -> bool:
    """Check if a file is an __init__.py file."""
    return path.name == "__init__.py"


def _extract_imports(content: str) -> list[tuple[int, str]]:
    """
    Extract 'from X import Y' statements from file content.

    Returns list of (line_number, line_content) tuples.
    Excludes:
    - 'from __future__ import' (allowed)
    - Lines inside TYPE_CHECKING blocks (allowed)
    """
    lines = content.split("\n")
    imports: list[tuple[int, str]] = []

    in_type_checking = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track TYPE_CHECKING blocks
        if "if TYPE_CHECKING:" in line or "if _typing.TYPE_CHECKING:" in line:
            in_type_checking = True
            continue

        # End of TYPE_CHECKING block (simplistic detection)
        if (
            in_type_checking
            and stripped
            and not stripped.startswith("#")
            and not line.startswith(" ")
            and not line.startswith("\t")
        ):
            in_type_checking = False

        # Skip if we're in a TYPE_CHECKING block
        if in_type_checking:
            continue

        # Check for forbidden import pattern
        if stripped.startswith("from ") and " import " in stripped:
            # Allow __future__ imports
            if "from __future__ import" in stripped:
                continue

            imports.append((i, stripped))

    return imports


def _check_file_imports(path: _pathlib.Path) -> list[str]:
    """
    Check a file for import violations.

    Returns list of violation messages.
    """
    # Skip __init__.py files (re-exports are allowed)
    if _is_init_file(path):
        return []

    content = path.read_text()
    violations = []

    for line_num, line in _extract_imports(content):
        violations.append(f"{path}:{line_num}: {line}")

    return violations


class TestImportStyle:
    """Tests for import style compliance."""

    def test_src_no_from_imports(self) -> None:
        """Source files should not use 'from X import Y' pattern."""
        violations: list[str] = []

        for path in _get_python_files(SRC_DIR):
            violations.extend(_check_file_imports(path))

        if violations:
            msg = "Found forbidden 'from X import Y' imports:\n"
            msg += "\n".join(f"  {v}" for v in violations)
            msg += "\n\nUse 'import X as _x' (external) or 'import X as x' (internal) instead."
            _pytest.fail(msg)

    def test_tests_no_from_imports(self) -> None:
        """Test files should not use 'from X import Y' pattern."""
        violations: list[str] = []

        for path in _get_python_files(TESTS_DIR):
            # Skip this file itself
            if path.name == "test_coding_standards.py":
                continue
            violations.extend(_check_file_imports(path))

        if violations:
            msg = "Found forbidden 'from X import Y' imports:\n"
            msg += "\n".join(f"  {v}" for v in violations)
            msg += "\n\nUse 'import X as _x' (external) or 'import X as x' (internal) instead."
            _pytest.fail(msg)


class TestImportExtraction:
    """Tests for the import extraction logic itself."""

    def test_detects_from_import(self) -> None:
        """Should detect basic from imports."""
        content = "from pathlib import Path"
        imports = _extract_imports(content)
        assert len(imports) == 1
        assert imports[0][1] == "from pathlib import Path"

    def test_allows_future_imports(self) -> None:
        """Should allow __future__ imports."""
        content = "from __future__ import annotations"
        imports = _extract_imports(content)
        assert len(imports) == 0

    def test_ignores_type_checking_block(self) -> None:
        """Should ignore imports inside TYPE_CHECKING blocks."""
        content = """
import typing as _typing

if _typing.TYPE_CHECKING:
    from some_module import SomeType

def foo():
    pass
"""
        imports = _extract_imports(content)
        assert len(imports) == 0

    def test_detects_import_after_type_checking(self) -> None:
        """Should still detect imports after TYPE_CHECKING block ends."""
        content = """
import typing as _typing

if _typing.TYPE_CHECKING:
    from allowed import Type

from forbidden import Other

def foo():
    pass
"""
        imports = _extract_imports(content)
        assert len(imports) == 1
        assert "from forbidden import Other" in imports[0][1]

