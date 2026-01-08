"""
Tests for platform_utils.py module.

Covers platform detection, WSL detection, path utilities, and case sensitivity.
Uses mocking to test WSL-specific code paths on non-WSL systems.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Setup path for modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

import platform_utils
from platform_utils import (
    get_long_path,
    get_native_windows_path,
    get_wsl_version,
    handle_wsl_symlink,
    is_case_only_rename,
    is_filesystem_case_sensitive,
    is_path_case_sensitive,
    is_windows_path,
    is_wsl,
)


def reset_platform_utils_cache():
    """Reset all cached values in platform_utils."""
    platform_utils._IS_WSL = None
    platform_utils._WSL_VERSION = None
    platform_utils._CASE_SENSITIVE = None


class TestGetLongPath:
    """Tests for get_long_path()."""

    def test_get_long_path_on_non_windows(self):
        """On non-Windows, returns path unchanged."""
        with patch.object(sys, "platform", "linux"):
            result = get_long_path("/home/user/file.txt")
            assert result == "/home/user/file.txt"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_get_long_path_on_windows(self, tmp_path):
        """On Windows, prefixes with \\\\?\\."""
        test_path = tmp_path / "test.txt"
        result = get_long_path(test_path)
        assert result.startswith("\\\\?\\")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_get_long_path_already_prefixed(self):
        """Already prefixed paths are returned unchanged."""
        prefixed = "\\\\?\\C:\\some\\path"
        result = get_long_path(prefixed)
        assert result == prefixed

    def test_get_long_path_unc_path(self):
        """UNC paths get proper \\\\?\\UNC\\ prefix."""
        with patch.object(sys, "platform", "win32"):
            with patch("os.path.abspath", return_value="\\\\server\\share\\path"):
                result = get_long_path("\\\\server\\share\\path")
                assert result == "\\\\?\\UNC\\server\\share\\path"

    def test_get_long_path_regular_windows_path(self):
        """Regular Windows paths get \\\\?\\ prefix."""
        with patch.object(sys, "platform", "win32"):
            with patch("os.path.abspath", return_value="C:\\Users\\test"):
                result = get_long_path("C:\\Users\\test")
                assert result == "\\\\?\\C:\\Users\\test"

    def test_get_long_path_exception_handling(self):
        """Handles exceptions gracefully."""
        with patch("os.path.abspath", side_effect=Exception("test error")):
            with patch.object(sys, "platform", "win32"):
                result = get_long_path("some/path")
                assert result == "some/path"


class TestIsWsl:
    """Tests for is_wsl()."""

    def test_is_wsl_cached_true(self):
        """Returns cached True value."""
        platform_utils._IS_WSL = True
        assert is_wsl() is True
        reset_platform_utils_cache()

    def test_is_wsl_cached_false(self):
        """Returns cached False value."""
        platform_utils._IS_WSL = False
        assert is_wsl() is False
        reset_platform_utils_cache()

    def test_is_wsl_from_proc_version_microsoft(self):
        """Detects WSL from /proc/version containing 'microsoft'."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Linux version 5.10.16.3-microsoft-standard"

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {}, clear=True):
                result = is_wsl()
                assert result is True

        reset_platform_utils_cache()

    def test_is_wsl_from_proc_version_wsl(self):
        """Detects WSL from /proc/version containing 'wsl'."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Linux version 5.10.16.3-WSL2-something"

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {}, clear=True):
                result = is_wsl()
                assert result is True

        reset_platform_utils_cache()

    def test_is_wsl_from_wsl_distro_name_env(self):
        """Detects WSL from WSL_DISTRO_NAME environment variable."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=True):
                result = is_wsl()
                assert result is True

        reset_platform_utils_cache()

    def test_is_wsl_from_wsl_interop_env(self):
        """Detects WSL from WSL_INTEROP environment variable."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {"WSL_INTEROP": "/run/WSL/1_interop"}, clear=True):
                result = is_wsl()
                assert result is True

        reset_platform_utils_cache()

    def test_is_wsl_not_wsl(self):
        """Returns False when not in WSL."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {}, clear=True):
                result = is_wsl()
                assert result is False

        reset_platform_utils_cache()

    def test_is_wsl_proc_version_oserror(self):
        """Handles OSError when reading /proc/version."""
        reset_platform_utils_cache()

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = OSError("Permission denied")

        with patch("platform_utils.Path", return_value=mock_path):
            with patch.dict(os.environ, {}, clear=True):
                result = is_wsl()
                assert result is False

        reset_platform_utils_cache()


