#!/bin/bash
# -*- mode: python -*-
# vim: set ft=python:
# Polyglot bash/python script - bash delegates to venv python
"true" '''\'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
exec "$PROJECT_ROOT/local.venv/bin/python" "$0" "$@"
'''

"""
Find all hardcoded constants in the codebase using AST analysis.

Categories detected:
1. Magic numbers in comparisons (> N, < N, == N)
2. Magic numbers in assignments (x = N)
3. Magic numbers in function defaults (def foo(x=N))
4. Magic numbers in function calls (foo(limit=N))
5. Module-level ALL_CAPS assignments
6. Hardcoded strings (URLs, paths)
7. Slice literals ([:N], [-N:])
"""

import ast as _ast
import dataclasses as _dataclasses
import pathlib as _pathlib
import re as _re
import sys as _sys
import typing as _typing

# Numbers to ignore (common, non-magic)
IGNORED_NUMBERS = {0, 1, 2, -1, True, False, None}

# Strings to ignore
IGNORED_STRINGS = {"", "utf-8", "utf8", "w", "r", "rb", "wb", "a"}

# ALL_CAPS pattern
ALL_CAPS_PATTERN = _re.compile(r"^[A-Z][A-Z0-9_]+$")


@_dataclasses.dataclass
class Finding:
    """A constant finding."""
    
    file: str
    line: int
    category: str
    name: str | None
    value: _typing.Any
    context: str


class ConstantFinder(_ast.NodeVisitor):
    """AST visitor to find constants."""
    
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[Finding] = []
        self._in_class: str | None = None
        self._in_function: str | None = None
    
    def _add_finding(
        self,
        node: _ast.AST,
        category: str,
        name: str | None,
        value: _typing.Any,
        context: str,
    ) -> None:
        self.findings.append(Finding(
            file=self.filename,
            line=node.lineno,
            category=category,
            name=name,
            value=repr(value) if isinstance(value, str) else value,
            context=context,
        ))
    
    def visit_ClassDef(self, node: _ast.ClassDef) -> None:
        old_class = self._in_class
        self._in_class = node.name
        self.generic_visit(node)
        self._in_class = old_class
    
    def visit_FunctionDef(self, node: _ast.FunctionDef) -> None:
        old_func = self._in_function
        self._in_function = node.name
        
        # Check function defaults
        all_args = node.args.args + node.args.posonlyargs + node.args.kwonlyargs
        defaults = node.args.defaults + node.args.kw_defaults
        
        # Align defaults with args (defaults are right-aligned)
        num_no_default = len(all_args) - len([d for d in defaults if d is not None])
        
        for i, default in enumerate(defaults):
            if default is None:
                continue
            if isinstance(default, _ast.Constant):
                val = default.value
                if self._is_interesting_value(val):
                    # Find the arg name
                    arg_idx = num_no_default + i
                    if arg_idx < len(all_args):
                        arg_name = all_args[arg_idx].arg
                    else:
                        arg_name = "?"
                    self._add_finding(
                        default,
                        "function_default",
                        arg_name,
                        val,
                        f"def {node.name}({arg_name}={val!r})",
                    )
        
        self.generic_visit(node)
        self._in_function = old_func
    
    visit_AsyncFunctionDef = visit_FunctionDef
    
    def visit_Assign(self, node: _ast.Assign) -> None:
        """Check assignments for constants."""
        # Only care about simple name assignments
        if len(node.targets) == 1 and isinstance(node.targets[0], _ast.Name):
            name = node.targets[0].id
            
            # Module-level ALL_CAPS
            if (self._in_function is None and 
                self._in_class is None and 
                ALL_CAPS_PATTERN.match(name)):
                if isinstance(node.value, _ast.Constant):
                    self._add_finding(
                        node,
                        "module_constant",
                        name,
                        node.value.value,
                        f"{name} = {node.value.value!r}",
                    )
                elif isinstance(node.value, (_ast.List, _ast.Dict, _ast.Set, _ast.Tuple)):
                    self._add_finding(
                        node,
                        "module_constant",
                        name,
                        f"<{type(node.value).__name__}>",
                        f"{name} = <{type(node.value).__name__}>",
                    )
            
            # Local magic number assignment
            elif isinstance(node.value, _ast.Constant):
                val = node.value.value
                if self._is_interesting_value(val) and not ALL_CAPS_PATTERN.match(name):
                    scope = self._get_scope()
                    self._add_finding(
                        node,
                        "magic_assignment",
                        name,
                        val,
                        f"{scope}{name} = {val!r}",
                    )
        
        self.generic_visit(node)
    
    def visit_Compare(self, node: _ast.Compare) -> None:
        """Check comparisons for magic numbers."""
        for comparator in node.comparators:
            if isinstance(comparator, _ast.Constant):
                val = comparator.value
                if self._is_interesting_value(val):
                    self._add_finding(
                        comparator,
                        "magic_comparison",
                        None,
                        val,
                        f"comparison with {val!r}",
                    )
        
        self.generic_visit(node)
    
    def visit_Call(self, node: _ast.Call) -> None:
        """Check function calls for magic keyword arguments."""
        for keyword in node.keywords:
            if keyword.arg and isinstance(keyword.value, _ast.Constant):
                val = keyword.value.value
                if self._is_interesting_value(val):
                    # Get function name
                    func_name = self._get_call_name(node.func)
                    self._add_finding(
                        keyword,
                        "magic_kwarg",
                        keyword.arg,
                        val,
                        f"{func_name}({keyword.arg}={val!r})",
                    )
        
        self.generic_visit(node)
    
    def visit_Subscript(self, node: _ast.Subscript) -> None:
        """Check slices for magic numbers."""
        if isinstance(node.slice, _ast.Slice):
            for attr in ("lower", "upper", "step"):
                bound = getattr(node.slice, attr)
                if isinstance(bound, _ast.Constant):
                    val = bound.value
                    if isinstance(val, int) and val not in IGNORED_NUMBERS:
                        self._add_finding(
                            bound,
                            "magic_slice",
                            None,
                            val,
                            f"slice with {attr}={val}",
                        )
                elif isinstance(bound, _ast.UnaryOp) and isinstance(bound.op, _ast.USub):
                    if isinstance(bound.operand, _ast.Constant):
                        val = -bound.operand.value
                        if val not in IGNORED_NUMBERS:
                            self._add_finding(
                                bound,
                                "magic_slice",
                                None,
                                val,
                                f"slice with {attr}={val}",
                            )
        
        self.generic_visit(node)
    
    def _is_interesting_value(self, val: _typing.Any) -> bool:
        """Check if a value is an interesting constant."""
        if val in IGNORED_NUMBERS:
            return False
        if isinstance(val, str):
            if val in IGNORED_STRINGS:
                return False
            # Interesting strings: URLs, paths, or short config-like strings
            if val.startswith(("http://", "https://", "/", "~/")):
                return True
            if len(val) < 50 and not val.startswith("<"):
                return False  # Skip short strings (likely format strings)
            return False
        if isinstance(val, (int, float)):
            return True
        return False
    
    def _get_scope(self) -> str:
        """Get current scope prefix."""
        parts = []
        if self._in_class:
            parts.append(self._in_class)
        if self._in_function:
            parts.append(self._in_function)
        return ".".join(parts) + "." if parts else ""
    
    def _get_call_name(self, node: _ast.AST) -> str:
        """Get function name from call node."""
        if isinstance(node, _ast.Name):
            return node.id
        elif isinstance(node, _ast.Attribute):
            return f"...{node.attr}"
        return "<call>"


