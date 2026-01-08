#!/usr/bin/env python3
"""
path_safety.py

Provides path validation and safety checks to prevent:
- Directory traversal attacks (e.g. ../../etc/passwd)
- Writes outside allowed scope roots
- Symlink following (optionally)

Usage:
    from .path_safety import validate_path, is_safe_path

    validate_path("/some/path", root="/allowed/root")
"""

from pathlib import Path
from typing import Optional, Union


class PathSafetyError(Exception):
    """Raised when a path violates safety constraints."""

    pass


try:
    from . import platform_utils
except ImportError:
    import platform_utils


def resolve_path(path: Union[str, Path]) -> Path:
    """Resolve a path to its absolute form, resolving symlinks."""
    return Path(path).resolve()


def is_safe_path(path: Union[str, Path], root: Union[str, Path]) -> bool:
    """
    Check if a path is safely contained within a root directory.

    Args:
        path: The path to check (file or directory)
        root: The allowed root directory

    Returns:
        bool: True if path is inside root, False otherwise
    """
    try:
        # Convert to absolute paths and resolve symlinks
        abs_path = resolve_path(path)
        abs_root = resolve_path(root)

        # Check if root is actually a parent of path
        # This handles ../ traversal attempts automatically via resolve()
        try:
            abs_path.relative_to(abs_root)
            return True
        except ValueError:
            # On case-insensitive filesystems (including WSL mounts),
            # relative_to might fail due to case mismatch
            if not platform_utils.is_path_case_sensitive(abs_root):
                # Check parts case-insensitively
                root_parts = abs_root.parts
                path_parts = abs_path.parts

                if len(path_parts) >= len(root_parts):
                    # Compare prefix parts case-insensitively
                    for r, p in zip(root_parts, path_parts):
                        if r.lower() != p.lower():
                            return False
                    return True

            return False

    except (OSError, RuntimeError):
        return False


def validate_path(
    path: Union[str, Path], root: Union[str, Path], allow_symlinks: bool = False, error_msg: Optional[str] = None
) -> Path:
    """
    Validate that a path is safe and within the allowed root.

    Args:
        path: Path to validate
        root: Allowed root directory
        allow_symlinks: Whether to allow the final path to be a symlink
        error_msg: Custom error message used if validation fails

    Returns:
        Path: The resolved absolute path

    Raises:
        PathSafetyError: If path is unsafe or outside root
    """
    path_obj = Path(path)

    # Check for suspicious patterns before resolving
    # This catches obvious ../ attempts even if they resolve to valid paths
    # (though resolve() handles the actual check, explicit check is good defense-in-depth)
    parts = path_obj.parts
    if ".." in parts:
        raise PathSafetyError(f"Path traversal detected: {path}")

    # Check symlink constraint BEFORE resolution
    # This prevents symlink-based escapes from the allowed root
    if not allow_symlinks:
        try:
            # Check if the path exists and is a symlink
            if path_obj.exists() and path_obj.is_symlink():
                raise PathSafetyError(f"Symlink not allowed: {path}. Set allow_symlinks=True to permit.")
        except OSError:
            # If we can't check (permission issues, etc.), proceed with caution
            # The is_safe_path check will still validate the resolved path
            pass

    if not is_safe_path(path, root):
        msg = error_msg or f"Path '{path}' is outside allowed root '{root}'"
        raise PathSafetyError(msg)

    return resolve_path(path)


def ensure_directory_safety(path: Union[str, Path], root: Union[str, Path]) -> None:
    """
    Ensure a directory path is safe to create/write to.
    Does NOT create the directory, just validates.
    """
    validate_path(path, root)
