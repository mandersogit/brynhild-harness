"""
Live API tests for Brynhild.

These tests make actual API calls to LLM providers and require:
- Valid API keys (OPENROUTER_API_KEY environment variable)
- Network access

All tests are marked with @pytest.mark.live and excluded from default test runs.
Run with: make test-live or pytest -m live
"""

