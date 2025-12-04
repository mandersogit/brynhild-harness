#!/usr/bin/env python3
"""
Generic commit helper - execute commits from YAML plans.

This is a standalone script that can be used in any project.

Requirements:
    pip install click pyyaml

Usage (execute directly, relies on shebang):
    ./commit-helper.py plan.yaml              # Preview (dry-run)
    ./commit-helper.py plan.yaml --execute    # Execute commits

Usage (with specific interpreter):
    /path/to/python commit-helper.py plan.yaml
"""

import pathlib as _pathlib
import subprocess as _subprocess
import sys as _sys
import typing as _typing

import click as _click
import yaml as _yaml


def _run_git(
    args: list[str],
    cwd: _pathlib.Path,
    dry_run: bool = False,
) -> _subprocess.CompletedProcess[str]:
    """Run a git command."""
    cmd = ["git"] + args
    if dry_run:
        _click.echo(f"  [DRY-RUN] {' '.join(cmd)}")
        return _subprocess.CompletedProcess(cmd, 0, "", "")

    result = _subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _click.echo(f"  ERROR: git {' '.join(args)}", err=True)
        _click.echo(f"  {result.stderr}", err=True)
        _sys.exit(1)
    return result


def _validate_files(
    files: list[str],
    repo_path: _pathlib.Path,
) -> list[str]:
    """Validate that all files exist. Returns list of missing files."""
    missing = []
    for f in files:
        path = repo_path / f
        if not path.exists():
            missing.append(f)
    return missing


def _find_duplicate_files(
    commits: list[dict[str, _typing.Any]],
) -> dict[str, list[int]]:
    """Find files that appear in multiple commits.

    Returns dict mapping filename to list of commit indices (1-based).
    """
    file_commits: dict[str, list[int]] = {}
    for i, commit in enumerate(commits, 1):
        for f in commit.get("files", []):
            if f not in file_commits:
                file_commits[f] = []
            file_commits[f].append(i)

    # Return only duplicates
    return {f: commits for f, commits in file_commits.items() if len(commits) > 1}


def _load_plan(plan_path: _pathlib.Path) -> dict[str, _typing.Any]:
    """Load commit plan from YAML file."""
    with plan_path.open() as f:
        result: dict[str, _typing.Any] = _yaml.safe_load(f)
        return result


def _get_repo_path(plan: dict[str, _typing.Any], plan_path: _pathlib.Path) -> _pathlib.Path:
    """Get repository path from plan or default to plan's directory."""
    if "repo" in plan:
        return _pathlib.Path(plan["repo"]).expanduser().resolve()
    # Default: directory containing the plan file
    return plan_path.parent.resolve()


def _preview_plan(plan_path: _pathlib.Path) -> None:
    """Show what would happen without executing."""
    plan = _load_plan(plan_path)
    repo_path = _get_repo_path(plan, plan_path)

    _click.echo(f"=== Commit Plan: {plan_path.name} ===")
    _click.echo(f"Repository: {repo_path}")
    commits = plan.get("commits", [])
    _click.echo(f"Commits: {len(commits)}")
    _click.echo()

    # Check for duplicate files (same file in multiple commits)
    duplicates = _find_duplicate_files(commits)
    if duplicates:
        _click.echo("ERROR: Files appear in multiple commits:", err=True)
        _click.echo("(Each file can only be in ONE commit - hunking not supported)", err=True)
        for f, commit_nums in sorted(duplicates.items()):
            _click.echo(f"  - {f} → commits {commit_nums}", err=True)
        _sys.exit(1)

    # Validate all files exist
    all_files: set[str] = set()
    for commit in commits:
        all_files.update(commit.get("files", []))

    missing = _validate_files(list(all_files), repo_path)
    if missing:
        _click.echo("ERROR: Missing files:", err=True)
        for f in missing:
            _click.echo(f"  - {f}", err=True)
        _sys.exit(1)

    _click.echo(_click.style(f"✓ All {len(all_files)} files exist", fg="green"))
    _click.echo()

    # Show each commit
    for i, commit in enumerate(commits, 1):
        msg_lines = commit["message"].strip().split("\n")
        title = msg_lines[0]
        files = commit.get("files", [])

        _click.echo(f"--- Commit {i}: {title} ---")
        _click.echo(f"Files ({len(files)}):")
        for f in files[:5]:
            _click.echo(f"  + {f}")
        if len(files) > 5:
            _click.echo(f"  ... and {len(files) - 5} more")
        _click.echo()


def _execute_plan(plan_path: _pathlib.Path, dry_run: bool = False) -> None:
    """Execute commits from the plan."""
    plan = _load_plan(plan_path)
    repo_path = _get_repo_path(plan, plan_path)
    commits = plan.get("commits", [])

    _click.echo(f"=== Executing commits in {repo_path} ===")
    if dry_run:
        _click.echo("(DRY RUN - no changes will be made)")
    _click.echo()

    # Check for duplicate files (same file in multiple commits)
    duplicates = _find_duplicate_files(commits)
    if duplicates:
        _click.echo("ERROR: Files appear in multiple commits:", err=True)
        _click.echo("(Each file can only be in ONE commit - hunking not supported)", err=True)
        for f, commit_nums in sorted(duplicates.items()):
            _click.echo(f"  - {f} → commits {commit_nums}", err=True)
        _sys.exit(1)

    # Validate all files exist
    all_files: set[str] = set()
    for commit in commits:
        all_files.update(commit.get("files", []))

    missing = _validate_files(list(all_files), repo_path)
    if missing:
        _click.echo("ERROR: Missing files:", err=True)
        for f in missing:
            _click.echo(f"  - {f}", err=True)
        _sys.exit(1)

    # Execute each commit
    for i, commit in enumerate(commits, 1):
        msg = commit["message"].strip()
        files = commit.get("files", [])
        title = msg.split("\n")[0]

        _click.echo(f">>> Commit {i}: {title}")

        # Stage files
        for f in files:
            _run_git(["add", f], repo_path, dry_run)

        # Check if there are staged changes
        if not dry_run:
            result = _subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=repo_path,
            )
            if result.returncode == 0:
                _click.echo("  (no changes to commit, skipping)")
                continue

        # Commit
        _run_git(["commit", "-m", msg], repo_path, dry_run)
        _click.echo()

    _click.echo("=== Done ===")
    if not dry_run:
        commit_count = len(commits)
        _run_git(["log", "--oneline", f"-{commit_count}"], repo_path, dry_run)


@_click.command()
@_click.argument("plan_file", type=_click.Path(exists=True, path_type=_pathlib.Path))
@_click.option(
    "--execute", "-x",
    is_flag=True,
    help="Execute commits (default is preview/dry-run)",
)
@_click.option(
    "--dry-run", "-n",
    is_flag=True,
    help="With --execute: show what would happen without committing",
)
def main(plan_file: _pathlib.Path, execute: bool, dry_run: bool) -> None:
    """
    Execute commits from a YAML plan file.

    By default, shows a preview of what would happen.
    Use --execute to actually create the commits.

    \b
    Examples:
        python commit-helper.py plan.yaml              # Preview
        python commit-helper.py plan.yaml --execute    # Execute
        python commit-helper.py plan.yaml -x -n        # Execute dry-run
    """
    if execute:
        _execute_plan(plan_file, dry_run=dry_run)
    else:
        _preview_plan(plan_file)


if __name__ == "__main__":
    main()

