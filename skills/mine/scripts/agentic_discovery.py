#!/usr/bin/env python3
"""
agentic_discovery.py

Discovers agentic candidate sources in repositories beyond .claude/* directories.
Searches common locations for prompts, agent definitions, workflows, and configs.

Part of Agentic Discovery & Conversion
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Discovery patterns for agentic content
AGENTIC_LOCATIONS = {
    "root_files": [
        "README.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "PROMPTS.md",
        "AGENTS.md",
        "INSTRUCTIONS.md",
        "SYSTEM.md",
    ],
    "doc_dirs": [
        "docs/**/*.md",
        "doc/**/*.md",
        "documentation/**/*.md",
    ],
    "prompt_dirs": [
        "prompts/**/*.md",
        "prompts/**/*.txt",
        "prompt/**/*.md",
        "instructions/**/*.md",
        "system/**/*.md",
    ],
    "agent_dirs": [
        "agents/**/*.md",
        "agents/**/*.json",
        "agents/**/*.yaml",
        "agents/**/*.yml",
        "agent/**/*.md",
    ],
    "workflow_files": [
        ".github/workflows/**/*.yml",
        ".github/workflows/**/*.yaml",
    ],
    "config_files": [
        "**/*.json",
        "**/*.yaml",
        "**/*.yml",
    ],
}

# Directories to always skip
SKIP_DIRS = {
    ".git",
    ".claude",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "egg-info",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "htmlcov",
}

# File size limits
MAX_FILE_SIZE = 2_000_000  # 2MB
MAX_TOTAL_CANDIDATES = 500
MAX_SCAN_TIME = 120  # 2 minutes for agentic pass

# Keywords that suggest agentic content in config files
AGENTIC_KEYWORDS = {
    "agent",
    "agents",
    "tools",
    "functions",
    "function_calling",
    "model",
    "prompt",
    "system",
    "messages",
    "instructions",
    "assistant",
    "llm",
    "openai",
    "anthropic",
    "claude",
    "gpt",
    "langchain",
    "langgraph",
    "autogen",
    "crewai",
}


class AgenticDiscoverer:
    """Discovers agentic candidate sources in repositories."""

    def __init__(
        self,
        repo_path: Path,
        verbose: bool = False,
        max_files: int = MAX_TOTAL_CANDIDATES,
        include_globs: Optional[List[str]] = None,
        exclude_globs: Optional[List[str]] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.verbose = verbose
        self.max_files = max_files
        self.include_globs = include_globs or []
        self.exclude_globs = exclude_globs or []
        self.candidates_found = 0
        self.start_time: Optional[float] = None
        self._seen_paths: Set[str] = set()

    def _log(self, message: str):
        if self.verbose:
            print(f"[AGENTIC-DISCOVER] {message}", file=sys.stderr)

    def discover(self) -> List[Dict[str, Any]]:
        """
        Discover agentic candidate files.

        Returns list of candidate dicts:
        {
            'path': Path,
            'rel_path': str,  # Relative to repo root
            'category': str,  # 'root_file', 'prompt_dirs', 'agent_dirs', etc.
            'size_bytes': int,
        }
        """
        self.start_time = time.monotonic()
        candidates = []

        # Skip if not a directory
        if not self.repo_path.is_dir():
            self._log(f"Not a directory: {self.repo_path}")
            return candidates

        self._log(f"Starting agentic discovery in {self.repo_path}")

        # Root files (high priority)
        candidates.extend(self._scan_root_files())
        if self._check_limits():
            return candidates

        # Prompt directories
        candidates.extend(self._scan_pattern_category("prompt_dirs"))
        if self._check_limits():
            return candidates

        # Agent directories
        candidates.extend(self._scan_pattern_category("agent_dirs"))
        if self._check_limits():
            return candidates

        # Doc directories
        candidates.extend(self._scan_pattern_category("doc_dirs"))
        if self._check_limits():
            return candidates

        # Workflow files
        candidates.extend(self._scan_pattern_category("workflow_files"))
        if self._check_limits():
            return candidates

        # Config files (lowest priority, filtered by content)
        candidates.extend(self._scan_config_files())

        self._log(f"Discovery complete: {len(candidates)} candidates found")
        return candidates

    def _scan_root_files(self) -> List[Dict[str, Any]]:
        """Scan root-level files that commonly contain agentic content."""
        results = []

        for filename in AGENTIC_LOCATIONS["root_files"]:
            file_path = self.repo_path / filename
            if file_path.exists() and file_path.is_file():
                if self._is_valid_candidate(file_path):
                    candidate = self._create_candidate(file_path, "root_file")
                    if candidate:
                        results.append(candidate)
                        if self._check_limits():
                            return results

        return results

    def _scan_pattern_category(self, category: str) -> List[Dict[str, Any]]:
        """Scan files matching patterns in a category."""
        results = []

        for pattern in AGENTIC_LOCATIONS.get(category, []):
            try:
                for file_path in self.repo_path.glob(pattern):
                    if self._check_limits():
                        return results

                    # Skip if already seen
                    path_str = str(file_path.resolve())
                    if path_str in self._seen_paths:
                        continue

                    if not file_path.is_file() or file_path.is_symlink():
                        continue

                    # Skip files in excluded directories
                    if self._is_in_skip_dir(file_path):
                        continue

                    if self._is_valid_candidate(file_path):
                        candidate = self._create_candidate(file_path, category)
                        if candidate:
                            results.append(candidate)

            except (OSError, PermissionError) as e:
                self._log(f"Error scanning pattern {pattern}: {e}")
                continue

        return results

    def _scan_config_files(self) -> List[Dict[str, Any]]:
        """Scan config files, filtering by content keywords."""
        results = []

        for pattern in AGENTIC_LOCATIONS.get("config_files", []):
            try:
                for file_path in self.repo_path.glob(pattern):
                    if self._check_limits():
                        return results

                    # Skip if already seen
                    path_str = str(file_path.resolve())
                    if path_str in self._seen_paths:
                        continue

                    # Skip files in excluded directories
                    if self._is_in_skip_dir(file_path):
                        continue

                    if not file_path.is_file() or file_path.is_symlink():
                        continue

                    # Quick content check for agentic keywords
                    if self._contains_agentic_keywords(file_path):
                        if self._is_valid_candidate(file_path):
                            candidate = self._create_candidate(file_path, "config_files")
                            if candidate:
                                results.append(candidate)

            except (OSError, PermissionError) as e:
                self._log(f"Error scanning config files: {e}")
                continue

        return results

    def _is_in_skip_dir(self, file_path: Path) -> bool:
        """Check if file is in a directory that should be skipped."""
        try:
            rel_path = file_path.relative_to(self.repo_path)
            for part in rel_path.parts:
                if part in SKIP_DIRS:
                    return True
                # Skip hidden directories (except .github)
                if part.startswith(".") and part != ".github":
                    return True
        except ValueError:
            pass
        return False

    def _is_valid_candidate(self, file_path: Path) -> bool:
        """Check if file is a valid candidate (size, binary check)."""
        try:
            # Check file size
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                self._log(f"Skipping large file ({size} bytes): {file_path}")
                return False

            if size == 0:
                return False

            # Quick binary check (null byte in first 8KB)
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return False

            # Check exclude globs
            for glob in self.exclude_globs:
                if file_path.match(glob):
                    return False

            # Check include globs (if specified, must match at least one)
            if self.include_globs:
                if not any(file_path.match(glob) for glob in self.include_globs):
                    return False

            return True

        except (OSError, PermissionError):
            return False

    def _contains_agentic_keywords(self, file_path: Path) -> bool:
        """Check if file contains agentic keywords (case-insensitive)."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                # Read first 4KB only
                content = f.read(4096).lower()
                return any(kw in content for kw in AGENTIC_KEYWORDS)
        except (OSError, UnicodeDecodeError):
            return False

    def _create_candidate(self, file_path: Path, category: str) -> Optional[Dict[str, Any]]:
        """Create a candidate dictionary."""
        try:
            path_str = str(file_path.resolve())

            # Skip if already seen
            if path_str in self._seen_paths:
                return None

            self._seen_paths.add(path_str)
            self.candidates_found += 1

            # Get relative path
            try:
                rel_path = file_path.relative_to(self.repo_path)
            except ValueError:
                rel_path = file_path

            return {
                "path": file_path,
                "rel_path": str(rel_path),
                "category": category,
                "size_bytes": file_path.stat().st_size,
            }

        except (OSError, PermissionError):
            return None

    def _check_limits(self) -> bool:
        """Check if limits exceeded. Returns True if should stop."""
        if self.candidates_found >= self.max_files:
            self._log(f"Hit max files limit ({self.max_files})")
            return True

        if self.start_time and time.monotonic() - self.start_time > MAX_SCAN_TIME:
            self._log(f"Hit scan timeout ({MAX_SCAN_TIME}s)")
            return True

        return False


