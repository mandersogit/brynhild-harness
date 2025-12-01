"""
Tests for sandbox utilities.

Tests path validation, sensitive path blocking, and Seatbelt profile generation.
"""

import os as _os
import pathlib as _pathlib
import tempfile as _tempfile

import pytest as _pytest

import brynhild.tools.sandbox as sandbox


class TestPathValidation:
    """Test path validation logic."""

    def test_allows_path_within_project(self, tmp_path: _pathlib.Path) -> None:
        """Writing to a path within the project root should be allowed."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        target = tmp_path / "subdir" / "file.txt"

        result = sandbox.validate_path(target, config, operation="write")

        assert result == target.resolve()

    def test_blocks_path_outside_project(self, tmp_path: _pathlib.Path) -> None:
        """Writing to a path outside the project root should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        # Use a path that's outside the allowed directories
        target = _pathlib.Path("/var/log/malicious.txt")

        with _pytest.raises(sandbox.PathValidationError) as exc_info:
            sandbox.validate_path(target, config, operation="write")

        # Should be blocked as protected location or outside allowed dirs
        error_msg = str(exc_info.value)
        assert "denied" in error_msg.lower()

    def test_allows_tmp_for_writes(self, tmp_path: _pathlib.Path) -> None:
        """Writing to /tmp should be allowed."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        target = _pathlib.Path("/tmp/brynhild_test.txt")

        # Should not raise - /tmp is always allowed
        result = sandbox.validate_path(target, config, operation="write")
        # On macOS, /tmp resolves to /private/tmp
        assert result == target.resolve()

    def test_allows_tempdir_for_writes(self, tmp_path: _pathlib.Path) -> None:
        """Writing to the system temp directory should be allowed."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        target = _pathlib.Path(_tempfile.gettempdir()) / "brynhild_test.txt"

        # Should not raise
        result = sandbox.validate_path(target, config, operation="write")
        assert result == target.resolve()

    def test_blocks_dotdot_traversal(self, tmp_path: _pathlib.Path) -> None:
        """Paths with .. that escape the project should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        # Try to escape via .. to user's home directory (outside temp)
        # Using ~ since temp is under /var/folders which is under the allowed temp paths
        home = _pathlib.Path.home()
        target = tmp_path / ".." / ".." / ".." / ".." / str(home.relative_to("/")) / "escape.txt"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(target, config, operation="write")

    def test_allows_additional_paths(self, tmp_path: _pathlib.Path) -> None:
        """Additional allowed paths should be writable."""
        extra_dir = tmp_path / "extra"
        extra_dir.mkdir()

        project = tmp_path / "project"
        project.mkdir()

        config = sandbox.SandboxConfig(
            project_root=project,
            allowed_paths=[extra_dir],
        )

        target = extra_dir / "file.txt"
        result = sandbox.validate_path(target, config, operation="write")
        assert result == target.resolve()

    def test_read_allowed_outside_project(self, tmp_path: _pathlib.Path) -> None:
        """Reading from outside the project should be allowed (if not sensitive)."""
        config = sandbox.SandboxConfig(project_root=tmp_path)

        # /etc/hosts should exist and be readable (not in sensitive read list)
        # We need a file that exists but isn't in the sensitive list
        # Use a file in the temp directory that we create
        test_file = tmp_path.parent / "readable_test.txt"
        test_file.write_text("test")

        try:
            # Should not raise for read operation on non-sensitive path
            result = sandbox.validate_path(test_file, config, operation="read")
            assert result == test_file.resolve()
        finally:
            test_file.unlink()


class TestSensitivePathBlocking:
    """Test blocking of sensitive paths."""

    def test_blocks_ssh_directory(self, tmp_path: _pathlib.Path) -> None:
        """~/.ssh should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        ssh_dir = _pathlib.Path.home() / ".ssh"

        with _pytest.raises(sandbox.PathValidationError) as exc_info:
            sandbox.validate_path(ssh_dir, config, operation="read")

        assert "sensitive" in str(exc_info.value).lower() or "protected" in str(
            exc_info.value
        ).lower()

    def test_blocks_aws_credentials(self, tmp_path: _pathlib.Path) -> None:
        """~/.aws should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        aws_dir = _pathlib.Path.home() / ".aws"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(aws_dir, config, operation="read")

    def test_blocks_zshrc(self, tmp_path: _pathlib.Path) -> None:
        """~/.zshrc should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        zshrc = _pathlib.Path.home() / ".zshrc"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(zshrc, config, operation="write")

    def test_blocks_launch_agents(self, tmp_path: _pathlib.Path) -> None:
        """~/Library/LaunchAgents should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        launch_agents = _pathlib.Path.home() / "Library" / "LaunchAgents"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(launch_agents, config, operation="write")

    def test_blocks_gnupg(self, tmp_path: _pathlib.Path) -> None:
        """~/.gnupg should be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        gnupg = _pathlib.Path.home() / ".gnupg"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(gnupg, config, operation="read")

    def test_blocks_subdirectory_of_sensitive_path(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Subdirectories of sensitive paths should also be blocked."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        target = _pathlib.Path.home() / ".ssh" / "id_rsa"

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(target, config, operation="read")


class TestSymlinkHandling:
    """Test handling of symbolic links."""

    def test_resolves_symlinks(self, tmp_path: _pathlib.Path) -> None:
        """Symlinks should be resolved before validation."""
        project = tmp_path / "project"
        project.mkdir()
        real_file = project / "real.txt"
        real_file.write_text("content")

        # Create symlink
        link = project / "link.txt"
        link.symlink_to(real_file)

        config = sandbox.SandboxConfig(project_root=project)

        result = sandbox.validate_path(link, config, operation="read")
        assert result == real_file

    def test_blocks_symlink_escape(self, tmp_path: _pathlib.Path) -> None:
        """Symlinks that point to sensitive paths should be blocked."""
        project = tmp_path / "project"
        project.mkdir()

        # Create symlink pointing to a sensitive path (that may or may not exist)
        link = project / "escape_ssh"
        ssh_dir = _pathlib.Path.home() / ".ssh"
        link.symlink_to(ssh_dir)

        config = sandbox.SandboxConfig(project_root=project)

        # Should be blocked because it resolves to ~/.ssh
        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path(link, config, operation="read")


class TestSeatbeltProfile:
    """Test Seatbelt profile generation."""

    def test_generates_valid_profile(self, tmp_path: _pathlib.Path) -> None:
        """Generated profile should be syntactically valid."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        profile = sandbox.generate_seatbelt_profile(config)

        # Basic structure checks
        assert "(version 1)" in profile
        assert "(deny default)" in profile
        assert "(allow file-read*)" in profile
        assert str(tmp_path) in profile

    def test_allows_project_writes(self, tmp_path: _pathlib.Path) -> None:
        """Profile should allow writes to project directory."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        profile = sandbox.generate_seatbelt_profile(config)

        assert f'(allow file-write* (subpath "{tmp_path}"))' in profile

    def test_allows_tmp_writes(self, tmp_path: _pathlib.Path) -> None:
        """Profile should allow writes to /tmp (or /private/tmp on macOS)."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        profile = sandbox.generate_seatbelt_profile(config)

        # On macOS, /tmp is a symlink to /private/tmp
        assert (
            '(allow file-write* (subpath "/tmp"))' in profile
            or '(allow file-write* (subpath "/private/tmp"))' in profile
        )

    def test_blocks_network_by_default(self, tmp_path: _pathlib.Path) -> None:
        """Profile should block network by default."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        profile = sandbox.generate_seatbelt_profile(config)

        assert "(deny network*)" in profile

    def test_allows_network_when_configured(self, tmp_path: _pathlib.Path) -> None:
        """Profile should allow network when configured."""
        config = sandbox.SandboxConfig(project_root=tmp_path, allow_network=True)
        profile = sandbox.generate_seatbelt_profile(config)

        assert "(allow network*)" in profile


class TestSandboxCommand:
    """Test sandbox command wrapping."""

    def test_wraps_command_with_sandbox(self, tmp_path: _pathlib.Path) -> None:
        """Command should be wrapped with platform-appropriate sandbox."""
        import platform as _platform

        config = sandbox.SandboxConfig(project_root=tmp_path)
        command = "echo hello"

        wrapped, profile_path = sandbox.get_sandbox_command(command, config)

        system = _platform.system()
        if system == "Darwin":
            assert "sandbox-exec" in wrapped
            assert "-f" in wrapped
            assert profile_path is not None
            assert profile_path.exists()
            sandbox.cleanup_sandbox_profile(profile_path)
        elif system == "Linux":
            assert "bwrap" in wrapped
            assert "--ro-bind" in wrapped
            # Linux doesn't use profile files
            assert profile_path is None
        else:
            # Unsupported platform - command returned unchanged
            assert wrapped == command

    def test_dry_run_mode(self, tmp_path: _pathlib.Path) -> None:
        """Dry run should not create profile."""
        config = sandbox.SandboxConfig(project_root=tmp_path, dry_run=True)
        command = "echo hello"

        wrapped, profile_path = sandbox.get_sandbox_command(command, config)

        assert "DRY RUN" in wrapped
        assert profile_path is None

    def test_escapes_single_quotes(self, tmp_path: _pathlib.Path) -> None:
        """Single quotes in commands should be properly escaped."""
        config = sandbox.SandboxConfig(project_root=tmp_path)
        command = "echo 'hello world'"

        wrapped, profile_path = sandbox.get_sandbox_command(command, config)

        # The command should be escaped
        assert "hello world" in wrapped

        sandbox.cleanup_sandbox_profile(profile_path)

    def test_profile_cleanup_macos(self, tmp_path: _pathlib.Path) -> None:
        """Profile cleanup should remove the file (macOS only)."""
        import platform as _platform

        if _platform.system() != "Darwin":
            _pytest.skip("macOS-only test: Seatbelt profiles")

        config = sandbox.SandboxConfig(project_root=tmp_path)
        command = "echo test"

        _, profile_path = sandbox.get_sandbox_command(command, config)
        assert profile_path is not None
        assert profile_path.exists()

        sandbox.cleanup_sandbox_profile(profile_path)
        assert not profile_path.exists()

    def test_skip_sandbox_flag(self, tmp_path: _pathlib.Path) -> None:
        """skip_sandbox should return command unchanged."""
        config = sandbox.SandboxConfig(project_root=tmp_path, skip_sandbox=True)
        command = "echo hello"

        wrapped, profile_path = sandbox.get_sandbox_command(command, config)

        assert wrapped == command
        assert profile_path is None


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""

    def test_check_write_path_valid(self, tmp_path: _pathlib.Path) -> None:
        """check_write_path should return resolved path for valid paths."""
        # Change to tmp_path so it becomes the project root
        original_cwd = _pathlib.Path.cwd()
        _os.chdir(tmp_path)
        try:
            target = tmp_path / "file.txt"
            result = sandbox.check_write_path(target)
            assert result == target.resolve()
        finally:
            _os.chdir(original_cwd)

    def test_check_write_path_invalid(self) -> None:
        """check_write_path should raise for invalid paths."""
        with _pytest.raises(sandbox.PathValidationError):
            sandbox.check_write_path(_pathlib.Path.home() / ".ssh" / "id_rsa")

    def test_check_read_path_blocks_sensitive(self) -> None:
        """check_read_path should block sensitive paths."""
        with _pytest.raises(sandbox.PathValidationError):
            sandbox.check_read_path(_pathlib.Path.home() / ".ssh")

    def test_is_path_safe_returns_bool(self, tmp_path: _pathlib.Path) -> None:
        """is_path_safe should return bool without raising."""
        config = sandbox.SandboxConfig(project_root=tmp_path)

        assert sandbox.is_path_safe(tmp_path / "file.txt", config, "write") is True
        assert (
            sandbox.is_path_safe(_pathlib.Path.home() / ".ssh", config, "read") is False
        )


class TestCustomBlockedPaths:
    """Test custom blocked path configuration."""

    def test_additional_blocked_paths(self, tmp_path: _pathlib.Path) -> None:
        """Custom blocked paths should be enforced for paths outside allowed dirs."""
        # Custom blocked path outside the project (e.g., another location on disk)
        # Since /opt exists on macOS but isn't in our default blocked list,
        # we can use it to test custom blocking
        config = sandbox.SandboxConfig(
            project_root=tmp_path,
            blocked_paths=["/opt/custom_secrets"],
        )

        with _pytest.raises(sandbox.PathValidationError):
            sandbox.validate_path("/opt/custom_secrets/key.txt", config, operation="read")


class TestSandboxUnavailableError:
    """Test sandbox failure modes."""

    def test_unsupported_platform_raises_error(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Unsupported platforms should raise SandboxUnavailableError."""
        import platform as _platform_module

        # Simulate an unsupported platform
        monkeypatch.setattr(_platform_module, "system", lambda: "Windows")

        config = sandbox.SandboxConfig(project_root=tmp_path)

        with _pytest.raises(sandbox.SandboxUnavailableError) as exc_info:
            sandbox.get_sandbox_command("echo test", config)

        error_msg = str(exc_info.value)
        assert "Windows" in error_msg
        assert "dangerously-skip-sandbox" in error_msg

    def test_unsupported_platform_with_skip_sandbox_works(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """skip_sandbox=True should work on unsupported platforms."""
        import platform as _platform_module

        monkeypatch.setattr(_platform_module, "system", lambda: "Windows")

        config = sandbox.SandboxConfig(project_root=tmp_path, skip_sandbox=True)
        command = "echo test"

        wrapped, profile_path = sandbox.get_sandbox_command(command, config)

        assert wrapped == command
        assert profile_path is None

    def test_macos_missing_sandbox_exec_raises_error(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Missing sandbox-exec on macOS should raise SandboxUnavailableError."""
        import platform as _platform_module
        import shutil as _shutil_module

        monkeypatch.setattr(_platform_module, "system", lambda: "Darwin")
        monkeypatch.setattr(_shutil_module, "which", lambda _: None)

        config = sandbox.SandboxConfig(project_root=tmp_path)

        with _pytest.raises(sandbox.SandboxUnavailableError) as exc_info:
            sandbox.get_sandbox_command("echo test", config)

        error_msg = str(exc_info.value)
        assert "sandbox-exec" in error_msg
        assert "dangerously-skip-sandbox" in error_msg

    def test_error_message_includes_override_instructions(
        self, tmp_path: _pathlib.Path, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Error messages should explain how to override."""
        import platform as _platform_module

        monkeypatch.setattr(_platform_module, "system", lambda: "FreeBSD")

        config = sandbox.SandboxConfig(project_root=tmp_path)

        with _pytest.raises(sandbox.SandboxUnavailableError) as exc_info:
            sandbox.get_sandbox_command("echo test", config)

        error_msg = str(exc_info.value)
        assert "--dangerously-skip-sandbox" in error_msg
        assert "BRYNHILD_DANGEROUSLY_SKIP_SANDBOX" in error_msg

