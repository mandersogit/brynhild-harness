# Configuration Migration Guide

This guide helps you migrate from the legacy flat environment variables to the new nested configuration system.

## Overview

Brynhild now uses a layered YAML configuration system with nested structure. The old flat environment variables (`BRYNHILD_MODEL`, `BRYNHILD_PROVIDER`, etc.) are no longer supported.

**If you see an error like this:**

```
Configuration Error: Legacy environment variable detected.

Found: BRYNHILD_MODEL=anthropic/claude-sonnet-4

This variable is no longer supported. Please migrate to:
  export BRYNHILD_MODELS__DEFAULT="anthropic/claude-sonnet-4"

Or better, use a config file at ~/.config/brynhild/config.yaml
```

Follow this guide to update your configuration.

---

## Migration Table

| Old Variable | New Variable | Config File Path |
|-------------|--------------|------------------|
| `BRYNHILD_MODEL` | `BRYNHILD_MODELS__DEFAULT` | `models.default` |
| `BRYNHILD_PROVIDER` | `BRYNHILD_PROVIDERS__DEFAULT` | `providers.default` |
| `BRYNHILD_VERBOSE` | `BRYNHILD_BEHAVIOR__VERBOSE` | `behavior.verbose` |
| `BRYNHILD_MAX_TOKENS` | `BRYNHILD_BEHAVIOR__MAX_TOKENS` | `behavior.max_tokens` |

**Note:** The new environment variables use double underscores (`__`) to indicate nested structure.

---

## Option 1: Update Environment Variables

Simply rename your environment variables:

**Before:**
```bash
export BRYNHILD_MODEL="anthropic/claude-sonnet-4"
export BRYNHILD_PROVIDER="openrouter"
export BRYNHILD_VERBOSE="true"
```

**After:**
```bash
export BRYNHILD_MODELS__DEFAULT="anthropic/claude-sonnet-4"
export BRYNHILD_PROVIDERS__DEFAULT="openrouter"
export BRYNHILD_BEHAVIOR__VERBOSE="true"
```

---

## Option 2: Use a Config File (Recommended)

Create a YAML config file for cleaner, more maintainable configuration.

**Location:** `~/.config/brynhild/config.yaml`

```yaml
# User configuration
models:
  default: anthropic/claude-sonnet-4
  
providers:
  default: openrouter

behavior:
  verbose: true
  max_tokens: 16384
```

### Benefits of Config Files

- **Layered configuration:** Project configs override user configs
- **All options in one place:** Easier to manage than scattered env vars
- **Comments:** Document your choices
- **Inspect with CLI:** `brynhild config show --provenance`

---

## Configuration Precedence

Settings are loaded in this order (later sources override earlier):

1. **Built-in defaults** — Bundled with Brynhild
2. **User config** — `~/.config/brynhild/config.yaml`
3. **Project config** — `.brynhild/config.yaml` in project root
4. **Environment variables** — `BRYNHILD_*` with `__` for nesting
5. **CLI options** — `--model`, `--provider`, etc.

---

## Inspecting Your Configuration

Use the `config` command to see your effective settings:

```bash
# Show merged configuration
brynhild config show

# Show where each value comes from
brynhild config show --provenance

# Show specific section
brynhild config show --section models

# Show config file paths
brynhild config path
```

---

## API Key

The API key environment variable is unchanged:

```bash
export OPENROUTER_API_KEY="your-key-here"
```

---

## Common Issues

### "Legacy environment variable detected"

You have an old-style env var set. Either:
- Rename it using the migration table above
- Unset it: `unset BRYNHILD_MODEL`
- Use a config file instead

### Config file not found

Brynhild works without a config file (uses built-in defaults). Create one at `~/.config/brynhild/config.yaml` if you want to customize settings.

### Environment variable not working

Make sure you're using double underscores (`__`) for nested paths:
- ❌ `BRYNHILD_MODELS_DEFAULT` (single underscore)
- ✅ `BRYNHILD_MODELS__DEFAULT` (double underscore)

