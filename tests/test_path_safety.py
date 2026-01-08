#!/usr/bin/env python3
"""
test_path_safety.py

Tests for path_safety module - verifies path traversal protection.
"""

import sys
import os
from pathlib import Path
import pytest


from path_safety import validate_path, is_safe_path, PathSafetyError

# This test file proves the following claims:
DOC_CLAIMS = [
    "path_safety_traversal_blocked",
]


class TestPathSafetyTraversalBlocked:
    """Tests that verify paths containing '../' are rejected."""

    def test_traversal_blocked_with_dotdot_in_path(self, tmp_path):
        """Path with '../' should raise PathSafetyError."""
        root = tmp_path / "root"
        root.mkdir()

        # Path that tries to escape root via ../
        bad_path = root / "subdir" / ".." / ".." / "outside"

        with pytest.raises(PathSafetyError) as exc_info:
            validate_path(bad_path, root)

        assert "traversal" in str(exc_info.value).lower()

    def test_traversal_blocked_with_dotdot_string(self, tmp_path):
        """String path with '..' component should be blocked."""
        root = tmp_path / "root"
        root.mkdir()

        # String path with traversal
        bad_path = str(root / "foo" / ".." / ".." / "bar")

        with pytest.raises(PathSafetyError):
            validate_path(bad_path, root)

    def test_is_safe_path_returns_false_for_escaped_path(self, tmp_path):
        """is_safe_path should return False for paths escaping root."""
        root = tmp_path / "safe_root"
        root.mkdir()

        outside = tmp_path / "outside_root"
        outside.mkdir()

        assert not is_safe_path(outside, root)

    def test_valid_path_accepted(self, tmp_path):
        """Valid path within root should be accepted."""
        root = tmp_path / "root"
        root.mkdir()

        good_path = root / "subdir" / "file.txt"
        good_path.parent.mkdir(parents=True, exist_ok=True)
        good_path.touch()

        # Should not raise
        result = validate_path(good_path, root)
        assert result is not None

    def test_is_safe_path_returns_true_for_contained_path(self, tmp_path):
        """is_safe_path should return True for paths inside root."""
        root = tmp_path / "root"
        root.mkdir()

        inside = root / "subdir" / "file.txt"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.touch()

        assert is_safe_path(inside, root)


class TestPathSafetyScopeEnforced:
    """Tests that verify paths outside scope root are rejected."""

    def test_path_outside_root_rejected(self, tmp_path):
        """Absolute path outside root should fail."""
        root = tmp_path / "allowed"
        root.mkdir()

        forbidden = tmp_path / "forbidden" / "secret.txt"
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.touch()

        with pytest.raises(PathSafetyError):
            validate_path(forbidden, root)

    def test_sibling_directory_rejected(self, tmp_path):
        """Sibling directory should not be accessible from root."""
        root = tmp_path / "project"
        root.mkdir()

        sibling = tmp_path / "other_project"
        sibling.mkdir()

        with pytest.raises(PathSafetyError):
            validate_path(sibling, root)


class TestPathSafetyEdgeCases:
    """Extra edge cases for coverage."""

    def test_root_is_safe(self, tmp_path):
        """The root itself is a safe path."""
        assert is_safe_path(tmp_path, tmp_path)

    def test_symlink_traversal(self, tmp_path):
        """Symlinks pointing outside root should be unsafe (if resolution enforced)."""
        # Note: validate_path usually resolves symlinks.
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        link = root / "link_to_outside"
        try:
            os.symlink(outside, link)
            # Depending on implementation of validate_path, it might resolve or not.
            # safe_io checks usually resolve.
            # Let's check is_safe_path valid logic
            # is_safe_path(path, root) -> path.resolve().relative_to(root.resolve())
            assert not is_safe_path(link, root)
        except OSError:
            # Skip on windows if no symlink privs
            pass

    def test_ensure_directory_safety(self, tmp_path):
        """Test wrapper function."""
        from path_safety import ensure_directory_safety, is_safe_path

        root = tmp_path / "root"
        root.mkdir()
        ensure_directory_safety(root, root)  # Should pass

        with pytest.raises(PathSafetyError):
            ensure_directory_safety(tmp_path / "outside", root)

    def test_case_insensitive_path_validation(self, tmp_path):
        """Test validation on case-insensitive paths (simulated or real)."""
        root = tmp_path / "RootDir"
        root.mkdir()

        # Valid path with different case
        child = root / "ChildDir"
        child.mkdir()

        # Should pass if platform is case-insensitive (Windows) OR if we rely on pathlib resolution
        # On Windows, resolve() normalizes case? actually depends.
        # But validate_path handles it.

        # Test explicit logic via is_safe_path
        # We can construct paths that look different.

        path_str = str(root) + "\\ChildDir"
        root_str = str(root).lower()

        # If we are on Windows, this should pass
        if sys.platform == "win32":
            assert is_safe_path(path_str, root_str)
            assert is_safe_path(root_str, path_str) is False  # reversed


