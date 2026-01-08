#!/usr/bin/env python3
"""
url_utils.py - URL credential handling utilities

Provides:
- URL credential redaction for safe logging
- Cross-platform GIT_ASKPASS authentication helpers
- JSON sanitization for stored provenance/registry
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import urlparse, urlunparse

# =============================================================================
# URL Credential Redaction
# =============================================================================


def redact_url_credentials(url: str) -> str:
    """
    Redact username:password from URLs before logging/printing.

    Example:
        https://user:token@example.com/org/repo.git
        → https://***:***@example.com/org/repo.git
    """
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Replace credentials with redacted markers
            netloc = parsed.netloc
            if "@" in netloc:
                creds, host = netloc.rsplit("@", 1)
                netloc = "***:***@" + host
            redacted = parsed._replace(netloc=netloc)
            return urlunparse(redacted)
        return url
    except Exception:
        # If parsing fails, do basic regex redaction
        return re.sub(r"://[^:]+:[^@]+@", "://***:***@", url)


# Pattern to match URL-like field names
URL_FIELD_PATTERNS = re.compile(r"(url|origin|source|remote|endpoint)", re.IGNORECASE)


def sanitize_json_urls(data: Any) -> Any:
    """
    Recursively sanitize URL-like fields in JSON-serializable data.

    Applies redact_url_credentials() to any string value in a field
    whose name matches common URL patterns (url, origin, source, etc.).
    """
    if isinstance(data, dict):
        return {
            k: (
                redact_url_credentials(v)
                if isinstance(v, str) and URL_FIELD_PATTERNS.search(k)
                else sanitize_json_urls(v)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_json_urls(item) for item in data]
    else:
        return data


# =============================================================================
# Cross-Platform GIT_ASKPASS Authentication
# =============================================================================

# Python askpass script content - reads credentials from environment
ASKPASS_SCRIPT = '''#!/usr/bin/env python3
"""GIT_ASKPASS helper - reads credentials from environment variables."""
import os
import sys

prompt = sys.argv[1] if len(sys.argv) > 1 else ""
prompt_lower = prompt.lower()

if "username" in prompt_lower or "login" in prompt_lower:
    print(os.environ.get("GIT_AUTH_USERNAME", "x-access-token"))
elif "password" in prompt_lower or "token" in prompt_lower:
    print(os.environ.get("GIT_AUTH_TOKEN", ""))
else:
    # Unknown prompt - return token as fallback (some git versions use generic prompts)
    print(os.environ.get("GIT_AUTH_TOKEN", ""))
'''


def _create_askpass_scripts() -> Tuple[Path, Path]:
    """
    Create askpass helper scripts for cross-platform GIT_ASKPASS.

    Returns (wrapper_path, tmp_dir) - wrapper is what GIT_ASKPASS points to.
    Caller is responsible for cleaning up tmp_dir after use.

    NOTE: Token is NOT passed here - it's provided via GIT_AUTH_TOKEN env var
    at clone time, keeping credentials out of script bodies and function args.

    CRITICAL: GIT_ASKPASS must point to a single executable path (no arguments).
    On POSIX: We create a shell wrapper that invokes the Python script.
    On Windows: We create a .cmd wrapper that invokes the Python script.

    IMPORTANT: Wrappers use sys.executable (the current Python interpreter) instead
    of relying on 'python' or 'python3' being on PATH. This ensures it works in:
    - Virtual environments (venv/conda)
    - CI environments with minimal PATH
    - Windows where 'python3' may not exist
    """
    # Create temp directory to hold both scripts
    tmp_dir = Path(tempfile.mkdtemp(prefix="git_askpass_"))

    # Get the current Python interpreter path (works in venvs, CI, etc.)
    python_exe = sys.executable

    # Python askpass script - reads credentials from environment
    python_script = tmp_dir / "askpass.py"
    python_script.write_text(ASKPASS_SCRIPT, encoding="utf-8")

    if sys.platform == "win32":  # pragma: win32-only
        # Windows: Create .cmd wrapper script
        # Use python_exe (sys.executable) to ensure we use the same Python running MINE
        wrapper = tmp_dir / "askpass.cmd"
        wrapper.write_text(f'@echo off\n"{python_exe}" "{python_script}" %*\n', encoding="utf-8")
    else:  # pragma: posix-only
        # POSIX: Create shell wrapper script
        # Use python_exe (sys.executable) to ensure we use the same Python running MINE
        wrapper = tmp_dir / "askpass.sh"
        wrapper.write_text(f'#!/bin/sh\nexec "{python_exe}" "{python_script}" "$@"\n', encoding="utf-8")
        # Make both executable on POSIX
        os.chmod(wrapper, stat.S_IRWXU)
        os.chmod(python_script, stat.S_IRWXU)

    return wrapper, tmp_dir


def clone_with_token_askpass(
    url: str, dest: Path, token: str, depth: int = 1, extra_args: Optional[list] = None, verbose: bool = False
) -> bool:
    """
    Clone using GIT_ASKPASS to avoid token in URL/process list.

    IMPORTANT: Git prompts separately for Username and Password.
    Uses a wrapper script approach for cross-platform compatibility.

    The wrapper script is necessary because GIT_ASKPASS must be a single
    executable path—it cannot include command-line arguments.

    Args:
        url: Repository URL to clone
        dest: Destination path
        token: Authentication token
        depth: Clone depth (default 1 for shallow clone)
        extra_args: Additional git clone arguments
        verbose: Print progress to stderr

    Returns:
        True if clone succeeded, False otherwise
    """
    wrapper_path, tmp_dir = _create_askpass_scripts()

    try:
        env = os.environ.copy()
        # GIT_ASKPASS points to wrapper script (single path, no arguments)
        env["GIT_ASKPASS"] = str(wrapper_path)
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Pass credentials via env vars (NOT in script body or argv)
        env["GIT_AUTH_TOKEN"] = token
        env["GIT_AUTH_USERNAME"] = "x-access-token"

        cmd = ["git", "clone", "--depth", str(depth)]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend([url, str(dest)])

        subprocess.run(cmd, check=True, capture_output=not verbose, env=env)
        return True
    except subprocess.CalledProcessError as e:
        if verbose:
            # IMPORTANT: Never print env or credential-bearing strings
            print(f"Clone failed with exit code {e.returncode}", file=sys.stderr)
        return False
    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(tmp_dir)
        except OSError:
            pass


def clone_with_auth_fallback(
    url: str,
    dest: Path,
    token: Optional[str] = None,
    depth: int = 1,
    extra_args: Optional[list] = None,
    verbose: bool = False,
) -> bool:
    """
    Clone with fallback chain: gh CLI → wrapper askpass → plain clone.

    This is the recommended approach for cross-platform authenticated cloning.
    On Windows, gh CLI is preferred as it handles auth most reliably.

    Args:
        url: Repository URL to clone
        dest: Destination path
        token: Optional authentication token (from GITHUB_TOKEN env if not provided)
        depth: Clone depth (default 1 for shallow clone)
        extra_args: Additional git clone arguments
        verbose: Print progress to stderr

    Returns:
        True if clone succeeded, False otherwise
    """
    # Get token from env if not provided
    if token is None:
        token = os.environ.get("GITHUB_TOKEN", "")

    # Try gh CLI first (handles auth via its own credential store)
    if shutil.which("gh"):
        try:
            # Pass token via GH_TOKEN for headless environments
            # (gh auth login may not have been run)
            gh_env = os.environ.copy()
            if token:
                gh_env["GH_TOKEN"] = token

            cmd = ["gh", "repo", "clone", url, str(dest), "--"]
            cmd.extend(["--depth", str(depth)])
            if extra_args:
                cmd.extend(extra_args)

            subprocess.run(cmd, check=True, capture_output=not verbose, env=gh_env)
            return True
        except subprocess.CalledProcessError:
            if verbose:
                print("gh clone failed, falling back to git", file=sys.stderr)

    # Fallback to wrapper askpass (cross-platform)
    if token:
        if clone_with_token_askpass(url, dest, token, depth, extra_args, verbose):
            return True

    # Last resort: plain git clone (no auth)
    try:
        cmd = ["git", "clone", "--depth", str(depth)]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend([url, str(dest)])

        subprocess.run(cmd, check=True, capture_output=not verbose)
        return True
    except subprocess.CalledProcessError:
        return False