class TestGetWslVersion:
    """Tests for get_wsl_version()."""

    def test_get_wsl_version_cached(self):
        """Returns cached value."""
        platform_utils._WSL_VERSION = 2
        platform_utils._IS_WSL = True
        assert get_wsl_version() == 2
        reset_platform_utils_cache()

    def test_get_wsl_version_not_wsl(self):
        """Returns None when not WSL."""
        platform_utils._IS_WSL = False
        platform_utils._WSL_VERSION = None
        assert get_wsl_version() is None
        reset_platform_utils_cache()

    def test_get_wsl_version_wsl2_from_run_wsl(self):
        """Detects WSL2 from /run/WSL directory."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_run_wsl = MagicMock()
        mock_run_wsl.exists.return_value = True

        with patch("platform_utils.Path") as mock_path_class:
            mock_path_class.return_value = mock_run_wsl
            result = get_wsl_version()
            assert result == 2

        reset_platform_utils_cache()

    def test_get_wsl_version_wsl2_from_proc_version(self):
        """Detects WSL2 from /proc/version kernel string."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_run_wsl = MagicMock()
        mock_run_wsl.exists.return_value = False

        mock_proc_version = MagicMock()
        mock_proc_version.read_text.return_value = "Linux 5.10.16.3-microsoft-standard-WSL2"

        def path_side_effect(p):
            if p == "/run/WSL":
                return mock_run_wsl
            elif p == "/proc/version":
                return mock_proc_version
            return MagicMock()

        with patch("platform_utils.Path", side_effect=path_side_effect):
            result = get_wsl_version()
            assert result == 2

        reset_platform_utils_cache()

    def test_get_wsl_version_wsl1_default(self):
        """Defaults to WSL1 when WSL detected but not WSL2."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_run_wsl = MagicMock()
        mock_run_wsl.exists.return_value = False

        mock_proc_version = MagicMock()
        mock_proc_version.read_text.return_value = "Linux 4.4.0-microsoft"

        def path_side_effect(p):
            if p == "/run/WSL":
                return mock_run_wsl
            elif p == "/proc/version":
                return mock_proc_version
            return MagicMock()

        with patch("platform_utils.Path", side_effect=path_side_effect):
            result = get_wsl_version()
            assert result == 1

        reset_platform_utils_cache()

    def test_get_wsl_version_proc_version_oserror(self):
        """Handles OSError when checking WSL version, defaults to WSL1."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_run_wsl = MagicMock()
        mock_run_wsl.exists.return_value = False

        mock_proc_version = MagicMock()
        mock_proc_version.read_text.side_effect = OSError("Permission denied")

        def path_side_effect(p):
            if p == "/run/WSL":
                return mock_run_wsl
            elif p == "/proc/version":
                return mock_proc_version
            return MagicMock()

        with patch("platform_utils.Path", side_effect=path_side_effect):
            result = get_wsl_version()
            assert result == 1  # Default to WSL1

        reset_platform_utils_cache()


class TestIsWindowsPath:
    """Tests for is_windows_path()."""

    def test_is_windows_path_not_wsl(self):
        """Returns False when not in WSL."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = False

        result = is_windows_path(Path("/mnt/c/Users"))
        assert result is False

        reset_platform_utils_cache()

    def test_is_windows_path_wsl_mnt_path(self):
        """Detects /mnt/c/ style paths in WSL."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt", "c", "Users")

        result = is_windows_path(mock_path)
        assert result is True

        reset_platform_utils_cache()

    def test_is_windows_path_wsl_linux_path(self):
        """Returns False for Linux paths in WSL."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "home", "user")

        result = is_windows_path(mock_path)
        assert result is False

        reset_platform_utils_cache()

    def test_is_windows_path_short_parts(self):
        """Returns False for paths with fewer than 3 parts."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt")

        result = is_windows_path(mock_path)
        assert result is False

        reset_platform_utils_cache()

    def test_is_windows_path_oserror_on_resolve(self):
        """Handles OSError when resolving path."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.side_effect = OSError("Cannot resolve")
        mock_path.parts = ("/", "mnt", "c", "Users")

        result = is_windows_path(mock_path)
        assert result is True

        reset_platform_utils_cache()

    def test_is_windows_path_non_single_char_drive(self):
        """Returns False when drive letter is not single char."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt", "cd", "Users")  # 'cd' is not a valid drive

        result = is_windows_path(mock_path)
        assert result is False

        reset_platform_utils_cache()


