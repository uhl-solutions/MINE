"""
CLI argument parsing helpers for MINE skills.

Provides standardized --dry-run flag handling with backward compatibility.
"""

import argparse
from typing import Optional


class DryRunAction(argparse.Action):
    """
    Custom argparse action for --dry-run that supports both flag and value syntax.

    Supports:
      --dry-run          -> True (flag style, preferred)
      --dry-run=true     -> True (deprecated value style)
      --dry-run=false    -> False (deprecated value style)
      --no-dry-run       -> False (explicit disable, for Python 3.9+)

    Default is True when not specified.
    """

    def __init__(
        self,
        option_strings,
        dest,
        nargs=None,
        const=None,
        default=None,
        type=None,
        choices=None,
        required=False,
        help=None,
        metavar=None,
    ):
        # Allow nargs='?' for optional value support
        if nargs is None:
            nargs = "?"
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=True,  # Value when flag used without argument
            default=True if default is None else default,  # Default when not specified
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        # Handle different input scenarios
        if isinstance(values, str):
            # Backward compatibility: --dry-run=true or --dry-run=false
            lower_val = values.lower()
            if lower_val in ("true", "1", "yes", "on"):
                result = True
                # Only warn for explicit value, not for flag usage
                if option_string and "=" in (option_string + "=" + values if values else ""):
                    pass  # This is the deprecated style but we don't warn to avoid noise
            elif lower_val in ("false", "0", "no", "off"):
                result = False
            else:
                # Any other string is treated as True (consistent with old behavior)
                result = True
        elif isinstance(values, bool):
            result = values

        setattr(namespace, self.dest, result)


class NoDryRunAction(argparse.Action):
    """
    Custom argparse action for --no-dry-run to explicitly disable dry-run mode.
    """

    def __init__(
        self,
        option_strings,
        dest,
        nargs=None,
        const=None,
        default=None,
        type=None,
        choices=None,
        required=False,
        help=None,
        metavar=None,
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,  # No arguments
            const=False,
            default=argparse.SUPPRESS,  # Don't set if not used
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, False)


def add_dry_run_argument(
    parser: argparse.ArgumentParser, default: bool = True, help_text: Optional[str] = None
) -> None:
    """
    Add standardized --dry-run and --no-dry-run arguments to a parser.

    Args:
        parser: The argument parser to add arguments to
        default: Default value when neither flag is used (default: True)
        help_text: Custom help text (optional)

    Example:
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        # Now supports: --dry-run, --dry-run=true, --dry-run=false, --no-dry-run
    """
    if help_text is None:
        help_text = "Preview changes without writing (default: true)"

    parser.add_argument(
        "--dry-run", action=DryRunAction, dest="dry_run", default=default, help=help_text, metavar="BOOL"
    )

    parser.add_argument(
        "--no-dry-run", action=NoDryRunAction, dest="dry_run", help="Execute changes (equivalent to --apply)"
    )


def add_apply_argument(parser: argparse.ArgumentParser, help_text: Optional[str] = None) -> None:
    """
    Add standardized --apply argument as an alias for --dry-run=false.

    Args:
        parser: The argument parser to add the argument to
        help_text: Custom help text (optional)
    """
    if help_text is None:
        help_text = "Apply changes (equivalent to --no-dry-run)"

    parser.add_argument("--apply", action="store_true", dest="apply_changes", help=help_text)


def resolve_dry_run(args: argparse.Namespace) -> bool:
    """
    Resolve the effective dry-run state from parsed arguments.

    Handles the interaction between --dry-run, --no-dry-run, and --apply flags.

    Args:
        args: Parsed arguments namespace

    Returns:
        bool: True if in dry-run mode, False if changes should be applied

    Priority (highest to lowest):
        1. --apply (always disables dry-run)
        2. --no-dry-run (disables dry-run)
        3. --dry-run=false (deprecated, disables dry-run)
        4. --dry-run or --dry-run=true (enables dry-run)
        5. Default (True - dry-run enabled)
    """
    # Check for --apply flag
    apply_changes = getattr(args, "apply_changes", False)

    # Get dry_run value (defaults to True if not set)
    dry_run = getattr(args, "dry_run", True)

    # --apply takes precedence and disables dry-run
    if apply_changes:
        return False

    return dry_run


def get_dry_run_prefix(dry_run: bool) -> str:
    """
    Get a prefix string for output messages based on dry-run state.

    Args:
        dry_run: Current dry-run state

    Returns:
        str: "[DRY-RUN] " if in dry-run mode, empty string otherwise
    """
    return "[DRY-RUN] " if dry_run else ""


def print_dry_run_notice(dry_run: bool) -> None:
    """
    Print a notice about the current dry-run state.

    Args:
        dry_run: Current dry-run state
    """
    if dry_run:
        print("\n[DRY-RUN] No files will be modified. Use --apply or --no-dry-run to execute.\n")
