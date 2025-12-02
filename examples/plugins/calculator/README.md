# Calculator Plugin

An example Brynhild plugin that provides a calculator tool for evaluating mathematical expressions.

## Features

- Basic arithmetic: `+`, `-`, `*`, `/`, `**`, `%`
- Mathematical functions: `sqrt`, `sin`, `cos`, `tan`, `log`, `exp`, `abs`
- Constants: `pi`, `e`
- Safe evaluation (no arbitrary code execution)

## Installation

### Option 1: Environment Variable

```bash
export BRYNHILD_PLUGIN_PATH="/path/to/brynhild/examples/plugins/calculator"
```

### Option 2: Symlink

```bash
ln -s /path/to/brynhild/examples/plugins/calculator ~/.brynhild/plugins/calculator
```

## Usage

Once installed, the `calculator` tool is available in Brynhild sessions:

```
User: What is the square root of 144?
Assistant: I'll calculate that for you.
[Tool: calculator, expression=sqrt(144)]
Result: 12.0

The square root of 144 is 12.
```

## Examples

| Expression | Result |
|------------|--------|
| `2 + 2` | `4` |
| `sqrt(16)` | `4.0` |
| `sin(pi/2)` | `1.0` |
| `2 ** 10` | `1024` |
| `abs(-5)` | `5` |
| `log(e)` | `1.0` |

## Testing

Run standalone tests (no Brynhild required):

```bash
cd examples/plugins/calculator
python -m pytest tests/ -v
```

## Files

- `plugin.yaml` - Plugin manifest
- `tools/calculator.py` - Calculator tool implementation
- `tests/test_calculator.py` - Unit tests
- `README.md` - This file

## See Also

- [Plugin Development Guide](../../../docs/plugin-development-guide.md)
- [Plugin Tool Interface](../../../docs/plugin-tool-interface.md)