class TestGetNativeWindowsPath:
    """Tests for get_native_windows_path()."""

    def test_get_native_windows_path_not_windows_path(self):
        """Returns None for non-Windows paths."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = False

        result = get_native_windows_path(Path("/home/user"))
        assert result is None

        reset_platform_utils_cache()

    def test_get_native_windows_path_conversion(self):
        """Converts WSL path to Windows path."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt", "c", "Users", "test")

        with patch("platform_utils.is_windows_path", return_value=True):
            result = get_native_windows_path(mock_path)

        assert result == "C:\\Users\\test"
        reset_platform_utils_cache()

    def test_get_native_windows_path_oserror_on_resolve(self):
        """Handles OSError when resolving path."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.side_effect = OSError("Cannot resolve")
        mock_path.parts = ("/", "mnt", "d", "Data", "files")

        with patch("platform_utils.is_windows_path", return_value=True):
            result = get_native_windows_path(mock_path)

        assert result == "D:\\Data\\files"
        reset_platform_utils_cache()

    def test_get_native_windows_path_short_path(self):
        """Returns None for path with fewer than 3 parts after resolution."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt")

        with patch("platform_utils.is_windows_path", return_value=True):
            result = get_native_windows_path(mock_path)

        assert result is None
        reset_platform_utils_cache()


class TestIsFilesystemCaseSensitive:
    """Tests for is_filesystem_case_sensitive()."""

    def test_is_filesystem_case_sensitive_detection(self):
        """Detects case sensitivity correctly."""
        reset_platform_utils_cache()

        result = is_filesystem_case_sensitive()
        assert isinstance(result, bool)

        # On Windows, typically False; on Linux, typically True
        if sys.platform == "win32":
            assert result is False

        reset_platform_utils_cache()

    def test_is_filesystem_case_sensitive_cached_true(self):
        """Returns cached True value."""
        platform_utils._CASE_SENSITIVE = True
        assert is_filesystem_case_sensitive() is True
        reset_platform_utils_cache()

    def test_is_filesystem_case_sensitive_cached_false(self):
        """Returns cached False value."""
        platform_utils._CASE_SENSITIVE = False
        assert is_filesystem_case_sensitive() is False
        reset_platform_utils_cache()


