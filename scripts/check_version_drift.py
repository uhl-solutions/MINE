#!/usr/bin/env python3
"""
Check for version drift between pre-commit hooks and requirements.

This script ensures that tool versions are consistent across:
- .pre-commit-config.yaml
- config/requirements-dev.txt

Usage:
    python scripts/check_version_drift.py

Exit codes:
    0 - All versions are aligned
    1 - Version drift detected
"""

import argparse
import re
import sys
from pathlib import Path

from _logging import setup_logging, get_logger


def extract_precommit_ruff_version(content: str) -> str | None:
    """Extract Ruff version from pre-commit config."""
    # Match: rev: vX.Y.Z (after ruff-pre-commit repo line)
    match = re.search(r"ruff-pre-commit.*?\n\s*rev:\s*v?(\d+\.\d+\.\d+)", content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def extract_requirements_ruff_version(content: str) -> str | None:
    """Extract Ruff version from requirements file."""
    # Match: ruff==X.Y.Z
    match = re.search(r"^ruff==(\d+\.\d+\.\d+)", content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def main() -> int:
    """Check for version drift and report findings."""
    parser = argparse.ArgumentParser(description="Check for version drift")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    root = Path(__file__).parent.parent

    precommit_path = root / ".pre-commit-config.yaml"
    requirements_path = root / "config" / "requirements-dev.txt"

    errors = []

    # Read files
    if not precommit_path.exists():
        errors.append(f"Missing: {precommit_path}")
    if not requirements_path.exists():
        errors.append(f"Missing: {requirements_path}")

    if errors:
        for error in errors:
            logger.error(error)
        return 1

    precommit_content = precommit_path.read_text()
    requirements_content = requirements_path.read_text()

    # Extract versions
    precommit_ruff = extract_precommit_ruff_version(precommit_content)
    requirements_ruff = extract_requirements_ruff_version(requirements_content)

    print("=== Version Drift Check ===")
    print()

    drift_detected = False

    # Check Ruff versions
    print("Ruff versions:")
    print(f"  .pre-commit-config.yaml: {precommit_ruff or 'NOT FOUND'}")
    print(f"  config/requirements-dev.txt: {requirements_ruff or 'NOT FOUND'}")

    if precommit_ruff is None or requirements_ruff is None:
        logger.warning("Unable to extract versions")
        drift_detected = True
    elif precommit_ruff != requirements_ruff:
        logger.warning(f"DRIFT DETECTED ({precommit_ruff} != {requirements_ruff})")
        drift_detected = True
    else:
        print(f"  STATUS: ✓ Aligned at v{precommit_ruff}")

    print()

    if drift_detected:
        logger.error("Version drift detected!")
        print()
        print("To fix:")
        print("  1. Decide on a single version (typically the latest)")
        print("  2. Update both .pre-commit-config.yaml and config/requirements-dev.txt")
        print("  3. Run: pre-commit run --all-files")
        return 1

    logger.info("✓ All versions are aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
