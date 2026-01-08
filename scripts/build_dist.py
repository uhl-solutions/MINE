#!/usr/bin/env python3
"""
build_dist.py - Build distribution package from dist-manifest.json

Creates a clean "two skills only" distribution by:
1. Reading the dist-manifest.json for include/exclude patterns
2. Copying only allowlisted files to a dist directory
3. Enforcing exclusions (no tests, CI, coverage artifacts)
4. Optionally creating a ZIP archive

Usage:
    python build_dist.py [--output dist/] [--zip] [--verify]

This script ensures the final distribution contains only the files
specified in dist-manifest.json, making "final repo contains only
necessary files" verifiable instead of manual.
"""

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set
import zipfile

from _logging import setup_logging, get_logger


# Fixed timestamp for reproducible builds (Jan 1, 2020 00:00:00)
REPRODUCIBLE_TIMESTAMP = (2020, 1, 1, 0, 0, 0)

# Fixed permission modes for reproducibility
DEFAULT_FILE_MODE = 0o644
EXECUTABLE_FILE_MODE = 0o755


def load_manifest(manifest_path: Path) -> dict:
    """Load and validate the dist-manifest.json file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Validate required fields
    if "include" not in manifest:
        raise ValueError("Manifest missing 'include' field")
    if "exclude" not in manifest:
        raise ValueError("Manifest missing 'exclude' field")

    return manifest


def expand_glob_pattern(base_dir: Path, pattern: str) -> List[Path]:
    """Expand a glob pattern relative to base_dir."""
    # Handle ** patterns
    if "**" in pattern:
        return list(base_dir.glob(pattern))
    else:
        return list(base_dir.glob(pattern))


def matches_any_pattern(path: Path, patterns: List[str], base_dir: Path) -> bool:
    """Check if path matches any of the given glob patterns."""
    # Get relative path for pattern matching
    rel_path = None
    try:
        rel_path = path.relative_to(base_dir)
        rel_str = str(rel_path)
    except ValueError:
        rel_str = str(path)

    for pattern in patterns:
        # Handle directory patterns
        if pattern.endswith("/**"):
            dir_pattern = pattern[:-3]
            if rel_str.startswith(dir_pattern) or fnmatch.fnmatch(rel_str, pattern):
                return True
        elif fnmatch.fnmatch(rel_str, pattern):
            return True
        elif fnmatch.fnmatch(path.name, pattern):
            return True
        # Check if any parent directory matches (only if rel_path is valid)
        if rel_path is not None:
            for parent in rel_path.parents:
                if fnmatch.fnmatch(str(parent), pattern.rstrip("/**")):
                    return True

    return False


def collect_files(base_dir: Path, include_patterns: List[str], exclude_patterns: List[str]) -> List[Path]:
    """Collect files matching include patterns but not exclude patterns."""
    included_files: Set[Path] = set()

    # Expand include patterns
    for pattern in include_patterns:
        for path in expand_glob_pattern(base_dir, pattern):
            if path.is_file():
                included_files.add(path)
            elif path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        included_files.add(child)

    # Filter out excluded files
    filtered_files = []
    for path in sorted(included_files):
        if not matches_any_pattern(path, exclude_patterns, base_dir):
            filtered_files.append(path)

    return filtered_files


def copy_files(files: List[Path], source_dir: Path, dest_dir: Path, verbose: bool = False) -> int:
    """Copy files to destination directory, preserving structure."""
    copied = 0

    for source_path in files:
        try:
            rel_path = source_path.relative_to(source_dir)
        except ValueError:
            continue

        dest_path = dest_dir / rel_path

        # Create parent directories
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(source_path, dest_path)
        copied += 1

        if verbose:
            get_logger(__name__).debug(f"Copied: {rel_path}")

    return copied


def create_reproducible_zip(source_dir: Path, output_path: Path, verbose: bool = False) -> None:
    """Create a ZIP archive with deterministic ordering and timestamps."""
    all_files = sorted(source_dir.rglob("*"))

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in all_files:
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)

                # Read file content
                data = file_path.read_bytes()

                # Create ZipInfo with fixed timestamp
                info = zipfile.ZipInfo(str(arcname), date_time=REPRODUCIBLE_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED

                # Set deterministic permission bits
                import stat

                if file_path.stat().st_mode & stat.S_IXUSR:
                    mode = EXECUTABLE_FILE_MODE
                else:
                    mode = DEFAULT_FILE_MODE
                info.external_attr = (mode | stat.S_IFREG) << 16

                zf.writestr(info, data)

                if verbose:
                    get_logger(__name__).debug(f"Added to ZIP: {arcname}")

    if verbose:
        get_logger(__name__).debug(f"Created reproducible ZIP: {output_path}")


def verify_distribution(dist_dir: Path, manifest: dict) -> bool:
    """Verify that distribution contains only allowed files."""
    exclude_patterns = manifest.get("exclude", [])
    violations = []

    for path in dist_dir.rglob("*"):
        if path.is_file():
            rel_path = path.relative_to(dist_dir)
            rel_str = str(rel_path)

            # Check for excluded patterns that shouldn't be present
            for pattern in exclude_patterns:
                if pattern.endswith("/**"):
                    dir_pattern = pattern[:-3]
                    if rel_str.startswith(dir_pattern):
                        violations.append((rel_str, pattern))
                        break
                elif fnmatch.fnmatch(rel_str, pattern):
                    violations.append((rel_str, pattern))
                    break
                elif fnmatch.fnmatch(path.name, pattern):
                    violations.append((rel_str, pattern))
                    break

    if violations:
        logger = get_logger(__name__)
        logger.error("VERIFICATION FAILED: Found excluded files in distribution:")
        for file_path, pattern in violations:
            logger.error(f"  - {file_path} (matches exclude: {pattern})")
        return False

    return True


def compute_manifest_hash(files: List[Path], base_dir: Path) -> str:
    """Compute a hash of all file contents for reproducibility verification."""
    hasher = hashlib.sha256()

    for path in sorted(files):
        try:
            rel_path = str(path.relative_to(base_dir))
            hasher.update(rel_path.encode("utf-8"))
            hasher.update(path.read_bytes())
        except (ValueError, OSError):
            continue

    return hasher.hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description="Build distribution package from dist-manifest.json")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/dist-manifest.json"),
        help="Path to manifest file (default: config/dist-manifest.json)",
    )
    parser.add_argument("--output", type=Path, default=Path("dist"), help="Output directory (default: dist/)")
    parser.add_argument("--zip", action="store_true", help="Create a ZIP archive of the distribution")
    parser.add_argument(
        "--zip-name", type=str, default="mine-skills", help="Base name for ZIP file (default: mine-skills)"
    )
    parser.add_argument("--verify", action="store_true", help="Verify distribution after building")
    parser.add_argument("--clean", action="store_true", help="Clean output directory before building")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be copied without doing it")

    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(verbose=args.verbose, quiet=getattr(args, "quiet", False))
    logger = get_logger(__name__)

    # Determine project root (where manifest lives)
    if args.manifest.is_absolute():
        project_root = args.manifest.parent
    else:
        project_root = Path.cwd()

    manifest_path = project_root / args.manifest if not args.manifest.is_absolute() else args.manifest

    logger.info(f"Building distribution from: {project_root}")
    logger.info(f"Using manifest: {manifest_path}")
    logger.info(f"Output directory: {args.output}")

    # Load manifest
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to load manifest: {e}")
        return 1

    logger.info(f"Manifest version: {manifest.get('version', 'unknown')}")
    logger.debug(f"Include patterns: {len(manifest['include'])}")
    logger.debug(f"Exclude patterns: {len(manifest['exclude'])}")

    # Collect files
    files = collect_files(project_root, manifest["include"], manifest["exclude"])

    logger.info(f"Files to include: {len(files)}")

    if args.dry_run:
        logger.info("=== DRY RUN - Files that would be copied ===")
        for f in files:
            try:
                rel = f.relative_to(project_root)
                logger.info(f"  {rel}")
            except ValueError:
                logger.info(f"  {f}")
        logger.info("No files were copied (dry-run mode)")
        return 0

    # Clean output directory if requested
    if args.clean and args.output.exists():
        if args.verbose:
            logger.debug(f"Cleaning output directory: {args.output}")
        shutil.rmtree(args.output)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Copy files
    logger.info("Copying files...")
    copied = copy_files(files, project_root, args.output, verbose=args.verbose)
    logger.info(f"Copied {copied} files")

    # Compute content hash
    content_hash = compute_manifest_hash(files, project_root)
    logger.info(f"Content hash: {content_hash}")

    # Create ZIP if requested
    if args.zip:
        timestamp = datetime.now().strftime("%Y%m%d")
        zip_name = f"{args.zip_name}-{timestamp}-{content_hash}.zip"
        zip_path = args.output.parent / zip_name

        logger.info(f"Creating ZIP archive: {zip_path}")
        create_reproducible_zip(args.output, zip_path, verbose=args.verbose)
        logger.info(f"ZIP created: {zip_path}")
        logger.info(f"ZIP size: {zip_path.stat().st_size:,} bytes")

    # Verify if requested
    if args.verify:
        logger.info("Verifying distribution...")
        if verify_distribution(args.output, manifest):
            logger.info("VERIFICATION PASSED: Distribution contains only allowed files")
        else:
            return 1

    logger.info("Build complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