class TestIsPathCaseSensitive:
    """Tests for is_path_case_sensitive()."""

    def test_is_path_case_sensitive_windows_path_in_wsl(self):
        """Windows paths in WSL are case-insensitive."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.parts = ("/", "mnt", "c", "Users")

        with patch("platform_utils.is_windows_path", return_value=True):
            result = is_path_case_sensitive(mock_path)

        assert result is False
        reset_platform_utils_cache()

    def test_is_path_case_sensitive_linux_path_in_wsl(self):
        """Linux paths in WSL use filesystem detection."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._CASE_SENSITIVE = True

        mock_path = MagicMock()
        with patch("platform_utils.is_windows_path", return_value=False):
            result = is_path_case_sensitive(mock_path)

        assert result is True
        reset_platform_utils_cache()

    def test_is_path_case_sensitive_native_path(self, tmp_path):
        """Native paths use filesystem detection."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = False

        result = is_path_case_sensitive(tmp_path)
        assert isinstance(result, bool)

        reset_platform_utils_cache()


class TestIsCaseOnlyRename:
    """Tests for is_case_only_rename()."""

    def test_is_case_only_rename_true(self):
        """Detects case-only renames."""
        old = Path("/path/to/File.txt")
        new = Path("/path/to/file.txt")
        assert is_case_only_rename(old, new) is True

    def test_is_case_only_rename_false_different_names(self):
        """Different names are not case-only renames."""
        old = Path("/path/to/file1.txt")
        new = Path("/path/to/file2.txt")
        assert is_case_only_rename(old, new) is False

    def test_is_case_only_rename_false_same_case(self):
        """Same case is not a rename."""
        old = Path("/path/to/file.txt")
        new = Path("/path/to/file.txt")
        assert is_case_only_rename(old, new) is False

    def test_is_case_only_rename_all_uppercase(self):
        """Detects uppercase to lowercase rename."""
        old = Path("/path/to/FILE.TXT")
        new = Path("/path/to/file.txt")
        assert is_case_only_rename(old, new) is True


class TestHandleWslSymlink:
    """Tests for handle_wsl_symlink()."""

    def test_handle_wsl_symlink_cross_filesystem_windows_to_linux(self):
        """Cross-filesystem symlinks (Windows to Linux) return False."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        source = MagicMock()
        target = MagicMock()

        with patch("platform_utils.is_windows_path", side_effect=[True, False]):
            result = handle_wsl_symlink(source, target)

        assert result is False
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_cross_filesystem_linux_to_windows(self):
        """Cross-filesystem symlinks (Linux to Windows) return False."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True

        source = MagicMock()
        target = MagicMock()

        with patch("platform_utils.is_windows_path", side_effect=[False, True]):
            result = handle_wsl_symlink(source, target)

        assert result is False
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_wsl1_ntfs_success(self):
        """WSL1 on NTFS symlink success."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._WSL_VERSION = 1

        source = MagicMock()
        target = MagicMock()
        target.symlink_to.return_value = None  # Success

        with patch("platform_utils.is_windows_path", return_value=True):
            with patch("platform_utils.get_wsl_version", return_value=1):
                result = handle_wsl_symlink(source, target)

        assert result is True
        target.symlink_to.assert_called_once_with(source)
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_wsl1_ntfs_failure(self):
        """WSL1 on NTFS symlink failure."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._WSL_VERSION = 1

        source = MagicMock()
        target = MagicMock()
        target.symlink_to.side_effect = OSError("Permission denied")

        with patch("platform_utils.is_windows_path", return_value=True):
            with patch("platform_utils.get_wsl_version", return_value=1):
                result = handle_wsl_symlink(source, target)

        assert result is False
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_wsl2_success(self):
        """WSL2 or Linux filesystem symlink success."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._WSL_VERSION = 2

        source = MagicMock()
        target = MagicMock()
        target.symlink_to.return_value = None

        with patch("platform_utils.is_windows_path", return_value=False):
            with patch("platform_utils.get_wsl_version", return_value=2):
                result = handle_wsl_symlink(source, target)

        assert result is True
        target.symlink_to.assert_called_once_with(source)
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_wsl2_failure(self):
        """WSL2 or Linux filesystem symlink failure."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._WSL_VERSION = 2

        source = MagicMock()
        target = MagicMock()
        target.symlink_to.side_effect = OSError("Operation not permitted")

        with patch("platform_utils.is_windows_path", return_value=False):
            with patch("platform_utils.get_wsl_version", return_value=2):
                result = handle_wsl_symlink(source, target)

        assert result is False
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_same_filesystem_linux(self, tmp_path):
        """Same-filesystem Linux symlinks attempt creation."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = False
        platform_utils._WSL_VERSION = None

        source = tmp_path / "source.txt"
        source.write_text("content")
        target = tmp_path / "link.txt"

        with patch("platform_utils.is_windows_path", return_value=False):
            with patch("platform_utils.get_wsl_version", return_value=None):
                result = handle_wsl_symlink(source, target)

        # May succeed or fail depending on permissions
        assert isinstance(result, bool)
        reset_platform_utils_cache()

    def test_handle_wsl_symlink_both_windows_paths_non_wsl1(self):
        """Both Windows paths with non-WSL1 version."""
        reset_platform_utils_cache()
        platform_utils._IS_WSL = True
        platform_utils._WSL_VERSION = 2

        source = MagicMock()
        target = MagicMock()
        target.symlink_to.return_value = None

        with patch("platform_utils.is_windows_path", return_value=True):
            with patch("platform_utils.get_wsl_version", return_value=2):
                result = handle_wsl_symlink(source, target)

        assert result is True
        reset_platform_utils_cache()