class TestSymlinkHandling:
    """Tests for allow_symlinks parameter enforcement."""

    def test_symlink_rejected_by_default(self, tmp_path):
        """Symlinks are rejected when allow_symlinks=False (default)."""
        root = tmp_path / "root"
        root.mkdir()
        target = root / "actual_file.txt"
        target.touch()
        link = root / "link_to_file"

        try:
            os.symlink(target, link)
            with pytest.raises(PathSafetyError) as exc_info:
                validate_path(link, root, allow_symlinks=False)
            assert "symlink" in str(exc_info.value).lower()
        except OSError:
            pytest.skip("Symlinks not supported on this system")

    def test_symlink_allowed_when_flag_true(self, tmp_path):
        """Symlinks are allowed when allow_symlinks=True."""
        root = tmp_path / "root"
        root.mkdir()
        target = root / "actual_file.txt"
        target.touch()
        link = root / "link_to_file"

        try:
            os.symlink(target, link)
            # Should not raise
            result = validate_path(link, root, allow_symlinks=True)
            assert result is not None
        except OSError:
            pytest.skip("Symlinks not supported on this system")

    def test_symlink_to_outside_rejected_even_with_flag(self, tmp_path):
        """Symlinks pointing outside root are rejected even with allow_symlinks=True."""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        outside_file = outside / "secret.txt"
        outside_file.touch()

        link = root / "escape_link"

        try:
            os.symlink(outside_file, link)
            # Even with allow_symlinks=True, the resolved path is outside root
            # is_safe_path resolves symlinks and checks containment
            with pytest.raises(PathSafetyError):
                validate_path(link, root, allow_symlinks=True)
        except OSError:
            pytest.skip("Symlinks not supported on this system")

    def test_non_symlink_path_unaffected(self, tmp_path):
        """Regular files work regardless of allow_symlinks setting."""
        root = tmp_path / "root"
        root.mkdir()
        regular_file = root / "normal.txt"
        regular_file.touch()

        # Should work with allow_symlinks=False (default)
        result1 = validate_path(regular_file, root, allow_symlinks=False)
        assert result1 is not None

        # Should also work with allow_symlinks=True
        result2 = validate_path(regular_file, root, allow_symlinks=True)
        assert result2 is not None

    def test_directory_symlink_rejected(self, tmp_path):
        """Directory symlinks are also rejected when allow_symlinks=False."""
        root = tmp_path / "root"
        root.mkdir()
        target_dir = root / "actual_dir"
        target_dir.mkdir()
        link = root / "link_to_dir"

        try:
            os.symlink(target_dir, link, target_is_directory=True)
            with pytest.raises(PathSafetyError) as exc_info:
                validate_path(link, root, allow_symlinks=False)
            assert "symlink" in str(exc_info.value).lower()
        except OSError:
            pytest.skip("Symlinks not supported on this system")


class TestPathSafetyCoverage:
    """Additional tests to reach 100% coverage."""

    def test_is_safe_path_resolve_error(self, tmp_path):
        """Test is_safe_path returns False when resolve raises OSError."""
        from unittest.mock import patch

        root = tmp_path / "root"
        root.mkdir()

        # Mock resolve_path to raise OSError
        with patch("path_safety.resolve_path", side_effect=OSError("Disk error")):
            assert is_safe_path("some/path", root) is False

    def test_path_case_insensitive_mismatch(self, tmp_path):
        """Test case-insensitive fallback logic returns True for matching paths."""
        from unittest.mock import patch, MagicMock

        root = tmp_path / "Root"
        root.mkdir()
        file_path = root / "File.txt"
        file_path.touch()

        # We need to force Value Error on relative_to but succeed on case check
        # Mock platform_utils.is_path_case_sensitive to return False
        with patch("platform_utils.is_path_case_sensitive", return_value=False):
            # We mock the Path objects to fail relative_to but pass parts check
            mock_root = MagicMock()
            mock_root.parts = ("C:", "Root")
            mock_root.resolve.return_value = mock_root

            mock_path = MagicMock()
            mock_path.parts = ("C:", "Root", "File.txt")
            mock_path.relative_to.side_effect = ValueError("Case mismatch")
            mock_path.resolve.return_value = mock_path

            # We need to patch Path constructor or resolve_path helper
            with patch("path_safety.resolve_path") as mock_resolve:
                mock_resolve.side_effect = [mock_path, mock_root]

                # Should return True because parts match case-insensitively
                # And we patched it to assume case-insensitive filesystem
                assert is_safe_path(file_path, root) is True

    def test_validate_path_symlink_check_fail(self, tmp_path):
        """Test validate_path continues if symlink check raises OSError."""
        from unittest.mock import patch, PropertyMock

        root = tmp_path / "root"
        root.mkdir()
        path = root / "test.txt"
        path.touch()

        # Mock is_symlink to raise OSError
        # This simulates "pass" block in validate_path
        with patch("pathlib.Path.is_symlink", side_effect=OSError("Access denied")):
            # Should not raise exception
            result = validate_path(path, root)
            assert result == path.resolve()
