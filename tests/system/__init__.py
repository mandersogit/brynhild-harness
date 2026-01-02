"""System tests for Brynhild.

System tests verify that multiple subsystems work together as a cohesive whole.
These tests exercise more complex scenarios than integration tests, involving
multiple components working in concert.

Test categories:
- test_tool_pipeline.py: Full tool execution pipeline (Tools + Sandbox + Hooks)
- test_hook_chain.py: Hook chain execution (Config + Hooks + Executors)
- test_session_lifecycle.py: Session lifecycle (Session + Hooks + Storage)
- test_config_cascade.py: Configuration priority cascade (CLI + Env + Config)
"""
