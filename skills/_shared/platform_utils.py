#!/usr/bin/env python3
"""
platform_utils.py - Platform-specific utilities

Handles platform detection, filesystem case sensitivity, and WSL quirks.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Union

_IS_WSL: Optional[bool] = None
_WSL_VERSION: Optional[int] = None
_CASE_SENSITIVE: Optional[bool] = None


def get_long_path(path: Union[str, Path]) -> str:
    """
    On Windows, prefix absolute paths with \\?\\ to support long paths (>260 chars).
    Returns the path as a string.
    """
    path_str = str(path)
    if sys.platform != "win32":
        return path_str

    # Already prefixed
    if path_str.startswith("\\\\?\\"):
        return path_str

    # Only absolute paths can be prefixed
    try:
        abs_path = os.path.abspath(path_str)

        if abs_path.startswith("\\\\"):
            # UNC path: \\server\\share -> \\?\\UNC\\server\\share
            return "\\\\?\\UNC\\" + abs_path[2:]
        else:
            # Regular path: C:\\path -> \\?\\C:\\path
            return "\\\\?\\" + abs_path
    except Exception:
        return path_str


def is_wsl() -> bool:
    """
    Detect if running under Windows Subsystem for Linux.
    """
    global _IS_WSL

    if _IS_WSL is not None:
        return _IS_WSL

    # Method 1: Check /proc/version
    try:
        version_file = Path("/proc/version")
        if version_file.exists():
            version_text = version_file.read_text().lower()
            if "microsoft" in version_text or "wsl" in version_text:
                _IS_WSL = True
                return True
    except (OSError, PermissionError):
        pass

    # Method 2: Check environment variable
    if os.environ.get("WSL_DISTRO_NAME"):
        _IS_WSL = True
        return True

    # Method 3: Check WSL interop
    if os.environ.get("WSL_INTEROP"):
        _IS_WSL = True
        return True

    _IS_WSL = False
    return False


def get_wsl_version() -> Optional[int]:
    """
    Get WSL version (1 or 2).

    Returns:
        1, 2, or None if not WSL
    """
    global _WSL_VERSION

    if _WSL_VERSION is not None:
        return _WSL_VERSION

    if not is_wsl():
        return None

    # WSL2 has /run/WSL directory
    if Path("/run/WSL").exists():
        _WSL_VERSION = 2
        return 2

    # Check for WSL2-specific kernel version pattern
    try:
        version_text = Path("/proc/version").read_text()
        if "microsoft-standard-WSL2" in version_text:
            _WSL_VERSION = 2
            return 2
    except (OSError, PermissionError):
        pass

    # Default to WSL1 if WSL detected but not WSL2
    _WSL_VERSION = 1
    return 1


def is_windows_path(path: Path) -> bool:
    """
    Check if path is on a Windows filesystem (via /mnt/).

    Args:
        path: Path to check

    Returns:
        True if path is on Windows filesystem
    """
    if not is_wsl():
        return False

    # Resolve to absolute path
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path

    # Check for /mnt/<drive> pattern
    parts = resolved.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt":
        if len(parts[2]) == 1 and parts[2].isalpha():
            return True

    return False


def get_native_windows_path(wsl_path: Path) -> Optional[str]:
    """
    Convert WSL path to native Windows path.

    /mnt/c/Users/foo -> C:\\Users\\foo

    Args:
        wsl_path: WSL path under /mnt/

    Returns:
        Windows path string, or None if not a Windows path
    """
    if not is_windows_path(wsl_path):
        return None

    try:
        resolved = wsl_path.resolve()
    except OSError:
        resolved = wsl_path

    parts = resolved.parts
    if len(parts) >= 3:
        drive = parts[2].upper()
        remainder = "\\".join(parts[3:])
        return f"{drive}:\\{remainder}"

    return None


def is_filesystem_case_sensitive() -> bool:
    """
    Detect if the current filesystem is case-sensitive.
    """
    global _CASE_SENSITIVE

    if _CASE_SENSITIVE is not None:
        return _CASE_SENSITIVE

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "CaSe_TeSt"
        test_file.touch()
        _CASE_SENSITIVE = not (Path(tmpdir) / "case_test").exists()

    return _CASE_SENSITIVE


def is_path_case_sensitive(path: Path) -> bool:
    """
    Check if the filesystem at path is case-sensitive.

    In WSL:
    - /home/... is case-sensitive (Linux filesystem)
    - /mnt/c/... is case-insensitive (Windows NTFS)
    """
    # On WSL, Windows paths are case-insensitive
    if is_wsl() and is_windows_path(path):
        return False

    # Use actual filesystem test for native paths
    return is_filesystem_case_sensitive()


def is_case_only_rename(old_path: Path, new_path: Path) -> bool:
    """Check if this is a case-only rename."""
    return old_path.name.lower() == new_path.name.lower() and old_path.name != new_path.name


def handle_wsl_symlink(source: Path, target: Path) -> bool:
    """
    Create symlink with WSL-aware handling.

    WSL1 has limited symlink support on NTFS.
    WSL2 has better support but cross-filesystem links are problematic.

    Returns:
        True if symlink created successfully
    """
    # Check for cross-filesystem symlink (problematic in WSL)
    source_is_windows = is_windows_path(source)
    target_is_windows = is_windows_path(target)

    if source_is_windows != target_is_windows:
        # Cross-filesystem symlink - may not work reliably
        # Copy instead of symlink
        return False

    # WSL1 symlinks on NTFS require developer mode
    if get_wsl_version() == 1 and target_is_windows:
        # Try symlink, fall back to copy on failure
        try:
            target.symlink_to(source)
            return True
        except OSError:
            return False

    # WSL2 or Linux filesystem - normal symlink
    try:
        target.symlink_to(source)
        return True
    except OSError:
        return False
