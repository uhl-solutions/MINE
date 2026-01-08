"""
Directory scanning logic for integration discovery.

Provides functions for scanning directories to find Claude Code
integrations and their markers.
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .markers import find_markers, infer_repo_name, group_markers_by_repo


def scan_for_integrations(
    locations: List[tuple],
    skip_dirs: Optional[List[str]] = None,
    verbose: bool = False,
    log_fn: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Scan multiple locations for integrations.

    Args:
        locations: List of (scope, path) tuples to scan
        skip_dirs: List of directory names to skip
        verbose: Enable verbose logging
        log_fn: Optional logging function

    Returns:
        List of discovered integration dictionaries
    """
    if skip_dirs is None:
        skip_dirs = ["node_modules", "venv", "__pycache__", ".git"]

    discoveries = []

    def log(msg: str):
        if log_fn:
            log_fn(msg)
        elif verbose:
            print(f"[DISCOVER] {msg}", file=sys.stderr)

    for scope, path in locations:
        log(f"Scanning {scope}: {path}")
        found = scan_location(path, scope, skip_dirs=skip_dirs, log_fn=log)
        discoveries.extend(found)

    return discoveries


def scan_location(
    path: Path,
    scope: str,
    skip_dirs: Optional[List[str]] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Scan a single location for integration markers.

    Handles both project/root scope (recursive search for .claude dirs)
    and user scope (direct marker search in ~/.claude).

    Args:
        path: Path to scan
        scope: Scope type ("project", "root", or "user")
        skip_dirs: List of directory names to skip
        log_fn: Optional logging function for verbose output

    Returns:
        List of discovered integration dictionaries
    """
    if skip_dirs is None:
        skip_dirs = ["node_modules", "venv", "__pycache__", ".git"]

    discoveries = []

    if not path.exists():
        return discoveries

    def walk_error_handler(os_error: OSError):
        """Handle permission errors during directory walk."""
        if os_error.errno == 13:  # Permission denied
            if log_fn:
                log_fn(f"Permission denied during directory walk: {os_error.filename}")
        else:
            raise os_error

    # Look for .claude directory markers (project/root scope)
    if scope in ["project", "root"]:
        discoveries.extend(_scan_project_scope(path, skip_dirs, walk_error_handler, log_fn))

    # Look for user-scope artifacts
    if scope == "user":
        discoveries.extend(_scan_user_scope(path, log_fn))

    return discoveries


def _scan_project_scope(
    path: Path,
    skip_dirs: List[str],
    error_handler: Callable[[OSError], None],
    log_fn: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Scan for project-scope integrations.

    Recursively searches for .claude directories and extracts markers.

    Args:
        path: Root path to scan
        skip_dirs: Directories to skip
        error_handler: Function to handle OS errors
        log_fn: Optional logging function

    Returns:
        List of discovered integrations
    """
    discoveries = []

    try:
        for root, dirs, files in os.walk(path, onerror=error_handler):
            root_path = Path(root)

            # Check for .claude directory before filtering
            has_claude = ".claude" in dirs

            # Filter out hidden and large directories
            # (We check for .claude above before filtering)
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]

            if has_claude:
                claude_dir = root_path / ".claude"
                try:
                    found_markers = find_markers(claude_dir)
                    if found_markers:
                        discoveries.append(
                            {
                                "scope": "project",
                                "target_path": str(claude_dir.parent),
                                "claude_dir": str(claude_dir),
                                "markers": found_markers,
                                "markers_found": len(found_markers),
                                "inferred_name": infer_repo_name(found_markers),
                            }
                        )
                except PermissionError:
                    if log_fn:
                        log_fn(f"Permission denied: {claude_dir}")

    except PermissionError as e:
        if log_fn:
            log_fn(f"Permission denied scanning {path}: {e}")

    return discoveries


def _scan_user_scope(
    path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Scan for user-scope integrations.

    Searches the user's ~/.claude directory for markers and groups
    them by repository.

    Args:
        path: Path to user's .claude directory
        log_fn: Optional logging function

    Returns:
        List of discovered integrations
    """
    discoveries = []

    try:
        found_markers = find_markers(path)

        # Group markers by repo_id
        repo_groups = group_markers_by_repo(found_markers)

        # Create one discovery per repo group
        for repo_id, markers in repo_groups.items():
            discoveries.append(
                {
                    "scope": "user",
                    "target_path": str(path),
                    "claude_dir": str(path),
                    "markers": markers,
                    "markers_found": len(markers),
                    "inferred_name": repo_id,
                }
            )

    except PermissionError:
        if log_fn:
            log_fn(f"Permission denied: {path}")

    return discoveries


def filter_discoveries(
    discoveries: List[Dict[str, Any]],
    min_markers: int = 1,
    scopes: Optional[List[str]] = None,
    repo_pattern: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter discovered integrations by various criteria.

    Args:
        discoveries: List of discovered integrations
        min_markers: Minimum number of markers required
        scopes: List of scopes to include (None = all)
        repo_pattern: Regex pattern to match repo names (None = all)

    Returns:
        Filtered list of discoveries
    """
    import re

    filtered = discoveries

    # Filter by minimum markers
    if min_markers > 1:
        filtered = [d for d in filtered if d["markers_found"] >= min_markers]

    # Filter by scope
    if scopes:
        filtered = [d for d in filtered if d["scope"] in scopes]

    # Filter by repo name pattern
    if repo_pattern:
        pattern = re.compile(repo_pattern)
        filtered = [d for d in filtered if pattern.search(d["inferred_name"])]

    return filtered
