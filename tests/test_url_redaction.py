#!/usr/bin/env python3
"""
test_url_redaction.py - Tests for URL credential redaction

Tests the url_utils module's credential handling functions.
"""

import pytest
from url_utils import redact_url_credentials, sanitize_json_urls

DOC_CLAIMS = ["secrets_redacted"]


class TestRedactUrlCredentials:
    """Tests for redact_url_credentials function."""

    def test_redacts_username_password(self):
        """Redacts user:pass from URL."""
        url = "https://user:password123@github.com/org/repo.git"
        result = redact_url_credentials(url)

        assert "password123" not in result
        assert "user:" not in result
        assert "***:***@github.com" in result

    def test_redacts_token_in_url(self):
        """Redacts token from URL."""
        url = "https://ghp_token123456789@github.com/org/repo.git"
        result = redact_url_credentials(url)

        assert "ghp_token123456789" not in result
        assert "@github.com" in result

    def test_redacts_x_access_token(self):
        """Redacts x-access-token format."""
        url = "https://x-access-token:ghp_abc123@github.com/org/repo"
        result = redact_url_credentials(url)

        assert "ghp_abc123" not in result
        assert "x-access-token:" not in result

    def test_preserves_clean_url(self):
        """Preserves URLs without credentials."""
        url = "https://github.com/org/repo.git"
        result = redact_url_credentials(url)

        assert result == url

    def test_handles_ssh_url(self):
        """Handles SSH URLs gracefully."""
        url = "git@github.com:org/repo.git"
        result = redact_url_credentials(url)

        # SSH URLs don't have our target pattern, should pass through
        assert "git@github.com" in result or result == url

    def test_handles_empty_string(self):
        """Handles empty string."""
        result = redact_url_credentials("")
        assert result == ""

    def test_handles_invalid_url(self):
        """Handles malformed URLs gracefully."""
        result = redact_url_credentials("not-a-url")
        assert result == "not-a-url"


class TestSanitizeJsonUrls:
    """Tests for sanitize_json_urls function."""

    def test_sanitizes_source_url_field(self):
        """Sanitizes source_url field in dict."""
        data = {"repo_id": "org/repo", "source_url": "https://token@github.com/org/repo"}
        result = sanitize_json_urls(data)

        assert "token@" not in result["source_url"]
        assert "org/repo" in result["source_url"]

    def test_sanitizes_nested_urls(self):
        """Sanitizes URLs in nested structures."""
        data = {"integration": {"origin_url": "https://user:pass@github.com/x/y", "name": "test"}}
        result = sanitize_json_urls(data)

        assert "pass@" not in result["integration"]["origin_url"]

    def test_sanitizes_list_items(self):
        """Sanitizes URLs in lists."""
        data = {"endpoints": [{"url": "https://token@api.example.com"}, {"url": "https://clean.example.com"}]}
        result = sanitize_json_urls(data)

        assert "token@" not in result["endpoints"][0]["url"]
        assert result["endpoints"][1]["url"] == "https://clean.example.com"

    def test_preserves_non_url_fields(self):
        """Preserves fields that don't match URL patterns."""
        data = {"repo_id": "org/repo", "name": "my-project", "count": 42}
        result = sanitize_json_urls(data)

        assert result == data

    def test_handles_none_values(self):
        """Handles None values gracefully."""
        data = {"source_url": None, "name": "test"}
        result = sanitize_json_urls(data)

        assert result["source_url"] is None

    def test_full_provenance_sanitization(self):
        """Test full provenance-like structure."""
        provenance = {
            "version": "1.0",
            "repo_id": "user/repo",
            "source_url": "https://ghp_secret@github.com/user/repo",
            "import_time": "2024-01-01T00:00:00",
            "artifact_mappings": [
                {
                    "type": "skill",
                    "source_relpath": ".claude/skills/test",
                    "origin_url": "https://another:token@example.com",
                }
            ],
        }
        result = sanitize_json_urls(provenance)

        # Check credentials are removed
        assert "ghp_secret" not in str(result)
        assert "another:token" not in str(result)

        # Check structure preserved
        assert result["repo_id"] == "user/repo"
        assert len(result["artifact_mappings"]) == 1


class TestUrlRedactionCoverage:
    """Additional tests to reach 100% coverage."""

    def test_clone_cleanup_exception(self, tmp_path):
        """Test cleanup exception handling in clone_with_token_askpass."""
        from url_utils import clone_with_token_askpass
        from unittest.mock import patch

        # We need git to fail first to trigger finally block quickly?
        # Or succeed. Either way finally runs.
        # We want to force shutil.rmtree to raise OSError

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            with patch("shutil.rmtree", side_effect=OSError("Access denied")):
                # Should not raise exception
                result = clone_with_token_askpass("https://github.com/org/repo", tmp_path / "dest", "token")
                assert result is True
