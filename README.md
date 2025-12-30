# Brynhild

An AI coding assistant for the terminal.

> **Born**: November 28, 2025 in a three-day sprint  
> **First public release**: November 30, 2025  
> **Named after**: The Norse valkyrie and shieldmaiden

## Requirements

### All Platforms

- Python 3.11+
- `ripgrep` (`rg`) for code search

### Linux

- `bubblewrap` (`bwrap`) for sandbox protection

Verify dependencies are available:

```bash
which bwrap rg
```

If not installed, work with your system administrator or install to a local path (e.g., NFS-mounted tools directory) and ensure it's in your `PATH`.

**Ubuntu 24.04**: AppArmor restricts unprivileged user namespaces by default. To enable bubblewrap:

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

### macOS

```bash
brew install ripgrep
```

Sandbox uses built-in `sandbox-exec`.

## Installation

```bash
# Clone
git clone <repo-url>
cd brynhild

# Create venv
python3 -m venv local.venv

# Install
./local.venv/bin/pip install -e .

# Verify
./bin/brynhild --version
```

## Configuration

Set your API key:

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

### Option 1: Config File (Recommended)

Create `~/.config/brynhild/config.yaml`:

```yaml
models:
  default: anthropic/claude-sonnet-4

providers:
  default: openrouter

behavior:
  max_tokens: 16384
```

### Option 2: Environment Variables

```bash
export BRYNHILD_MODELS__DEFAULT="anthropic/claude-sonnet-4"
export BRYNHILD_PROVIDERS__DEFAULT="openrouter"    # openrouter | ollama
```

**Note:** Use double underscores (`__`) for nested settings.

### Inspect Configuration

```bash
brynhild config show              # Show effective settings
brynhild config show --provenance # Show where each value comes from
brynhild config path              # Show config file locations
```

See [docs/migration-guide.md](docs/migration-guide.md) for details.

## Usage

```bash
# Interactive mode
./bin/brynhild

# Single query
./bin/brynhild chat "explain this code"

# Show model thinking/reasoning (streams in real-time)
./bin/brynhild --show-thinking chat "solve this problem"

# Show config
./bin/brynhild config

# List tools
./bin/brynhild tools list
```

## Development

```bash
# Install dev dependencies
./local.venv/bin/pip install -e ".[dev]"

# Run tests
make test

# Type check
make typecheck

# Lint
make lint
```

## License

MIT
