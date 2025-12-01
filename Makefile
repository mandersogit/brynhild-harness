# Brynhild Development Makefile
#
# Usage:
#   make test        - Run all tests
#   make test-fast   - Run tests excluding slow/integration
#   make test-cov    - Run tests with coverage report
#   make lint        - Run linter (ruff)
#   make typecheck   - Run type checker (mypy)
#   make format      - Format code (ruff + black)
#   make all         - Run lint, typecheck, and tests
#   make clean       - Remove build artifacts
#
# Note: All commands use the project's virtual environment explicitly.

PYTHON := ./local.venv/bin/python
PIP := ./local.venv/bin/pip

.PHONY: test test-fast test-integration test-system test-e2e test-live test-ollama test-cov lint typecheck format all clean help

# Default target
help:
	@echo "Brynhild Development Commands"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests (except live)"
	@echo "  make test-fast        Run unit tests only (fast)"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-system      Run system tests only"
	@echo "  make test-e2e         Run end-to-end tests only"
	@echo "  make test-live        Run live API tests (requires keys)"
	@echo "  make test-ollama      Run tests against local Ollama server"
	@echo "  make test-cov         Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint        Run ruff linter"
	@echo "  make typecheck   Run mypy type checker"
	@echo "  make format      Format code with ruff and black"
	@echo "  make all         Run lint, typecheck, and all tests"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean       Remove build artifacts and coverage reports"
	@echo "  make install     Install package in editable mode with dev deps"
	@echo ""

# Run all tests (excluding live API tests)
test:
	$(PYTHON) -m pytest tests/ -v -m "not live"

# Run only fast tests (exclude slow, integration, system, e2e, and live)
test-fast:
	$(PYTHON) -m pytest tests/ -v -m "not slow and not integration and not system and not e2e and not live"

# Run integration tests only
test-integration:
	$(PYTHON) -m pytest tests/ -v -m "integration"

# Run system tests only
test-system:
	$(PYTHON) -m pytest tests/ -v -m "system"

# Run end-to-end tests only
test-e2e:
	$(PYTHON) -m pytest tests/ -v -m "e2e"

# Run live API tests (requires API keys)
test-live:
	$(PYTHON) -m pytest tests/ -v -m "live"

# Run Ollama tests against local/private server (set BRYNHILD_OLLAMA_HOST in .env)
test-ollama:
	$(PYTHON) -m pytest tests/ -v -m "ollama_local"

# Run tests with coverage (excluding live API tests)
test-cov:
	$(PYTHON) -m pytest tests/ -v -m "not live" \
		--cov=src/brynhild \
		--cov-report=term-missing \
		--cov-report=html:coverage_html

# Run a specific test file or pattern
# Usage: make test-file FILE=tests/cli/test_main.py
test-file:
	$(PYTHON) -m pytest $(FILE) -v

# Lint with ruff
lint:
	$(PYTHON) -m ruff check src/ tests/

# Type check with mypy
typecheck:
	$(PYTHON) -m mypy src/ --ignore-missing-imports

# Format code
format:
	$(PYTHON) -m ruff check src/ tests/ --fix
	$(PYTHON) -m black src/ tests/

# Run all checks
all: lint typecheck test

# Install in development mode
install:
	$(PIP) install -e ".[dev]"

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf coverage_html/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
