---
name: commit-helper
description: Create and execute git commit plans from YAML files - use when organizing changes into logical commits or when user wants help structuring their git history
---

# Commit Helper Skill

## ⚠️ CRITICAL: NO AUTONOMOUS COMMITS ⚠️

**NEVER execute commits without explicit user authorization.**

This skill is for:
1. **Creating commit plans** - Always allowed
2. **Previewing plans** - Always allowed (read-only)
3. **Executing commits** - ONLY when user explicitly says to commit

**If in doubt, ask the user before any git-modifying operation.**

---

## When to Use This Skill

Use this skill when the user needs to:
- Organize changes into logical, well-structured commits
- Create a commit plan for review before executing
- Document what changes belong together
- Manage complex multi-commit workflows

## The Commit Plan Approach

Instead of committing changes ad-hoc, create a YAML plan that:
1. Groups related changes into logical commits
2. Provides clear commit messages
3. Can be reviewed before execution
4. Can be re-run if interrupted (idempotent)

## Commit Plan Format

Plans are YAML files. Naming convention: `YYYY-MM-DD-description.yaml`

### Minimal Plan (Single Repo)

```yaml
# Commit plan: Feature X
# Date: 2024-12-01

commits:
  - message: |
      feat: add user authentication

      - Add login endpoint
      - Add session management
      - Add logout functionality
    files:
      - src/auth/login.py
      - src/auth/session.py
      - tests/test_auth.py
```

### Plan with Explicit Repo Path

```yaml
# Commit plan with explicit repo
repo: /path/to/my/project

commits:
  - message: |
      fix: correct date formatting

      Dates were displaying in wrong timezone.
    files:
      - src/utils/dates.py
      - tests/test_dates.py
```

### Multi-Commit Plan

```yaml
commits:
  # ============================================================
  # Commit 1: Security fix
  # ============================================================
  - message: |
      security: validate user input

      Prevent SQL injection in search endpoint.
    files:
      - src/api/search.py
      - tests/test_search.py

  # ============================================================
  # Commit 2: Feature
  # ============================================================
  - message: |
      feat: add export functionality

      Users can now export data as CSV.
    files:
      - src/api/export.py
      - src/utils/csv.py
      - tests/test_export.py
```

## Commit Message Types

Use conventional commit prefixes:
- `feat:` - New feature
- `fix:` - Bug fix
- `refactor:` - Code change that neither fixes nor adds
- `security:` - Security improvement
- `improve:` - Enhancement to existing functionality
- `build:` - Build system or dependencies
- `config:` - Configuration changes
- `docs:` - Documentation only
- `test:` - Adding or correcting tests
- `chore:` - Other changes

## Using the Bundled Script

This skill includes a standalone script: `scripts/commit-helper.py`

**Required packages:** `click`, `pyyaml`

### Running the Script

**Default: Execute directly (relies on shebang)**

```bash
./scripts/commit-helper.py plan.yaml              # Preview
./scripts/commit-helper.py plan.yaml --execute    # Execute
./scripts/commit-helper.py plan.yaml -x -n        # Dry-run
```

**If you have a preferred Python interpreter** (e.g., project venv):

```bash
/path/to/python scripts/commit-helper.py plan.yaml
```

### If Dependencies Are Missing

If the script fails due to missing `click` or `pyyaml`:

1. **Report the error to the user** - Do NOT attempt to install packages autonomously
2. **Tell the user what's needed** - "This script requires `click` and `pyyaml`"
3. **Let the user decide** how to install (system pip, venv, etc.)

**Exception:** If you have explicit custody of a project venv (e.g., `./venv/bin/python`) and the user has authorized package installation, then you may install dependencies there.

## Creating a Commit Plan

### Step 1: Identify Changed Files

```bash
git status
git diff
```

### Step 2: Group Changes Logically

**Good groupings:**
- All files for a single feature
- All files for a bug fix
- Related refactoring together
- Config/build changes together

**Bad groupings:**
- Unrelated changes in one commit
- Single file per commit (too granular)
- Feature + formatting in same commit

### Step 3: Write the Plan

Create `YYYY-MM-DD-description.yaml` with:
1. Header comment with title and date
2. Optional `repo:` path (defaults to plan's directory)
3. `commits:` list with message and files

### Step 4: Preview

```bash
python scripts/commit-helper.py plan.yaml
```

This validates files exist and shows what would happen.

### Step 5: Execute (WITH USER AUTHORIZATION)

```bash
python scripts/commit-helper.py plan.yaml --execute
```

## Re-running After Interruption

The script is idempotent:
- Already-committed files stage with no changes
- `git diff --cached --quiet` detects nothing to commit
- Skips with "(no changes to commit, skipping)"

Safe to re-run the same plan after partial completion.

## Summary: What You Can Do Autonomously

| Action                         | Autonomous?                           |
|--------------------------------|---------------------------------------|
| Create commit plan YAML        | ✅ Yes                                 |
| Run preview (no --execute)     | ✅ Yes                                 |
| Run --execute --dry-run        | ✅ Yes                                 |
| Run --execute                  | ❌ NO - requires explicit user request |
| Any direct `git commit`        | ❌ NO - NEVER                          |
| Any direct `git push`          | ❌ NO - NEVER                          |

---

## Advanced: Multi-Repo Sync (brynhild-specific)

For projects with parallel repositories (e.g., development + public release), the brynhild project includes an extended script at `scripts/commit-helper` that supports:

```yaml
source_repo: /path/to/dev/repo
public_repo: /path/to/public/repo

commits:
  - message: |
      feat: new feature
    files:
      - src/feature.py
```

Commands:
- `./scripts/commit-helper plan.yaml` - Preview
- `./scripts/commit-helper plan.yaml execute` - Commit to source repo
- `./scripts/commit-helper plan.yaml sync-public` - Copy and commit to public repo

This is specific to brynhild's dual-repo workflow and not needed for typical single-repo use.
