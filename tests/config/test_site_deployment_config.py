"""Tests for site and deployment config layers."""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.config.sources as sources


class TestSiteDeploymentConfigLayers:
    """Tests for BRYNHILD_SITE_CONFIG and BRYNHILD_DEPLOYMENT_CONFIG."""

    @_pytest.fixture
    def config_dirs(self, tmp_path: _pathlib.Path) -> dict[str, _pathlib.Path]:
        """Create temp directories for site and deployment config."""
        site_dir = tmp_path / "site"
        deployment_dir = tmp_path / "deployment"
        site_dir.mkdir()
        deployment_dir.mkdir()
        return {"site": site_dir, "deployment": deployment_dir}

    def test_site_config_loads(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Site config should be loaded when BRYNHILD_SITE_CONFIG is set."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("""
models:
  default: site-test-model
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
        }, clear=False):
            # Remove user config interference
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            assert "site" in layer_names, "Site layer should be loaded"

    def test_deployment_config_loads(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Deployment config should be loaded when BRYNHILD_DEPLOYMENT_CONFIG is set."""
        deployment_config = config_dirs["deployment"] / "deployment.yaml"
        deployment_config.write_text("""
models:
  default: deployment-test-model
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_DEPLOYMENT_CONFIG": str(deployment_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            assert "deployment" in layer_names, "Deployment layer should be loaded"

    def test_deployment_overrides_site(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Deployment config should override site config."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("""
models:
  default: site-model
""")

        deployment_config = config_dirs["deployment"] / "deployment.yaml"
        deployment_config.write_text("""
models:
  default: deployment-model
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(deployment_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            merged = source.dcm.to_dict()

            assert merged["models"]["default"] == "deployment-model"

    def test_site_values_merge_when_not_overridden(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Site config values should be present when not overridden by deployment."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("""
models:
  default: site-model
  aliases:
    site-unique-alias: some/model
""")

        deployment_config = config_dirs["deployment"] / "deployment.yaml"
        deployment_config.write_text("""
models:
  default: deployment-model
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(deployment_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            merged = source.dcm.to_dict()

            # Deployment overrides default
            assert merged["models"]["default"] == "deployment-model"
            # But site's unique alias is still present
            assert "site-unique-alias" in merged["models"]["aliases"]

    def test_provider_instances_merge(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Provider instances from both site and deployment should be available."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("""
providers:
  default: site-provider
  instances:
    site-provider:
      type: pais
      endpoint: https://site.example.com
""")

        deployment_config = config_dirs["deployment"] / "deployment.yaml"
        deployment_config.write_text("""
providers:
  default: deployment-provider
  instances:
    deployment-provider:
      type: vertex-ai
      project_id: my-project
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(deployment_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            merged = source.dcm.to_dict()

            # Deployment default wins
            assert merged["providers"]["default"] == "deployment-provider"

            # Both instances are available
            instances = merged["providers"]["instances"]
            assert "site-provider" in instances
            assert "deployment-provider" in instances
            assert instances["site-provider"]["type"] == "pais"
            assert instances["deployment-provider"]["type"] == "vertex-ai"

    def test_directory_path_uses_default_filename(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """When pointing to a directory, should use site.yaml or deployment.yaml."""
        # Create files with default names
        site_yaml = config_dirs["site"] / "site.yaml"
        site_yaml.write_text("""
models:
  default: site-from-dir
""")

        deployment_yaml = config_dirs["deployment"] / "deployment.yaml"
        deployment_yaml.write_text("""
models:
  default: deployment-from-dir
""")

        # Point to directories, not files
        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(config_dirs["site"]),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(config_dirs["deployment"]),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            merged = source.dcm.to_dict()

            # Should have loaded both
            assert merged["models"]["default"] == "deployment-from-dir"

    def test_layer_precedence_order(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Verify the complete precedence order: project > user > deployment > site > builtin."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("""
models:
  default: site-model
""")

        deployment_config = config_dirs["deployment"] / "deployment.yaml"
        deployment_config.write_text("""
models:
  default: deployment-model
""")

        user_config = tmp_path / "user.yaml"
        user_config.write_text("""
models:
  default: user-model
""")

        project_config = tmp_path / "project" / ".brynhild" / "config.yaml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text("""
models:
  default: project-model
""")

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(deployment_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                project_root=tmp_path / "project",
                user_config_path=user_config,
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            # Verify order (highest precedence first)
            expected_order = ["project", "user", "deployment", "site", "built-in"]
            assert layer_names == expected_order

            # Verify project wins
            merged = source.dcm.to_dict()
            assert merged["models"]["default"] == "project-model"

    def test_missing_configs_are_skipped(self, tmp_path: _pathlib.Path) -> None:
        """Missing site/deployment configs should be skipped without error."""
        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(tmp_path / "nonexistent-site.yaml"),
            "BRYNHILD_DEPLOYMENT_CONFIG": str(tmp_path / "nonexistent-deployment.yaml"),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            # Only built-in should be present
            assert layer_names == ["built-in"]

    def test_env_var_constants_defined(self) -> None:
        """Environment variable constants should be defined."""
        assert hasattr(sources, "ENV_SITE_CONFIG")
        assert hasattr(sources, "ENV_DEPLOYMENT_CONFIG")
        assert sources.ENV_SITE_CONFIG == "BRYNHILD_SITE_CONFIG"
        assert sources.ENV_DEPLOYMENT_CONFIG == "BRYNHILD_DEPLOYMENT_CONFIG"

    def test_path_expansion_tilde(self, tmp_path: _pathlib.Path) -> None:
        """Paths with ~ should be expanded."""
        # Create a config file in a "fake home" directory
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        site_config = fake_home / "site.yaml"
        site_config.write_text("""
models:
  default: tilde-expanded-model
""")

        # Mock expanduser to expand ~ to our fake home
        def mock_expanduser(path: str) -> str:
            return path.replace("~", str(fake_home))

        with (
            _mock.patch("os.path.expanduser", side_effect=mock_expanduser),
            _mock.patch.dict(_os.environ, {
                "BRYNHILD_SITE_CONFIG": "~/site.yaml",
            }, clear=False),
        ):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            assert "site" in layer_names, "Site config with ~ path should be loaded"
            merged = source.dcm.to_dict()
            assert merged["models"]["default"] == "tilde-expanded-model"

    def test_path_expansion_env_var(self, tmp_path: _pathlib.Path) -> None:
        """Paths with $VAR should be expanded."""
        deployment_config = tmp_path / "deployment.yaml"
        deployment_config.write_text("""
models:
  default: envvar-expanded-model
""")

        with _mock.patch.dict(_os.environ, {
            "MY_CONFIG_DIR": str(tmp_path),
            "BRYNHILD_DEPLOYMENT_CONFIG": "$MY_CONFIG_DIR/deployment.yaml",
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            assert "deployment" in layer_names, "Deployment config with $VAR should load"
            merged = source.dcm.to_dict()
            assert merged["models"]["default"] == "envvar-expanded-model"

    def test_empty_config_file_skipped(
        self, config_dirs: dict[str, _pathlib.Path], tmp_path: _pathlib.Path
    ) -> None:
        """Empty config files should be silently skipped."""
        site_config = config_dirs["site"] / "site.yaml"
        site_config.write_text("")  # Empty file

        with _mock.patch.dict(_os.environ, {
            "BRYNHILD_SITE_CONFIG": str(site_config),
        }, clear=False):
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                user_config_path=tmp_path / "nonexistent-user.yaml",
            )
            layers = source.get_loaded_layers()
            layer_names = [name for name, _ in layers]

            # Empty file should not appear in layers
            assert "site" not in layer_names