def discover_agentic_content(
    repo_path: str,
    verbose: bool = False,
    max_files: int = MAX_TOTAL_CANDIDATES,
    include_globs: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to discover agentic content in a repository.

    Args:
        repo_path: Path to the repository
        verbose: Enable verbose logging
        max_files: Maximum number of candidates to return
        include_globs: Optional list of glob patterns to include
        exclude_globs: Optional list of glob patterns to exclude

    Returns:
        List of candidate dictionaries
    """
    discoverer = AgenticDiscoverer(
        repo_path=Path(repo_path),
        verbose=verbose,
        max_files=max_files,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )
    return discoverer.discover()


def main():
    """CLI entry point for standalone discovery."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Discover agentic content in repositories")

    parser.add_argument("--source", required=True, help="Path to repository to scan")

    parser.add_argument("--output", help="Output file for JSON report (default: stdout)")

    parser.add_argument(
        "--max-files",
        type=int,
        default=MAX_TOTAL_CANDIDATES,
        help=f"Maximum candidates to discover (default: {MAX_TOTAL_CANDIDATES})",
    )

    parser.add_argument("--include", help="Comma-separated glob patterns to include")

    parser.add_argument("--exclude", help="Comma-separated glob patterns to exclude")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Parse globs
    include_globs = args.include.split(",") if args.include else None
    exclude_globs = args.exclude.split(",") if args.exclude else None

    # Run discovery
    candidates = discover_agentic_content(
        repo_path=args.source,
        verbose=args.verbose,
        max_files=args.max_files,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )

    # Prepare JSON output (convert Path objects to strings)
    output_candidates = [
        {
            "path": str(c["path"]),
            "rel_path": c["rel_path"],
            "category": c["category"],
            "size_bytes": c["size_bytes"],
        }
        for c in candidates
    ]

    report = {
        "source": args.source,
        "candidates_count": len(output_candidates),
        "candidates": output_candidates,
    }

    # Output
    json_output = json.dumps(report, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", errors="replace") as f:
            f.write(json_output)
        print(f"Report written to {args.output}")
    else:
        print(json_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
