#!/usr/bin/env python3
"""
git_helpers.py - Git operations helper functions

Provides safe Git operations for cloning, fetching, and analyzing repositories.
"""

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def has_gh_cli() -> bool:
    """Check if GitHub CLI is available and authenticated."""
    if not shutil.which("gh"):
        return False

    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


MAX_RETRIES = 4  # Total 5 attempts
RETRY_DELAY_BASE = 2


def clone_repo(url: str, dest_path: Path, verbose: bool = False) -> bool:
    """Clone a repository using centralized auth fallback (with exponential backoff).

    Uses secure authentication via GIT_ASKPASS to avoid token exposure in:
    - Process listings (ps aux)
    - .git/config persistence
    - Command history
    - Error messages
    """
    dest = Path(dest_path)

    # Import secure clone helper
    try:
        from url_utils import clone_with_auth_fallback, redact_url_credentials
    except ImportError:
        redact_url_credentials = lambda x: x
        clone_with_auth_fallback = None

    # Retry loop
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Use centralized clone helper (handles gh CLI, askpass, and plain git fallback)
            if clone_with_auth_fallback is not None:
                if verbose:
                    print(f"Attempting clone (attempt {attempt + 1}/{MAX_RETRIES + 1})...", file=sys.stderr)
                if clone_with_auth_fallback(url, dest, depth=1, extra_args=["--no-single-branch"], verbose=verbose):
                    return True

            # Ultimate fallback: plain git clone (no auth)
            if verbose:
                print(f"Trying plain git clone (attempt {attempt + 1}/{MAX_RETRIES + 1})...", file=sys.stderr)
            cmd = ["git", "clone", "--depth", "1", "--no-single-branch", url, str(dest)]
            subprocess.run(cmd, check=True, capture_output=not verbose)
            return True

        except subprocess.CalledProcessError:
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_BASE * (2**attempt)
                if verbose:
                    print(f"Clone failed, retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
                # Cleanup partial dir if exists
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
            else:
                if verbose:
                    print(
                        f"Clone failed for {redact_url_credentials(url)} after {MAX_RETRIES + 1} attempts",
                        file=sys.stderr,
                    )
                return False
        except Exception as e:
            if verbose:
                print(f"Clone error: {type(e).__name__}", file=sys.stderr)
            return False

    return False


def fetch_repo(repo_path: Path, verbose: bool = False) -> bool:
    """Fetch latest changes from remote (with exponential backoff)."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            subprocess.run(["git", "-C", str(repo_path), "fetch", "--all"], check=True, capture_output=not verbose)
            if verbose:
                print(f"[GIT] Fetched updates for {repo_path}")
            return True
        except subprocess.CalledProcessError:
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_BASE * (2**attempt)
                if verbose:
                    print(f"Fetch failed, retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
            else:
                return False
    return False


def get_current_commit(repo_path: Path) -> Optional[str]:
    """Get current HEAD commit SHA."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_remote_head(repo_path: Path, branch: str = None) -> Optional[str]:
    """Get remote HEAD commit SHA, auto-detecting default branch if needed."""
    try:
        # If branch/ref specified, try it
        if branch:
            # Try origin/{branch} (Remote Branch)
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", f"origin/{branch}"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()

            # Try as exact tag/ref (might be fetched locally already)
            result = subprocess.run(["git", "-C", str(repo_path), "rev-parse", branch], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()

            return None

        # Auto-detect default branch from remote HEAD
        result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "refs/remotes/origin/HEAD"], capture_output=True, text=True
        )

        if result.returncode == 0:
            # Output like: refs/remotes/origin/main
            ref = result.stdout.strip()
            branch_name = ref.split("/")[-1]

            # Get SHA for that branch
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", f"origin/{branch_name}"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()

        # Fallback 1: Query remote HEAD symbolic ref via ls-remote
        result = subprocess.run(
            ["git", "-C", str(repo_path), "ls-remote", "--symref", "origin", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("ref:"):
                    # Line format: "ref: refs/heads/main	HEAD"
                    parts = line.split()
                    if len(parts) >= 2:
                        ref_part = parts[1]
                        branch_name = ref_part.split("/")[-1]

                        # Get SHA for that branch
                        result = subprocess.run(
                            ["git", "-C", str(repo_path), "rev-parse", f"origin/{branch_name}"],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            return result.stdout.strip()

        # Fallback 2: try common branch names
        for default_branch in ["main", "master", "develop"]:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", f"origin/{default_branch}"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()

        return None
    except subprocess.CalledProcessError:
        return None


def get_commit_log(repo_path: Path, from_commit: str, to_commit: str) -> List[Dict[str, str]]:
    """Get commit log between two commits."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                f"{from_commit}..{to_commit}",
                "--pretty=format:%H|||%an|||%ae|||%aI|||%s",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) == 5:
                commits.append(
                    {"sha": parts[0], "author": parts[1], "email": parts[2], "date": parts[3], "message": parts[4]}
                )

        return commits
    except subprocess.CalledProcessError:
        return []


def get_file_diff(repo_path: Path, from_commit: str, to_commit: str, file_path: str) -> Optional[str]:
    """Get diff for a specific file between commits, handling binary files."""
    try:
        # We don't use text=True here initially to avoid potential decode errors
        # for binary content if git tries to show it (though unlikely with default diff)
        # But git diff with --name-status or similar is better.
        # Here we want the actual content diff.
        result = subprocess.run(
            ["git", "-C", str(repo_path), "diff", f"{from_commit}..{to_commit}", "--", file_path],
            capture_output=True,
            text=True,
            check=True,
            errors="replace",  # Handle potential encoding issues in filenames or diff markers
        )

        if "Binary files" in result.stdout:
            return f"Binary file changed: {file_path}"

        return result.stdout
    except subprocess.CalledProcessError:
        return None


def get_changed_files(repo_path: Path, from_commit: str, to_commit: str) -> List[Tuple[str, str]]:
    """
    Get list of changed files between commits.

    Returns list of (status, filepath) tuples.
    Status can be: A (added), M (modified), D (deleted), R (renamed)
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--name-status", f"{from_commit}..{to_commit}"],
            capture_output=True,
            text=True,
            check=True,
        )

        changes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                changes.append((parts[0], parts[1]))

        return changes
    except subprocess.CalledProcessError:
        return []


def get_tags(repo_path: Path) -> List[str]:
    """Get list of all tags in repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "tag", "--list"], capture_output=True, text=True, check=True
        )
        return [tag.strip() for tag in result.stdout.split("\n") if tag.strip()]
    except subprocess.CalledProcessError:
        return []


def checkout_commit(repo_path: Path, commit: str, verbose: bool = False) -> bool:
    """Checkout a specific commit."""
    try:
        subprocess.run(["git", "-C", str(repo_path), "checkout", commit], check=True, capture_output=not verbose)
        return True
    except subprocess.CalledProcessError:
        return False


def is_commit_reachable(repo_path: Path, commit: str) -> bool:
    """
    Check if a commit exists and is reachable in the repository.

    Used for force-push detection: if a previously-imported commit
    is no longer reachable, history was rewritten.
    """
    try:
        result = subprocess.run(["git", "-C", str(repo_path), "cat-file", "-t", commit], capture_output=True, text=True)
        return result.returncode == 0 and "commit" in result.stdout
    except subprocess.CalledProcessError:
        return False


def get_merge_base(repo_path: Path, commit1: str, commit2: str) -> Optional[str]:
    """
    Get merge-base (common ancestor) between two commits.

    Returns None if commits have no common ancestor or error occurs.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "merge-base", commit1, commit2], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_safe_diff_range(repo_path: Path, from_commit: str, to_commit: str) -> Tuple[Optional[str], str, str]:
    """
    Get a safe commit range for diffing, handling history rewrites.

    Detects force-pushes and rebases, providing appropriate fallback behavior.

    Args:
        repo_path: Path to the git repository
        from_commit: The commit we last imported from
        to_commit: The new commit to update to

    Returns:
        Tuple of (from_commit, to_commit, status) where status is one of:
        - 'normal': Clean linear history, safe to diff
        - 'rewritten': History diverged but merge-base found
        - 'reimport_required': from_commit gone, full reimport needed
    """
    # Check if from_commit still exists
    if not is_commit_reachable(repo_path, from_commit):
        # History was rewritten - from_commit no longer exists
        current = get_current_commit(repo_path)
        if current:
            return (current, to_commit, "reimport_required")
        return (None, to_commit, "reimport_required")

    # Check if from_commit is ancestor of to_commit (clean fast-forward)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", from_commit, to_commit], capture_output=True
        )
        if result.returncode != 0:
            # from_commit is not ancestor - possible rebase
            merge_base = get_merge_base(repo_path, from_commit, to_commit)
            if merge_base:
                return (merge_base, to_commit, "rewritten")
            return (None, to_commit, "reimport_required")
    except subprocess.CalledProcessError:
        pass

    return (from_commit, to_commit, "normal")


def hash_file(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
