---
name: skill-creator
description: Create effective skills for brynhild agents. Use when the user wants to create, update, or improve a skill that extends agent capabilities with specialized knowledge, workflows, or tool integrations.
---

# Skill Creator

Skills are modular packages that extend an agent's capabilities with specialized knowledge, workflows, and tools. Think of them as "onboarding guides" that transform a general-purpose agent into a specialized one.

## Core Principle: The Context Window is a Public Good

Skills share context with: system prompt, conversation history, other skills' metadata, and the user's request.

**Default assumption: The agent is already very smart.** Only add context it doesn't already have. Challenge each piece: "Does the agent really need this?" and "Does this justify its token cost?"

Prefer concise examples over verbose explanations.

## Skill Structure

```
skill-name/
├── SKILL.md              (required - the only required file)
├── references/           (optional - docs loaded on-demand)
├── scripts/              (optional - executable code)
└── assets/               (optional - templates, images, etc.)
```

### SKILL.md Format

```yaml
---
name: skill-name
description: What it does and WHEN to use it. This is the ONLY trigger mechanism.
---

# Skill Name

[Instructions for using the skill - loaded only AFTER skill triggers]
```

**Frontmatter rules:**
- `name` (required): hyphen-case, must match directory name
- `description` (required): what + when. This is ALL the agent sees for selection.
- Nothing else. No `license`, no `allowed-tools`, no `metadata`.

**Why minimal frontmatter?**
- The description is the ONLY thing that helps with skill selection
- Extra fields are noise that don't help selection decisions
- `allowed-tools` is for runtime permissions, not selection - skip it
- Weaker models get confused by extra frontmatter

### The Description is Everything

The description determines when your skill gets loaded. It must answer:
1. What does this skill do?
2. When should the agent use it?

**Good:**
```yaml
description: Create and execute commit plans using the commit-helper tool - use when managing commits across repositories
```

**Bad:**
```yaml
description: A skill for commits
```

### Progressive Disclosure

Three-level loading minimizes context bloat:

1. **Metadata** (~100 tokens) - Always in context (name + description only)
2. **SKILL.md body** (<5k tokens) - Loaded when skill triggers
3. **Bundled resources** (unlimited) - Loaded on-demand by agent

Keep SKILL.md under 500 lines. Split into references/ when approaching this limit.

## What to Include

### In SKILL.md Body

- Core workflow steps
- Decision points and branching logic
- References to bundled resources ("see references/foo.md for details")
- Concise examples (prefer over verbose explanations)

### In references/

- Detailed documentation
- Domain-specific knowledge
- API specs, schemas
- Variant-specific patterns (e.g., aws.md, gcp.md)

### In scripts/

- Deterministic operations that would be rewritten each time
- Complex transformations
- Validated, tested code

**Script execution guidance:**
- Use shebang lines (e.g., `#!/usr/bin/env python3`) so scripts can run directly
- Document required dependencies in the script's docstring
- If a specific interpreter is needed, document it in SKILL.md

### In assets/

- Templates
- Boilerplate code
- Images, fonts
- Files used in output (not loaded into context)

## What to NOT Include

**Never create these files:**
- README.md
- INSTALLATION_GUIDE.md
- QUICK_REFERENCE.md
- CHANGELOG.md
- Any "meta" documentation

The skill is for an agent, not a human. No auxiliary context about creation, setup, or testing.

## System Safety: Do Not Mutate

**Default behavior: Do NOT modify the system.**

Skills should NEVER encourage the agent to:
- Install packages with `pip install` (or npm, apt, brew, etc.)
- Modify system configuration
- Create files outside the project directory
- Run commands that require elevated privileges

**When scripts have dependencies:**

1. **Document them** - List required packages in the script docstring and SKILL.md
2. **Fail gracefully** - If dependencies are missing, report the error clearly
3. **Let the user decide** - Tell the user what's needed; don't auto-install

**Exceptions (when agent MAY install packages):**
- Agent has explicit custody of a project venv (e.g., `./local.venv/bin/python`)
- User has explicitly authorized package installation
- Project rules/guidelines grant this permission

**Example SKILL.md guidance for scripts with dependencies:**

```markdown
### If Dependencies Are Missing

If the script fails due to missing packages:
1. Report the error to the user
2. Tell the user what's needed: "This script requires X and Y"
3. Let the user decide how to install

Exception: If you have custody of a project venv and authorization
to install packages, you may install there.
```

## Skill Locations in Brynhild

Skills are discovered from (in priority order):

1. `~/.config/brynhild/skills/` - Global user skills
2. `$BRYNHILD_SKILL_PATH` - Custom paths (colon-separated)
3. `.brynhild/skills/` - Project-local skills (highest priority)

For project-specific skills, use `.brynhild/skills/`.
For personal/global skills, use `~/.config/brynhild/skills/`.

## Skill Creation Process

1. **Understand** - Get concrete examples of how the skill will be used
2. **Plan** - Identify what scripts, references, assets would help
3. **Create** - Make the directory and SKILL.md
4. **Test** - Use the skill on real tasks
5. **Iterate** - Refine based on actual usage

### Step 1: Understand

Ask clarifying questions:
- "What functionality should this skill support?"
- "Can you give examples of how it would be used?"
- "What would a user say that should trigger this skill?"

### Step 2: Plan

For each example, consider:
- What code gets rewritten each time? → scripts/
- What documentation would help? → references/
- What templates or assets are needed? → assets/

### Step 3: Create

```bash
mkdir -p .brynhild/skills/my-skill
# Create SKILL.md with minimal frontmatter
# Add references/, scripts/, assets/ as needed
```

### Step 4: Test

Use the skill in real scenarios. Note struggles or inefficiencies.

### Step 5: Iterate

Update SKILL.md and resources based on actual performance.

## Design Patterns

See `references/patterns.md` for:
- Sequential workflows
- Conditional workflows  
- Template patterns
- Example patterns
- Progressive disclosure patterns

