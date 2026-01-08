#!/usr/bin/env python3
"""
hash_helpers.py - File hashing helper functions

Provides file hashing utilities for tracking changes and matching artifacts.
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional


def hash_file(file_path: Path) -> Optional[str]:
    """
    Calculate SHA-256 hash of a file.

    Returns hex digest string, or None if file cannot be read.
    """
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError):
        return None


def hash_string(content: str) -> str:
    """Calculate SHA-256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_directory_files(
    directory: Path, patterns: list[str] = None, exclude_patterns: list[str] = None
) -> Dict[str, str]:
    """
    Hash all files in a directory matching patterns.

    Args:
        directory: Directory to scan
        patterns: List of glob patterns to include (e.g., ['*.md', '*.py'])
                 If None, includes all files
        exclude_patterns: List of glob patterns to exclude

    Returns:
        Dictionary mapping relative paths to hash strings
    """
    if not directory.exists() or not directory.is_dir():
        return {}

    file_hashes = {}

    # Get all files if no patterns specified
    if patterns is None:
        files = [f for f in directory.rglob("*") if f.is_file()]
    else:
        files = []
        for pattern in patterns:
            files.extend(directory.rglob(pattern))

    # Apply exclusions
    if exclude_patterns:
        excluded = set()
        for pattern in exclude_patterns:
            excluded.update(directory.rglob(pattern))
        files = [f for f in files if f not in excluded]

    # Hash each file
    for file_path in files:
        file_hash = hash_file(file_path)
        if file_hash:
            rel_path = str(file_path.relative_to(directory))
            file_hashes[rel_path] = file_hash

    return file_hashes


def files_match(file1: Path, file2: Path) -> bool:
    """Check if two files have the same content (by hash)."""
    hash1 = hash_file(file1)
    hash2 = hash_file(file2)

    if hash1 is None or hash2 is None:
        return False

    return hash1 == hash2


def has_file_changed(file_path: Path, expected_hash: str) -> bool:
    """
    Check if a file has changed from an expected hash.

    Returns True if file is different or missing, False if matches.
    """
    current_hash = hash_file(file_path)

    if current_hash is None:
        return True  # File missing or unreadable

    return current_hash != expected_hash
