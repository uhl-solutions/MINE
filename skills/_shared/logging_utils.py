"""
Logging utilities for MINE skills.

Provides a consistent logging interface with support for:
- --verbose (DEBUG level)
- --quiet (ERROR only)
- Default (INFO level with clean user-friendly output)

Usage:
    from logging_utils import setup_logging, get_logger

    # In main():
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    logger.debug("Detailed debug info")
    logger.info("Normal user-facing message")
    logger.warning("Warning message")
    logger.error("Error message")
"""

import argparse
import logging
import sys
from typing import Optional


# Custom log format for different levels
class MINEFormatter(logging.Formatter):
    """Custom formatter that produces clean output for normal use and detailed output for debug."""

    FORMATS = {
        logging.DEBUG: "[DEBUG] %(name)s: %(message)s",
        logging.INFO: "%(message)s",
        logging.WARNING: "WARNING: %(message)s",
        logging.ERROR: "ERROR: %(message)s",
        logging.CRITICAL: "CRITICAL: %(message)s",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# Module-level state for the root logger
_configured = False
_root_logger_name = "mine"


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure logging for MINE skills.

    Args:
        verbose: Enable DEBUG level logging
        quiet: Suppress all but ERROR level messages
        log_file: Optional file path to write logs to

    Returns:
        The root MINE logger

    Note:
        - quiet takes precedence over verbose
        - Default level is INFO
    """
    global _configured

    # Determine log level
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Get or create the root logger
    logger = logging.getLogger(_root_logger_name)
    logger.setLevel(level)

    # Remove existing handlers if reconfiguring
    if _configured:
        logger.handlers.clear()

    # Console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(MINEFormatter())
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        A logger configured as a child of the MINE root logger

    Example:
        logger = get_logger(__name__)
        logger.info("Processing file...")
    """
    # If name starts with "mine" or "_shared", use as-is
    # Otherwise, prefix with mine.
    if name.startswith(_root_logger_name) or name.startswith("_shared"):
        return logging.getLogger(name)
    return logging.getLogger(f"{_root_logger_name}.{name}")


def add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add standard --verbose and --quiet arguments to a parser.

    Args:
        parser: The argument parser to add arguments to

    Example:
        parser = argparse.ArgumentParser()
        add_logging_arguments(parser)
        args = parser.parse_args()
        setup_logging(verbose=args.verbose, quiet=args.quiet)
    """
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (debug level)",
    )
    verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )


def log_action(action: str, target: str, dry_run: bool = False) -> None:
    """
    Log an action being taken on a target.

    Args:
        action: The action being performed (e.g., "Creating", "Updating", "Deleting")
        target: The target of the action (e.g., a file path)
        dry_run: If True, prefix with [DRY-RUN]

    Example:
        log_action("Creating", "/path/to/file.md", dry_run=True)
        # Output: [DRY-RUN] Creating /path/to/file.md
    """
    logger = get_logger("mine")
    prefix = "[DRY-RUN] " if dry_run else ""
    logger.info(f"{prefix}{action} {target}")


def log_skip(reason: str, target: str) -> None:
    """
    Log a skip action with reason.

    Args:
        reason: Why the target is being skipped
        target: The target being skipped

    Example:
        log_skip("Already exists", "/path/to/file.md")
        # Output: SKIP: /path/to/file.md (Already exists)
    """
    logger = get_logger("mine")
    logger.info(f"SKIP: {target} ({reason})")
