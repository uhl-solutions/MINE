#!/usr/bin/env python3
"""
test_shared_coverage_gaps.py

Targeted tests to cover edge cases, error handlers, and platform-specific branches
in skills/_shared modules that are hard to reach with integration tests.
"""

import sys
import os
import re
import pytest
import subprocess
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add shared modules to path
SHARED_DIR = Path(__file__).resolve().parent.parent / "skills" / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import url_utils
import safe_io
import path_safety
import redaction


class TestUrlUtilsGaps:
    """Coverage for url_utils.py edge cases."""

    def test_redact_url_credentials_exception_fallback(self):
        with patch("url_utils.urlparse", side_effect=ValueError("Parse error")):
            url = "https://user:pass@example.com/repo.git"
            result = url_utils.redact_url_credentials(url)
            assert "***:***@" in result
            assert "pass" not in result

    def test_create_askpass_scripts_windows(self, tmp_path):
        with patch("sys.platform", "win32"):
            with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                wrapper, tmp_dir = url_utils._create_askpass_scripts()
                assert wrapper.suffix == ".cmd"
                content = (tmp_path / "askpass.cmd").read_text()
                assert "@echo off" in content
                assert "python" in content.lower() or "exe" in content.lower()

    def test_create_askpass_scripts_posix(self, tmp_path):
        with patch("sys.platform", "linux"):
            with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                with patch("os.chmod"):
                    wrapper, tmp_dir = url_utils._create_askpass_scripts()
                    assert wrapper.suffix == ".sh"
                    content = (tmp_path / "askpass.sh").read_text()
                    assert "#!/bin/sh" in content
                    assert "exec" in content

    def test_clone_with_token_askpass_error(self, tmp_path):
        with patch("url_utils._create_askpass_scripts", return_value=(Path("wrapper"), Path("tmp"))):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
                with patch("shutil.rmtree") as mock_rm:
                    result = url_utils.clone_with_token_askpass("url", tmp_path, "token")
                    assert result is False
                    mock_rm.assert_called()

    def test_clone_with_auth_fallback_git_failure(self, tmp_path):
        with patch("shutil.which", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
                with patch("url_utils.clone_with_token_askpass", return_value=False):
                    result = url_utils.clone_with_auth_fallback("url", tmp_path, "token")
                    assert result is False


class TestSafeIoGaps:
    """Coverage for safe_io.py edge cases."""

    def test_file_lock_unlock_exception(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        if sys.platform == "win32":
            import msvcrt

            with patch("os.name", "nt"):
                mock_locking = MagicMock()
                mock_locking.side_effect = [None, OSError("Unlock failed")]
                with patch("msvcrt.locking", mock_locking):
                    cm = safe_io.file_lock(lock_path)
                    cm.__enter__()
                    try:
                        cm.__exit__(None, None, None)
                    except Exception:
                        pass
        else:
            with patch.dict(sys.modules, {"fcntl": MagicMock()}):
                import fcntl

                with patch("os.name", "posix"):
                    cm = safe_io.file_lock(lock_path)
                    cm.__enter__()
                    fcntl.flock.side_effect = OSError("Unlock failed")
                    try:
                        cm.__exit__(None, None, None)
                    except Exception:
                        pass

    def test_fsync_dir_posix_full_coverage(self, tmp_path):
        """Test fsync_dir execution flow on POSIX."""
        # This covers the try..finally block in fsync_dir
        with patch("os.name", "posix"):
            with patch("os.open", return_value=123) as mock_open:
                with patch("os.fsync") as mock_fsync:
                    with patch("os.close") as mock_close:
                        safe_io._fsync_dir_if_possible(tmp_path)
                        mock_open.assert_called()
                        mock_fsync.assert_called()
                        mock_close.assert_called()

    def test_fsync_dir_posix_exception(self, tmp_path):
        """Test fsync_dir swallows exception on POSIX."""
        with patch("os.name", "posix"):
            with patch("os.open", side_effect=OSError("fail")):
                safe_io._fsync_dir_if_possible(tmp_path)

    def test_fsync_dir_windows_skip(self, tmp_path):
        with patch("os.name", "nt"):
            with patch("os.open") as mock_open:
                safe_io._fsync_dir_if_possible(tmp_path)
                mock_open.assert_not_called()

    def test_safe_load_json_oserror(self, tmp_path):
        """Test safe_load_json returns default on OSError loading file."""
        path = tmp_path / "test.json"
        path.touch()
        # Trigger OSError during open/read
        with patch("builtins.open", side_effect=OSError("Disk error")):
            result = safe_io.safe_load_json(path, default="DEFAULT")
            assert result == "DEFAULT"

    def test_safe_write_json_backup_failure(self, tmp_path):
        """Test failure during backup creation in safe_write_json."""
        path = tmp_path / "test.json"
        path.write_text("{}")

        # Mock shutil.copy2 to fail
        with patch("shutil.copy2", side_effect=OSError("Copy failed")):
            result = safe_io.safe_write_json(path, {"a": 1})
            assert result is True
            assert (tmp_path / "test.json").exists()  # Write succeeded despite backup failure

    def test_safe_write_json_cleanup_failure(self, tmp_path):
        """Test failure during temp file cleanup in safe_write_json error handler."""
        path = tmp_path / "test.json"

        # We need to trigger an error during write/replace (e.g. os.replace fails)
        # AND THEN trigger an error during tmp_path.unlink()

        with patch("os.replace", side_effect=OSError("Replace failed")):
            # Note: safe_write_json creates a tmp path with mkstemp.
            # We can't easily mock the Path object it creates unless we mock Path entirely or tempfile.
            # But the code does `tmp_path.unlink()`.
            # We can mock Path.unlink.

            with patch("pathlib.Path.unlink", side_effect=OSError("Unlink failed")):
                result = safe_io.safe_write_json(path, {"a": 1})
                assert result is False

    def test_safe_write_text_backup_failure(self, tmp_path):
        """Test failure during backup creation in safe_write_text."""
        path = tmp_path / "test.txt"
        path.write_text("content")

        with patch("shutil.copy2", side_effect=OSError("Copy failed")):
            result = safe_io.safe_write_text(path, "new content")
            assert result is True
            assert path.read_text() == "new content"

    def test_safe_write_text_cleanup_failure(self, tmp_path):
        """Test failure during temp file cleanup in safe_write_text error handler."""
        path = tmp_path / "test.txt"

        with patch("os.replace", side_effect=OSError("Replace failed")):
            with patch("pathlib.Path.unlink", side_effect=OSError("Unlink failed")):
                result = safe_io.safe_write_text(path, "content")
                assert result is False

    def test_is_valid_json_file_oserror(self, tmp_path):
        path = tmp_path / "exists.json"
        path.touch()
        with patch("builtins.open", side_effect=OSError("Read failed")):
            assert safe_io._is_valid_json_file(path) is False


class TestPathSafetyGaps:
    """Coverage for path_safety.py edge cases."""

    def test_is_safe_path_resolve_error(self, tmp_path):
        with patch("path_safety.resolve_path", side_effect=OSError("Disk error")):
            assert path_safety.is_safe_path("any", "root") is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows specific test logic")
    def test_path_case_insensitive_mismatch(self, tmp_path):
        root = tmp_path / "MixedCase"
        root.mkdir()
        path = tmp_path / "mixedCASE" / "file"
        with patch("path_safety.platform_utils.is_path_case_sensitive", return_value=False):
            assert path_safety.is_safe_path(str(path), str(root))

    def test_validate_path_symlink_check_fail(self, tmp_path):
        p = tmp_path / "test"
        with patch("pathlib.Path.is_symlink", side_effect=OSError("Perm denied")):
            with patch("path_safety.is_safe_path", return_value=True):
                path_safety.validate_path(p, tmp_path, allow_symlinks=False)


class TestRedactionGaps:
    """Coverage for redaction.py edge cases."""

    def test_redact_regex_error(self):
        content = "test content"
        real_findall = re.findall

        def side_effect(pattern, string, flags=0):
            if "sk-" in pattern:  # Raise on OpenAI pattern
                raise re.error("Bad regex")
            return real_findall(pattern, string, flags)

        with patch("re.findall", side_effect=side_effect):
            result = redaction.redact_secrets(content, verbose=True)
            assert result == content

    def test_contains_secrets_regex_error(self):
        """Test contains_secrets handling re.error."""
        content = "test content"

        # Mock re.search to raise error
        with patch("re.search", side_effect=re.error("Bad regex")):
            assert redaction.contains_secrets(content) is False