def analyze_file(path: _pathlib.Path) -> list[Finding]:
    """Analyze a single Python file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = _ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Skipping {path}: {e}", file=_sys.stderr)
        return []
    
    finder = ConstantFinder(str(path))
    finder.visit(tree)
    return finder.findings


def main() -> None:
    """Main entry point."""
    src_dir = _pathlib.Path("src/brynhild")
    
    if not src_dir.exists():
        print(f"Directory not found: {src_dir}", file=_sys.stderr)
        _sys.exit(1)
    
    all_findings: list[Finding] = []
    
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        findings = analyze_file(py_file)
        all_findings.extend(findings)
    
    # Group by category
    by_category: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_category.setdefault(f.category, []).append(f)
    
    # Print results
    print("=" * 80)
    print("CONSTANT ANALYSIS REPORT")
    print("=" * 80)
    
    for category in sorted(by_category.keys()):
        findings = by_category[category]
        print(f"\n## {category.upper()} ({len(findings)} findings)\n")
        
        for f in sorted(findings, key=lambda x: (x.file, x.line)):
            rel_path = f.file.replace("src/brynhild/", "")
            print(f"  {rel_path}:{f.line}")
            print(f"    {f.context}")
            print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for category in sorted(by_category.keys()):
        print(f"  {category}: {len(by_category[category])}")
    print(f"\n  TOTAL: {len(all_findings)}")


if __name__ == "__main__":
    main()

