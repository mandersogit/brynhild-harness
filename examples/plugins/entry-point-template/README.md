# Brynhild Entry-Point Plugin Template

This is a complete template for creating pip-installable Brynhild plugins. It demonstrates all supported plugin features using the recommended entry-point approach.

## Quick Start

1. **Clone or copy this template**

   ```bash
   cp -r examples/plugins/entry-point-template my-plugin
   cd my-plugin
   ```

2. **Rename the package**

   - Rename `src/brynhild_my_plugin/` to `src/brynhild_YOUR_NAME/`
   - Update `pyproject.toml` with your package name
   - Update all imports

3. **Install in development mode**

   ```bash
   pip install -e .
   ```

4. **Verify installation**

   ```bash
   brynhild tools list  # Should show your tools
   brynhild plugins list  # Should show your plugin
   ```

## Plugin Features

This template demonstrates all supported plugin features:

| Feature    | Entry Point Group     | File                   | Description                    |
| ---------- | --------------------- | ---------------------- | ------------------------------ |
| Manifest   | `brynhild.plugins`    | `__init__.py`          | Plugin metadata                |
| Tools      | `brynhild.tools`      | `tools.py`             | Custom tools for the LLM       |
| Providers  | `brynhild.providers`  | `providers.py`         | Alternative LLM backends       |
| Hooks      | `brynhild.hooks`      | `hooks.py`             | Pre/post tool execution        |
| Skills     | `brynhild.skills`     | `skills.py`            | Behavioral guidance for LLM    |
| Commands   | `brynhild.commands`   | `commands.py`          | Custom slash commands          |
| Rules      | `brynhild.rules`      | `rules.py`             | Project-specific instructions  |

## Entry Point Requirements

### Important: Tools and Providers MUST be registered explicitly

For pip-installed plugins, Brynhild **cannot** scan directories to find tools and providers. You **must** register each one in `pyproject.toml`:

```toml
# ❌ WRONG - tools listed in manifest but not in entry points
# (Works for directory plugins but NOT for entry-point plugins)
[project.entry-points."brynhild.plugins"]
my-plugin = "brynhild_my_plugin:get_manifest"

# ✅ CORRECT - each tool registered individually
[project.entry-points."brynhild.plugins"]
my-plugin = "brynhild_my_plugin:get_manifest"

[project.entry-points."brynhild.tools"]
my-tool = "brynhild_my_plugin.tools:MyTool"
```

### Return Types

Each entry point must return the correct type:

| Group                | Must Return                          | Can Also Return                |
| -------------------- | ------------------------------------ | ------------------------------ |
| `brynhild.plugins`   | `PluginManifest` instance            | dict matching schema           |
| `brynhild.tools`     | `Tool` class (not instance!)         | -                              |
| `brynhild.providers` | `LLMProvider` class (not instance!)  | -                              |
| `brynhild.hooks`     | `HooksConfig` instance               | dict matching schema, callable |
| `brynhild.skills`    | `Skill` instance                     | dict matching schema, callable |
| `brynhild.commands`  | `Command` instance                   | dict matching schema, callable |
| `brynhild.rules`     | `str`                                | `list[str]`, callable          |

## File Structure

```
entry-point-template/
├── pyproject.toml                  # Package config with entry points
├── README.md                       # This file
└── src/
    └── brynhild_my_plugin/
        ├── __init__.py             # Manifest (brynhild.plugins)
        ├── tools.py                # Tools (brynhild.tools)
        ├── providers.py            # Providers (brynhild.providers)
        ├── hooks.py                # Hooks (brynhild.hooks)
        ├── skills.py               # Skills (brynhild.skills)
        ├── commands.py             # Commands (brynhild.commands)
        └── rules.py                # Rules (brynhild.rules)
```

## Debugging

If your plugin isn't working:

1. **Check installation**

   ```bash
   pip show brynhild-my-plugin
   ```

2. **Check entry points are registered**

   ```python
   from importlib.metadata import entry_points
   print(list(entry_points(group="brynhild.tools")))
   ```

3. **Test individual components**

   ```python
   from brynhild_my_plugin.tools import GreeterTool
   tool = GreeterTool()
   print(tool.name, tool.description)
   ```

4. **Check for import errors**

   ```bash
   python -c "from brynhild_my_plugin import get_manifest; print(get_manifest())"
   ```

## Testing

Create tests in `tests/` directory:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Publishing

1. Update version in `pyproject.toml`
2. Build: `python -m build`
3. Upload: `twine upload dist/*`

## See Also

- [Plugin Development Guide](../../../docs/plugin-development-guide.md)
- [Plugin Tool Interface](../../../docs/plugin-tool-interface.md)
- [Plugin API Reference](../../../docs/plugin-api-reference.md)

