# DeepChainMap Standalone Package Requirements

This document describes what would be needed to extract `DeepChainMap` as a standalone package, either as a top-level package within the brynhild monorepo or as an independent PyPI package.

## Current State

DeepChainMap is currently located at `brynhild.utils.deep_chain_map` and has:

- ✅ Zero external dependencies (stdlib only)
- ✅ Self-contained logic (no imports from other brynhild modules)
- ✅ Comprehensive test suite (297 tests, 99% coverage)
- ✅ Complete docstrings
- ❌ Absolute imports referencing `brynhild.utils.deep_chain_map`
- ❌ No package metadata (`pyproject.toml`, `__version__`)
- ❌ Tests import from `brynhild.utils`

## Requirements for Standalone Package

### 1. Convert Absolute Imports to Relative Imports

Current imports reference the full brynhild path:

```python
# _core.py - current
import brynhild.utils.deep_chain_map._frozen as _frozen
import brynhild.utils.deep_chain_map._operations as _operations

# _core.py - standalone
from . import _frozen
from . import _operations
```

Files requiring changes:

| File | Import to Change |
|------|------------------|
| `_core.py` | `brynhild.utils.deep_chain_map._frozen` → `._frozen` |
| `_core.py` | `brynhild.utils.deep_chain_map._operations` → `._operations` |
| `_proxy.py` | `brynhild.utils.deep_chain_map._frozen` → `._frozen` |
| `__init__.py` | `brynhild.utils.deep_chain_map._core` → `._core` |

### 2. Add Package Metadata

For PyPI distribution, add `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "deep-chain-map"
version = "1.0.0"
description = "ChainMap with deep merging and immutable semantics"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
keywords = ["chainmap", "config", "configuration", "merge", "layered"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Typing :: Typed",
]

[project.urls]
Homepage = "https://github.com/..."
Documentation = "https://..."
```

### 3. Add Version

In `__init__.py`:

```python
__version__ = "1.0.0"
__all__ = ["DeepChainMap"]
```

### 4. Create Standalone Test Suite

Tests currently import from `brynhild.utils`. For standalone:

```python
# Current
import brynhild.utils as utils
dcm = utils.DeepChainMap(...)

# Standalone
from deep_chain_map import DeepChainMap
dcm = DeepChainMap(...)
```

Options:
- A. Copy tests and update imports (duplication)
- B. Use import aliasing to support both
- C. Move tests with package, update brynhild to import from standalone

### 5. Expand Public API (Optional)

Consider exporting more for advanced users:

```python
__all__ = [
    "DeepChainMap",
    "FrozenMapping",
    "FrozenSequence",
]
```

### 6. Add README

Create `README.md` with:
- Installation instructions
- Quick start example
- Feature overview
- API documentation or link
- License

## Promotion Path

### Option A: Promote to `src/deep_chain_map/`

1. Move package to `src/deep_chain_map/`
2. Convert to relative imports
3. Update `brynhild.utils` to re-export: `from deep_chain_map import DeepChainMap`
4. Tests can import from either location

### Option B: Extract to Separate Repository

1. Create new repo `deep-chain-map`
2. Copy package with relative imports
3. Add `pyproject.toml`, README, LICENSE
4. Publish to PyPI
5. Add `deep-chain-map` as dependency in brynhild's requirements
6. Update brynhild imports

## Effort Estimate

| Task | Effort |
|------|--------|
| Convert imports | 15 min |
| Add `pyproject.toml` | 30 min |
| Add `__version__` | 5 min |
| Create README | 1 hour |
| Adapt tests | 1-2 hours |
| **Total** | **~3 hours** |

## Decision Record

*To be filled in when a decision is made.*

- **Date:** 
- **Decision:** 
- **Rationale:** 

