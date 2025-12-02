# Skill Design Patterns

## Sequential Workflows

Break complex tasks into clear steps:

```markdown
PDF form filling involves:

1. Analyze the form (run analyze_form.py)
2. Create field mapping (edit fields.json)
3. Validate mapping (run validate_fields.py)
4. Fill the form (run fill_form.py)
5. Verify output (check the result)
```

## Conditional Workflows

Guide through decision points:

```markdown
1. Determine the modification type:
   **Creating new content?** → Follow "Creation workflow"
   **Editing existing content?** → Follow "Editing workflow"

2. Creation workflow: [steps]
3. Editing workflow: [steps]
```

## Template Pattern

For consistent output format:

**Strict (API responses, data formats):**
```markdown
## Report structure

ALWAYS use this exact template:

# [Title]

## Executive summary
[One paragraph]

## Key findings
- Finding 1
- Finding 2

## Recommendations
1. Action 1
2. Action 2
```

**Flexible (when adaptation is useful):**
```markdown
## Report structure

Sensible default format, adjust as needed:

# [Title]
## Executive summary
## Key findings
## Recommendations

Adapt sections based on what you discover.
```

## Examples Pattern

When output quality depends on examples:

```markdown
## Commit message format

**Example 1:**
Input: Added user authentication with JWT tokens
Output:
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware

**Example 2:**
Input: Fixed bug where dates displayed incorrectly
Output:
fix(reports): correct date formatting in timezone conversion

Use UTC timestamps consistently across report generation
```

Examples > descriptions for teaching style and detail level.

## Progressive Disclosure Patterns

### High-level guide with references

```markdown
# PDF Processing

## Quick start
[code example]

## Advanced features
- **Form filling**: See references/forms.md
- **API reference**: See references/api.md
```

Agent loads forms.md or api.md only when needed.

### Domain-specific organization

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── references/
    ├── finance.md (revenue, billing)
    ├── sales.md (pipeline, opps)
    └── product.md (usage, features)
```

When user asks about sales, agent reads only sales.md.

### Variant-specific organization

```
cloud-deploy/
├── SKILL.md (workflow + selection logic)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

When user chooses AWS, agent reads only aws.md.

## Degrees of Freedom

Match specificity to task fragility:

**High freedom (text instructions):**
Use when multiple approaches are valid, decisions depend on context.

**Medium freedom (pseudocode, parameterized scripts):**
Use when a preferred pattern exists but variation is acceptable.

**Low freedom (specific scripts, few parameters):**
Use when operations are fragile, consistency is critical, or sequence matters.

Think of it as: narrow bridge with cliffs = guardrails (low freedom), open field = many routes (high freedom).

