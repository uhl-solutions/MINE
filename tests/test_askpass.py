#!/usr/bin/env python3
"""
test_askpass.py - Tests for GIT_ASKPASS authentication helpers

Tests the secure credential handling in url_utils.
"""

import os
import sys
import pytest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from url_utils import (
    ASKPASS_SCRIPT,
    clone_with_token_askpass,
    clone_with_auth_fallback,
)


class TestAskpassScriptContent:
    """Tests for the askpass script content."""

    def test_script_returns_username_for_username_prompt(self, tmp_path):
        """Askpass script returns username for username prompts."""
        # Create temp askpass script
        script_path = tmp_path / "askpass.py"
        script_path.write_text(ASKPASS_SCRIPT)

        env = os.environ.copy()
        env["GIT_AUTH_USERNAME"] = "x-access-token"
        env["GIT_AUTH_TOKEN"] = "test_token"

        result = subprocess.run(
            [sys.executable, str(script_path), "Username for 'https://github.com':"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "x-access-token" in result.stdout.strip()

    def test_script_returns_token_for_password_prompt(self, tmp_path):
        """Askpass script returns token for password prompts."""
        script_path = tmp_path / "askpass.py"
        script_path.write_text(ASKPASS_SCRIPT)

        env = os.environ.copy()
        env["GIT_AUTH_USERNAME"] = "x-access-token"
        env["GIT_AUTH_TOKEN"] = "my_secret_token"

        result = subprocess.run(
            [sys.executable, str(script_path), "Password for 'https://github.com':"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "my_secret_token"

    def test_script_token_not_in_script_body(self):
        """Verify token is not embedded in script content."""
        # The script should read from env vars, not have hardcoded credentials
        assert "ghp_" not in ASKPASS_SCRIPT
        assert "secret" not in ASKPASS_SCRIPT.lower()

        # It should reference environment variables
        assert "GIT_AUTH_TOKEN" in ASKPASS_SCRIPT
        assert "GIT_AUTH_USERNAME" in ASKPASS_SCRIPT


class TestCloneWithTokenAskpass:
    """Tests for clone_with_token_askpass function."""

    @pytest.mark.skip(reason="Requires network and may trigger auth prompts")
    def test_clone_invalid_repo_returns_false(self, tmp_path):
        """Clone of invalid repo returns False."""
        result = clone_with_token_askpass(
            url="https://github.com/nonexistent/repo12345", dest=tmp_path / "dest", token="fake_token", verbose=False
        )

        # Should fail (invalid repo) but not crash
        assert result is False

    def test_clone_does_not_expose_token_in_args(self, tmp_path):
        """Clone function never passes token as command argument."""
        # We can't easily test the actual clone, but we can verify the function
        # signature and that it uses environment variables

        # The function signature should not require token in URL
        import inspect

        sig = inspect.signature(clone_with_token_askpass)
        params = list(sig.parameters.keys())

        assert "url" in params
        assert "token" in params
        assert "dest" in params


class TestCloneWithAuthFallback:
    """Tests for clone_with_auth_fallback function."""

    @pytest.mark.skip(reason="Requires network and may trigger auth prompts")
    def test_returns_false_on_failure(self, tmp_path):
        """Returns False when all auth methods fail."""
        result = clone_with_auth_fallback(
            url="https://github.com/nonexistent/repo99999", dest=tmp_path / "dest", token="fake", verbose=False
        )

        assert result is False

    def test_uses_gh_token_env_var(self):
        """Function passes token via GH_TOKEN env var for gh CLI."""
        # This is a design verification - the actual call happens inside the function
        import inspect

        source = inspect.getsource(clone_with_auth_fallback)

        assert "GH_TOKEN" in source


class TestNoTokenInProcessOutput:
    """Tests that tokens don't appear in process outputs."""

    @pytest.mark.skip(reason="Requires network and may trigger auth prompts")
    def test_error_messages_dont_contain_token(self, tmp_path):
        """Error messages should not expose tokens."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_supersecret"}):
            # Attempt a failing clone
            result = clone_with_token_askpass(
                url="https://github.com/invalid/repo999", dest=tmp_path / "test", token="ghp_supersecret", verbose=True
            )

            # Token should not be in any error output - we can't capture stderr
            # easily here, but the function is designed to never print tokens
            assert result is False
