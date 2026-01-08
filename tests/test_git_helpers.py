"""
test_git_helpers.py - Tests for git helper utilities

Tests clone functionality using local repos (no network required),
security properties (no tokens in config), and file hashing.
"""

import pytest
import subprocess
import sys
import os
from pathlib import Path

from git_helpers import clone_repo, get_current_commit
from hash_helpers import hash_file


@pytest.fixture
def local_git_repo(tmp_path):
    """Create a local git repository for testing (no network required)."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)

    # Create a test file and commit
    test_file = repo_path / "README.md"
    test_file.write_text("# Test Repository\n\nThis is test content.\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    return repo_path


class TestCloneFromLocalRepo:
    """Test clone functionality using local repos (no network)."""

    def test_clone_local_repo_file_url(self, local_git_repo, tmp_path):
        """Clone from file:// URL works."""
        dest = tmp_path / "cloned"

        # Use file:// URL for local clone
        result = clone_repo(f"file://{local_git_repo}", dest)

        assert result is True
        assert (dest / "README.md").exists()
        assert (dest / ".git").exists()

    def test_cloned_repo_content_matches(self, local_git_repo, tmp_path):
        """Cloned repo has identical content."""
        dest = tmp_path / "cloned"
        clone_repo(f"file://{local_git_repo}", dest)

        original_content = (local_git_repo / "README.md").read_text()
        cloned_content = (dest / "README.md").read_text()

        assert cloned_content == original_content


class TestGitHelpersSecurity:
    """Security-focused tests for git helpers."""

    def test_no_token_in_git_config(self, local_git_repo, tmp_path, monkeypatch):
        """Ensure tokens don't persist in .git/config after clone."""
        dest = tmp_path / "cloned"

        # Set a fake token in environment
        fake_token = "ghp_TestTokenThatShouldNeverPersist123"
        monkeypatch.setenv("GITHUB_TOKEN", fake_token)

        # Clone (the token is read from env internally)
        clone_repo(f"file://{local_git_repo}", dest)

        # Read .git/config
        git_config = (dest / ".git" / "config").read_text()

        # Should not contain any token-like patterns
        assert fake_token not in git_config
        assert "ghp_" not in git_config
        assert "x-access-token" not in git_config.lower()
        assert "bearer" not in git_config.lower()

    def test_cloned_repo_has_clean_remote(self, local_git_repo, tmp_path):
        """Verify cloned repo remote URL does not contain credentials."""
        dest = tmp_path / "cloned"
        clone_repo(f"file://{local_git_repo}", dest)

        # Get remote URL
        result = subprocess.run(["git", "-C", str(dest), "remote", "-v"], capture_output=True, text=True)

        # Remote URL should not contain @ (credential marker) unless file://
        output = result.stdout
        for line in output.strip().split("\n"):
            if line and "file://" not in line:
                # For non-file URLs, should not have credentials
                parts = line.split()
                if len(parts) >= 2:
                    url = parts[1]
                    assert "@" not in url or url.startswith("file://"), f"Remote URL may contain credentials: {url}"


class TestGetCurrentCommit:
    """Test commit retrieval functionality."""

    def test_get_commit_from_repo(self, local_git_repo):
        """Get current commit hash from repository."""
        commit = get_current_commit(local_git_repo)

        assert commit is not None
        assert len(commit) == 40  # Full SHA-1 hash
        assert all(c in "0123456789abcdef" for c in commit)

    def test_get_commit_nonexistent_repo(self, tmp_path):
        """Get commit from non-git directory returns None."""
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()

        commit = get_current_commit(non_repo)
        assert commit is None


class TestHashFile:
    """Test file hashing utility."""

    def test_hash_file_deterministic(self, tmp_path):
        """Same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("test content")
        file2.write_text("test content")

        assert hash_file(file1) == hash_file(file2)

    def test_hash_file_different_content(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("content A")
        file2.write_text("content B")

        assert hash_file(file1) != hash_file(file2)

    def test_hash_file_empty(self, tmp_path):
        """Empty file has consistent hash."""
        empty1 = tmp_path / "empty1.txt"
        empty2 = tmp_path / "empty2.txt"

        empty1.write_text("")
        empty2.write_text("")

        hash1 = hash_file(empty1)
        hash2 = hash_file(empty2)

        assert hash1 == hash2
        assert hash1 is not None

    def test_hash_file_binary(self, tmp_path):
        """Binary file hashing works."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")

        result = hash_file(binary_file)

        assert result is not None
        assert len(result) > 0


class TestCloneWithBranch:
    """Test cloning with specific git refs."""

    def test_clone_default_branch(self, local_git_repo, tmp_path):
        """Clone without specifying branch uses default."""
        dest = tmp_path / "cloned"

        result = clone_repo(f"file://{local_git_repo}", dest)

        assert result is True
        assert (dest / "README.md").exists()
