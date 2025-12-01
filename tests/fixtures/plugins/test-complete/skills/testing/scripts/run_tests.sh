#!/bin/bash
# Helper script for running tests
# This demonstrates that skills can include helper scripts

echo "[TEST-PLUGIN-SKILL-SCRIPT] Running tests..."
./local.venv/bin/python -m pytest "$@"

