#!/usr/bin/env python3
"""
Install MINE skills to Claude Code configuration directory.

This script copies the MINE skills to your Claude Code setup,
supporting both user scope (~/.claude/) and custom destinations.

Usage:
    # Install to user scope (default)
    python scripts/install_skills.py

    # Preview what would be installed (dry-run)
    python scripts/install_skills.py --dry-run

    # Install to custom location
    python scripts/install_skills.py --target /path/to/claude/

    # Force overwrite existing skills
    python scripts/install_skills.py --force

Exit codes:
    0 - Installation successful
    1 - Installation failed or would fail (dry-run with conflicts)
"""

import argparse
import shutil
import sys
from pathlib import Path

from _logging import setup_logging, get_logger, add_logging_arguments


SKILLS_TO_INSTALL = ["mine", "mine-mine", "_shared"]


def get_default_target() -> Path:
    """Get the default Claude Code skills directory."""
    return Path.home() / ".claude" / "skills"


def check_existing(target: Path, skill: str) -> tuple[bool, str | None]:
    """Check if a skill already exists at target.

    Returns:
        (exists, status_message)
    """
    skill_path = target / skill
    if skill_path.exists():
        if skill_path.is_dir():
            return True, f"Directory exists: {skill_path}"
        else:
            return True, f"File exists at skill path: {skill_path}"
    return False, None


def install_skill(source: Path, target: Path, skill: str, dry_run: bool, force: bool) -> bool:
    """Install a single skill to the target directory.

    Returns:
        True if successful, False otherwise
    """
    source_path = source / "skills" / skill
    target_path = target / skill

    if not source_path.exists():
        get_logger(__name__).error(f"Source skill not found: {source_path}")
        return False

    exists, status = check_existing(target, skill)

    if exists:
        if force:
            action = "REPLACE" if not dry_run else "Would replace"
        else:
            logger = get_logger(__name__)
            logger.info(f"SKIP: {skill} - already exists at {target_path}")
            logger.info(f"       Use --force to overwrite")
            return True  # Not a failure, just skipped
    else:
        action = "INSTALL" if not dry_run else "Would install"

    get_logger(__name__).info(f"  {action}: {skill} -> {target_path}")

    if dry_run:
        return True

    # Perform the installation
    try:
        if exists and force:
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()

        shutil.copytree(source_path, target_path)
        return True
    except Exception as e:
        get_logger(__name__).error(f"Failed to install {skill}: {e}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Install MINE skills to Claude Code configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview installation
    python scripts/install_skills.py --dry-run

    # Install to default location (~/.claude/skills/)
    python scripts/install_skills.py

    # Install to project-local Claude setup
    python scripts/install_skills.py --target ./.claude/skills/

    # Reinstall/update existing skills
    python scripts/install_skills.py --force
""",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help=f"Target directory for skills (default: {get_default_target()})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be installed without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing skills",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source directory (default: repository root)",
    )
    add_logging_arguments(parser)

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    # Determine source directory
    if args.source:
        source = args.source
    else:
        source = Path(__file__).parent.parent

    # Validate source
    if not (source / "skills").exists():
        logger.error(f"Skills directory not found at {source / 'skills'}")
        return 1

    # Determine target directory
    target = args.target or get_default_target()

    # User-facing banner (intentional print for UX)
    print("=== MINE Skills Installer ===")
    print()
    print(f"Source: {source}")
    print(f"Target: {target}")
    print(f"Mode: {'DRY-RUN (preview only)' if args.dry_run else 'INSTALL'}")
    print()

    # Create target directory if needed
    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)
    elif not target.exists():
        logger.debug(f"Target directory would be created: {target}")

    # Install each skill
    success = True
    print("Skills:")
    for skill in SKILLS_TO_INSTALL:
        if not install_skill(source, target, skill, args.dry_run, args.force):
            success = False

    print()

    if args.dry_run:
        print("Dry-run complete. Run without --dry-run to install.")
        return 0

    if success:
        print("✓ Installation complete!")
        print()
        print("Next steps:")
        print("  1. Import a repository:")
        print(f"     python {target}/mine/scripts/import_assets.py --source <repo> --scope user")
        print()
        print("  2. Check for updates:")
        print(f"     python {target}/mine-mine/scripts/discover_integrations.py --discover")
        return 0
    else:
        logger.error("Installation completed with errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
