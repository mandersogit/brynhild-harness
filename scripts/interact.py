#!/bin/bash
# -*- mode: python -*-
# vim: set ft=python:
# Polyglot bash/python script - bash delegates to venv python
"true" '''\'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
exec "$PROJECT_ROOT/local.venv/bin/python" "$0" "$@"
'''
import IPython
import brynhild
IPython.embed(colors="Linux")