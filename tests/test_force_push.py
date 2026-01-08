#!/usr/bin/env python3
"""
test_force_push.py

Tests for force-push detection - verifies history rewrite detection and recovery.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


# This test file proves the following claims:
DOC_CLAIMS = [
    "force_push_detected",
]


class TestForcePushDetection:
    """Tests that verify force-push/history rewrite is detected and handled."""

    def test_is_commit_reachable_returns_true_for_valid_commit(self, tmp_path):
        """is_commit_reachable should return True when commit exists."""
        from git_helpers import is_commit_reachable
        import subprocess

        # Create a real git repo with a commit
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)

        # Create a file and commit
        (repo_path / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, capture_output=True)

        # Get the commit SHA
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        commit_sha = result.stdout.strip()

        # Test that it's reachable
        assert is_commit_reachable(repo_path, commit_sha) is True

    def test_is_commit_reachable_returns_false_for_invalid_commit(self, tmp_path):
        """is_commit_reachable should return False for non-existent commit."""
        from git_helpers import is_commit_reachable
        import subprocess

        # Create a git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)

        # Create initial commit
        (repo_path / "test.txt").write_text("test")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, capture_output=True)

        # Test with a fake SHA that doesn't exist
        fake_sha = "abc123deadbeef456789abcdef0123456789abcd"
        assert is_commit_reachable(repo_path, fake_sha) is False

    def test_get_safe_diff_range_normal_history(self, tmp_path):
        """get_safe_diff_range should return 'normal' for clean linear history."""
        from git_helpers import get_safe_diff_range
        import subprocess

        # Create repo with two commits
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)

        # First commit
        (repo_path / "test.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "commit 1"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        commit1 = result.stdout.strip()

        # Second commit
        (repo_path / "test.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "commit 2"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        commit2 = result.stdout.strip()

        # Test normal range
        from_commit, to_commit, status = get_safe_diff_range(repo_path, commit1, commit2)

        assert status == "normal", f"Expected 'normal' status, got '{status}'"
        assert from_commit == commit1
        assert to_commit == commit2

    def test_get_safe_diff_range_reimport_required_for_gone_commit(self, tmp_path):
        """get_safe_diff_range should return 'reimport_required' when from_commit is gone."""
        from git_helpers import get_safe_diff_range, get_current_commit
        import subprocess

        # Create repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)

        # Create a commit
        (repo_path / "test.txt").write_text("current")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "current"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        current = result.stdout.strip()

        # Use a non-existent commit as from_commit (simulates force-push)
        gone_commit = "0000000000000000000000000000000000000000"

        from_commit, to_commit, status = get_safe_diff_range(repo_path, gone_commit, current)

        assert status == "reimport_required", f"Expected 'reimport_required', got '{status}'"

    def test_get_merge_base_finds_common_ancestor(self, tmp_path):
        """get_merge_base should find common ancestor of two commits."""
        from git_helpers import get_merge_base
        import subprocess

        # Create repo with branching history
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)

        # Base commit
        (repo_path / "base.txt").write_text("base")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        base_commit = result.stdout.strip()

        # Branch A
        subprocess.run(["git", "checkout", "-b", "branch-a"], cwd=repo_path, capture_output=True)
        (repo_path / "a.txt").write_text("a")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "branch a"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        commit_a = result.stdout.strip()

        # Branch B (from base)
        subprocess.run(["git", "checkout", base_commit], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "branch-b"], cwd=repo_path, capture_output=True)
        (repo_path / "b.txt").write_text("b")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "branch b"], cwd=repo_path, capture_output=True)
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        commit_b = result.stdout.strip()

        # Find merge base
        merge_base = get_merge_base(repo_path, commit_a, commit_b)

        assert merge_base == base_commit, (
            f"Merge base should be {base_commit[:8]}, got {merge_base[:8] if merge_base else None}"
        )
