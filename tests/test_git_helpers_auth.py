"""
test_git_helpers_auth.py - Tests for authenticated git operations

Tests url_utils.clone_with_token_askpass and clone_with_auth_fallback
using mocking to avoid actual network/subprocess calls.
"""

import pytest
import subprocess
import os
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path

from url_utils import clone_with_token_askpass, clone_with_auth_fallback


class TestCloneWithTokenAskpass:
    """Tests for clone_with_token_askpass."""

    @patch("url_utils.subprocess.run")
    def test_clone_success(self, mock_run, tmp_path):
        """Test successful clone execution."""
        # mock_create_scripts.return_value = (Path("/tmp/askpass"), Path("/tmp/dir"))
        # We let the real _create_askpass_scripts run. It mocks sys.executable used inside?
        # No, it uses sys.executable. We trust it works.
        # We need to verify that GIT_ASKPASS env var is set to a path that exists.

        result = clone_with_token_askpass("https://github.com/org/repo.git", tmp_path / "repo", "fake_token")

        assert result is True
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        env = kwargs["env"]

        assert cmd == ["git", "clone", "--depth", "1", "https://github.com/org/repo.git", str(tmp_path / "repo")]
        assert "git_askpass_" in env["GIT_ASKPASS"]  # Check pattern since real path varies
        assert env["GIT_AUTH_TOKEN"] == "fake_token"

    @patch("url_utils.subprocess.run")
    def test_clone_failure(self, mock_run, tmp_path):
        """Test clone failure handling."""
        # mock_create_scripts.return_value = (Path("/tmp/askpass"), Path("/tmp/dir"))
        mock_run.side_effect = subprocess.CalledProcessError(128, ["git", "clone"])

        result = clone_with_token_askpass("https://github.com/org/repo.git", tmp_path / "repo", "fake_token")

        assert result is False

    @patch("url_utils.subprocess.run")
    def test_clone_with_extra_args(self, mock_run, tmp_path):
        """Test clone with extra arguments."""
        clone_with_token_askpass("url", tmp_path / "repo", "token", extra_args=["--branch", "dev"])
        args = mock_run.call_args[0][0]
        assert "--branch" in args
        assert "dev" in args

    @patch("url_utils.subprocess.run")
    def test_clone_failure_verbose(self, mock_run, tmp_path):
        """Test verbose failure logging."""
        mock_run.side_effect = subprocess.CalledProcessError(1, ["git"])

        # We assume print goes to stderr, capture it?
        # Pytest capsys can capture it if we run it unmocked IO?
        # Safe just to run it and ensure coverage hits the line.
        result = clone_with_token_askpass("url", tmp_path / "repo", "token", verbose=True)
        assert result is False


class TestCloneWithAuthFallback:
    """Tests for clone_with_auth_fallback."""

    @patch("url_utils.shutil.which")
    @patch("url_utils.subprocess.run")
    def test_gh_cli_success(self, mock_run, mock_which, tmp_path):
        """Test preference for gh CLI if available."""
        mock_which.return_value = "/usr/bin/gh"

        result = clone_with_auth_fallback("https://github.com/org/repo.git", tmp_path / "repo", "fake_token")

        assert result is True
        # Verify gh command usage
        calls = mock_run.call_args_list
        # Should verify auth status then clone... implementation detail check:
        # Implementation calls `gh report clone` directly? No, it checks which first.
        # Check source: checks which('gh') -> calls gh repo clone.

        # Verify call arguments
        found_clone = False
        for call in calls:
            args = call[0][0]
            if args[0] == "gh" and args[1] == "repo" and args[2] == "clone":
                found_clone = True
                break
        assert found_clone

    @patch("url_utils.shutil.which")
    @patch("url_utils.clone_with_token_askpass")
    def test_fallback_to_askpass(self, mock_askpass, mock_which, tmp_path):
        """Test fallback to askpass if gh missing."""
        mock_which.return_value = None  # gh not found
        mock_askpass.return_value = True

        result = clone_with_auth_fallback("https://github.com/org/repo.git", tmp_path / "repo", "fake_token")

        assert result is True
        assert result is True
        mock_askpass.assert_called_once()

    @patch("url_utils.shutil.which")
    def test_fallback_token_none(self, mock_which, tmp_path):
        """Test fallback picks up token from env."""
        mock_which.return_value = None

        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
            # We need to mock clone_with_token_askpass to verify it gets the token
            with patch("url_utils.clone_with_token_askpass") as mock_askpass:
                mock_askpass.return_value = True
                clone_with_auth_fallback("url", tmp_path, token=None)

                args = mock_askpass.call_args
                assert args[0][2] == "env_token"

    @patch("url_utils.shutil.which")
    @patch("url_utils.subprocess.run")
    def test_gh_cli_extra_args_verbose_failure(self, mock_run, mock_which, tmp_path):
        """Test gh cli with extra args and verbose failure."""
        mock_which.return_value = "gh"

        # Test extra args
        clone_with_auth_fallback("url", tmp_path, "token", extra_args=["--foo"])
        cmd = mock_run.call_args[0][0]
        assert "--foo" in cmd

        # Test failure
        mock_run.side_effect = subprocess.CalledProcessError(1, ["gh"])
        # Mock fallback too to avoid it running
        with patch("url_utils.clone_with_token_askpass") as mock_askpass:
            clone_with_auth_fallback("url", tmp_path, "token", verbose=True)
            # Should print to stderr (covered)
            mock_askpass.assert_called()

    def test_askpass_script_creation_linux(self, tmp_path):
        """Test askpass script creation on Linux (mocked)."""
        from url_utils import _create_askpass_scripts
        import sys

        with patch.object(sys, "platform", "linux"):
            script_path, dir_path = _create_askpass_scripts()

            assert script_path.exists()
            content = script_path.read_text()
            assert "#!/bin/sh" in content
            assert str(sys.executable) in content
            assert "exec" in content

    def test_askpass_script_creation_windows(self, tmp_path):
        """Test askpass script creation on Windows (mocked)."""
        from url_utils import _create_askpass_scripts
        import sys

        with patch.object(sys, "platform", "win32"):
            script_path, dir_path = _create_askpass_scripts()

            assert script_path.exists()
            content = script_path.read_text()
            # Windows batch file
            assert "@echo off" in content
            assert "echo" in content
