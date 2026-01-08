"""
Logging utilities for MINE scripts (repo-level tools).

This is a lightweight logging wrapper for scripts in the scripts/ directory.
It mirrors the pattern from skills/_shared/logging_utils.py but is self-contained
for use by standalone build/install tools.

Usage:
    from _logging import setup_logging, get_logger

    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)
    logger.info("Message")
"""

import argparse
import logging
import sys
from typing import Optional


class CleanFormatter(logging.Formatter):
    """Formatter that produces clean output for normal use and detailed output for debug."""

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


_configured = False
_root_logger_name = "mine.scripts"


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure logging for MINE scripts.

    Args:
        verbose: Enable DEBUG level logging
        quiet: Suppress all but ERROR level messages
        log_file: Optional file path to write logs to

    Returns:
        The root scripts logger
    """
    global _configured

    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logger = logging.getLogger(_root_logger_name)
    logger.setLevel(level)

    if _configured:
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(CleanFormatter())
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific script module."""
    if name.startswith(_root_logger_name):
        return logging.getLogger(name)
    return logging.getLogger(f"{_root_logger_name}.{name}")


def add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    """Add standard --verbose and --quiet arguments to a parser."""
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
