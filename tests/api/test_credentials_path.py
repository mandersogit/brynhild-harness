"""Tests for credentials_path support in providers."""

import json as _json
import os as _os
import pathlib as _pathlib
import tempfile as _tempfile
import typing as _typing
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api.base as base
import brynhild.api.credentials as credentials
import brynhild.api.factory as factory
import brynhild.api.providers.openrouter.provider as openrouter_provider
import brynhild.api.providers.ollama.provider as ollama_provider


class TestOpenRouterCredentialsPath:
    """Tests for OpenRouter credentials_path support."""

    def test_credentials_path_loads_api_key(self, tmp_path: _pathlib.Path) -> None:
        """Provider should load api_key from credentials file."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text(_json.dumps({"api_key": "sk-or-test-from-file"}))

        provider = openrouter_provider.OpenRouterProvider(
            credentials_path=str(creds_file)
        )
        assert provider._api_key == "sk-or-test-from-file"

    def test_credentials_path_takes_precedence_over_api_key(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """credentials_path should take precedence over api_key parameter."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text(_json.dumps({"api_key": "sk-from-file"}))

        provider = openrouter_provider.OpenRouterProvider(
            api_key="sk-from-param",
            credentials_path=str(creds_file),
        )
        assert provider._api_key == "sk-from-file"

    def test_credentials_path_with_tilde_expansion(self) -> None:
        """credentials_path should expand ~ to home directory."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            # Create a credentials file in a temp location
            creds_content = {"api_key": "sk-or-tilde-test"}
            creds_file = _pathlib.Path(tmpdir) / "creds.json"
            creds_file.write_text(_json.dumps(creds_content))

            # Mock expanduser to return our temp dir for ~
            with _mock.patch.object(_os.path, "expanduser") as mock_expand:
                mock_expand.side_effect = lambda p: p.replace("~", tmpdir)

                provider = openrouter_provider.OpenRouterProvider(
                    credentials_path="~/creds.json"
                )
                assert provider._api_key == "sk-or-tilde-test"

    def test_credentials_path_with_env_var_expansion(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """credentials_path should expand environment variables."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text(_json.dumps({"api_key": "sk-or-envvar-test"}))

        with _mock.patch.dict(_os.environ, {"CREDS_DIR": str(tmp_path)}):
            provider = openrouter_provider.OpenRouterProvider(
                credentials_path="$CREDS_DIR/openrouter.json"
            )
            assert provider._api_key == "sk-or-envvar-test"

    def test_credentials_path_missing_file_raises(self) -> None:
        """Missing credentials file should raise ValueError."""
        with _pytest.raises(ValueError, match="Credentials file not found"):
            openrouter_provider.OpenRouterProvider(
                credentials_path="/nonexistent/path/creds.json"
            )

    def test_credentials_path_missing_api_key_raises(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Credentials file without api_key should raise ValueError."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text(_json.dumps({"other_field": "value"}))

        with _pytest.raises(ValueError, match="missing 'api_key' field"):
            openrouter_provider.OpenRouterProvider(credentials_path=str(creds_file))

    def test_credentials_path_invalid_json_raises(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Invalid JSON in credentials file should raise ValueError."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text("not valid json {")

        with _pytest.raises(ValueError, match="Invalid JSON"):
            openrouter_provider.OpenRouterProvider(credentials_path=str(creds_file))

    def test_credentials_path_permission_denied_raises(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Permission denied reading credentials should raise ValueError."""
        creds_file = tmp_path / "openrouter.json"
        creds_file.write_text(_json.dumps({"api_key": "sk-test"}))
        creds_file.chmod(0o000)  # Remove all permissions

        try:
            with _pytest.raises(ValueError, match="Permission denied"):
                openrouter_provider.OpenRouterProvider(credentials_path=str(creds_file))
        finally:
            # Restore permissions for cleanup
            creds_file.chmod(0o644)

    def test_api_key_from_env_var_when_no_credentials_path(self) -> None:
        """Without credentials_path, should fall back to env var."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "sk-from-env"}):
            provider = openrouter_provider.OpenRouterProvider()
            assert provider._api_key == "sk-from-env"


class TestOllamaCredentialsPath:
    """Tests for Ollama credentials_path support."""

    def test_credentials_path_loads_api_key(self, tmp_path: _pathlib.Path) -> None:
        """Provider should load api_key from credentials file."""
        creds_file = tmp_path / "ollama.json"
        creds_file.write_text(_json.dumps({"api_key": "ollama-test-key"}))

        provider = ollama_provider.OllamaProvider(credentials_path=str(creds_file))
        # Check that Authorization header was set
        assert "Authorization" in provider._client.headers
        assert provider._client.headers["Authorization"] == "Bearer ollama-test-key"

    def test_credentials_path_takes_precedence_over_api_key(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """credentials_path should take precedence over api_key parameter."""
        creds_file = tmp_path / "ollama.json"
        creds_file.write_text(_json.dumps({"api_key": "key-from-file"}))

        provider = ollama_provider.OllamaProvider(
            api_key="key-from-param",
            credentials_path=str(creds_file),
        )
        assert provider._client.headers["Authorization"] == "Bearer key-from-file"

    def test_no_auth_header_without_credentials(self) -> None:
        """Without credentials, no Authorization header should be set."""
        provider = ollama_provider.OllamaProvider()
        assert "Authorization" not in provider._client.headers

    def test_api_key_param_sets_auth_header(self) -> None:
        """api_key parameter should set Authorization header."""
        provider = ollama_provider.OllamaProvider(api_key="direct-key")
        assert provider._client.headers["Authorization"] == "Bearer direct-key"

    def test_credentials_path_with_env_var_expansion(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """credentials_path should expand environment variables."""
        creds_file = tmp_path / "ollama.json"
        creds_file.write_text(_json.dumps({"api_key": "ollama-envvar-test"}))

        with _mock.patch.dict(_os.environ, {"CREDS_DIR": str(tmp_path)}):
            provider = ollama_provider.OllamaProvider(
                credentials_path="$CREDS_DIR/ollama.json"
            )
            assert provider._client.headers["Authorization"] == "Bearer ollama-envvar-test"

    def test_credentials_without_api_key_no_auth_header(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Credentials file without api_key should not set auth header."""
        creds_file = tmp_path / "ollama.json"
        creds_file.write_text(_json.dumps({"host": "example.com"}))

        provider = ollama_provider.OllamaProvider(credentials_path=str(creds_file))
        assert "Authorization" not in provider._client.headers


class TestLoadCredentialsFromPath:
    """Tests for the load_credentials_from_path helper function."""

    def test_loads_valid_json(self, tmp_path: _pathlib.Path) -> None:
        """Should load valid JSON file."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(_json.dumps({"api_key": "test", "extra": "value"}))

        result = credentials.load_credentials_from_path(str(creds_file))
        assert result == {"api_key": "test", "extra": "value"}

    def test_expands_tilde(self) -> None:
        """Should expand ~ in path."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            creds_file = _pathlib.Path(tmpdir) / "creds.json"
            creds_file.write_text(_json.dumps({"key": "value"}))

            with _mock.patch.object(_os.path, "expanduser") as mock_expand:
                mock_expand.side_effect = lambda p: p.replace("~", tmpdir)

                result = credentials.load_credentials_from_path("~/creds.json")
                assert result == {"key": "value"}

    def test_expands_env_vars(self, tmp_path: _pathlib.Path) -> None:
        """Should expand environment variables in path."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(_json.dumps({"key": "value"}))

        with _mock.patch.dict(_os.environ, {"MY_PATH": str(tmp_path)}):
            result = credentials.load_credentials_from_path("${MY_PATH}/creds.json")
            assert result == {"key": "value"}

    def test_rejects_non_object_json(self, tmp_path: _pathlib.Path) -> None:
        """Should reject JSON that's not an object."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(_json.dumps(["array", "not", "object"]))

        with _pytest.raises(ValueError, match="must contain a JSON object"):
            credentials.load_credentials_from_path(str(creds_file))


class TestFactoryCredentialsPathExpansion:
    """Tests for factory-level credentials_path expansion."""

    def test_expand_credentials_path_class_var_exists(self) -> None:
        """LLMProvider base class should have expand_credentials_path class variable."""
        assert hasattr(base.LLMProvider, "expand_credentials_path")
        assert base.LLMProvider.expand_credentials_path is True

    def test_expand_credentials_path_helper_expands_tilde(self) -> None:
        """Factory helper should expand ~ in credentials_path."""
        instance_config: dict[str, _typing.Any] = {"credentials_path": "~/creds.json"}

        factory._expand_credentials_path(
            openrouter_provider.OpenRouterProvider, instance_config
        )

        # After expansion, ~ should be replaced with home dir
        expanded = instance_config["credentials_path"]
        assert not expanded.startswith("~")
        assert expanded.endswith("/creds.json")

    def test_expand_credentials_path_helper_expands_env_vars(self) -> None:
        """Factory helper should expand $VAR in credentials_path."""
        with _mock.patch.dict(_os.environ, {"MY_CREDS_DIR": "/path/to/creds"}):
            instance_config: dict[str, _typing.Any] = {
                "credentials_path": "$MY_CREDS_DIR/openrouter.json"
            }

            factory._expand_credentials_path(
                openrouter_provider.OpenRouterProvider, instance_config
            )

            assert instance_config["credentials_path"] == "/path/to/creds/openrouter.json"

    def test_expand_credentials_path_helper_respects_class_var_false(self) -> None:
        """Factory helper should not expand if expand_credentials_path is False."""

        class NoExpandProvider(base.LLMProvider):
            """Test provider that doesn't want expansion."""

            expand_credentials_path = False

            @property
            def name(self) -> str:
                return "no-expand"

            @property
            def model(self) -> str:
                return "test"

            def supports_tools(self) -> bool:
                return False

            async def complete(self, messages, **kwargs):  # type: ignore[override]
                raise NotImplementedError

            def stream(self, messages, **kwargs):  # type: ignore[override]
                raise NotImplementedError

        instance_config: dict[str, _typing.Any] = {"credentials_path": "~/creds.json"}

        factory._expand_credentials_path(NoExpandProvider, instance_config)

        # Should NOT be expanded
        assert instance_config["credentials_path"] == "~/creds.json"

    def test_expand_credentials_path_helper_no_op_when_missing(self) -> None:
        """Factory helper should do nothing if credentials_path not in config."""
        instance_config: dict[str, _typing.Any] = {"other_key": "value"}

        # Should not raise
        factory._expand_credentials_path(
            openrouter_provider.OpenRouterProvider, instance_config
        )

        assert instance_config == {"other_key": "value"}

