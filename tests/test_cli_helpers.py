"""
Tests for CLI helpers module.

Tests the standardized --dry-run flag handling and argument resolution.
"""

import argparse
import sys
from pathlib import Path

import pytest

# Setup path for shared modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

from cli_helpers import (
    DryRunAction,
    NoDryRunAction,
    add_apply_argument,
    add_dry_run_argument,
    get_dry_run_prefix,
    print_dry_run_notice,
    resolve_dry_run,
)


class TestDryRunAction:
    """Tests for the DryRunAction custom argparse action."""

    def test_flag_without_value_sets_true(self):
        """--dry-run (no value) should set dry_run=True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_flag_with_true_value(self):
        """--dry-run=true should set dry_run=True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=true"])
        assert args.dry_run is True

    def test_flag_with_false_value(self):
        """--dry-run=false should set dry_run=False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=false"])
        assert args.dry_run is False

    def test_flag_with_uppercase_true(self):
        """--dry-run=TRUE should set dry_run=True (case insensitive)."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=TRUE"])
        assert args.dry_run is True

    def test_flag_with_uppercase_false(self):
        """--dry-run=FALSE should set dry_run=False (case insensitive)."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=FALSE"])
        assert args.dry_run is False

    def test_flag_with_yes_value(self):
        """--dry-run=yes should set dry_run=True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=yes"])
        assert args.dry_run is True

    def test_flag_with_no_value(self):
        """--dry-run=no should set dry_run=False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=no"])
        assert args.dry_run is False

    def test_flag_with_1_value(self):
        """--dry-run=1 should set dry_run=True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=1"])
        assert args.dry_run is True

    def test_flag_with_0_value(self):
        """--dry-run=0 should set dry_run=False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=0"])
        assert args.dry_run is False

    def test_default_is_true(self):
        """Not specifying --dry-run should default to True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args([])
        assert args.dry_run is True

    def test_custom_default_false(self):
        """Custom default=False should be respected."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser, default=False)
        args = parser.parse_args([])
        assert args.dry_run is False


class TestNoDryRunAction:
    """Tests for the --no-dry-run flag."""

    def test_no_dry_run_sets_false(self):
        """--no-dry-run should set dry_run=False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--no-dry-run"])
        assert args.dry_run is False

    def test_no_dry_run_overrides_dry_run(self):
        """--no-dry-run should take precedence when both are specified."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        # The last one wins in argparse
        args = parser.parse_args(["--dry-run", "--no-dry-run"])
        assert args.dry_run is False

    def test_dry_run_after_no_dry_run(self):
        """--dry-run after --no-dry-run should restore True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--no-dry-run", "--dry-run"])
        assert args.dry_run is True


class TestApplyArgument:
    """Tests for the --apply argument."""

    def test_apply_sets_apply_changes(self):
        """--apply should set apply_changes=True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--apply"])
        assert args.apply_changes is True

    def test_apply_not_specified(self):
        """Not specifying --apply should set apply_changes=False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args([])
        assert args.apply_changes is False


class TestResolveDryRun:
    """Tests for the resolve_dry_run function."""

    def test_resolve_default(self):
        """Default state (no flags) should return True (dry-run)."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args([])
        assert resolve_dry_run(args) is True

    def test_resolve_with_dry_run_flag(self):
        """--dry-run flag should return True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--dry-run"])
        assert resolve_dry_run(args) is True

    def test_resolve_with_no_dry_run(self):
        """--no-dry-run should return False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--no-dry-run"])
        assert resolve_dry_run(args) is False

    def test_resolve_with_apply(self):
        """--apply should override and return False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--apply"])
        assert resolve_dry_run(args) is False

    def test_resolve_apply_overrides_dry_run(self):
        """--apply should override --dry-run and return False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--dry-run", "--apply"])
        assert resolve_dry_run(args) is False

    def test_resolve_dry_run_false_value(self):
        """--dry-run=false should return False."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)
        args = parser.parse_args(["--dry-run=false"])
        assert resolve_dry_run(args) is False

    def test_resolve_without_apply_argument(self):
        """resolve_dry_run works when apply_changes is not set."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        # Don't add --apply argument
        args = parser.parse_args(["--dry-run"])
        assert resolve_dry_run(args) is True

    def test_resolve_without_dry_run_attribute(self):
        """resolve_dry_run defaults to True when dry_run attr is missing."""
        args = argparse.Namespace()  # Empty namespace
        assert resolve_dry_run(args) is True


class TestGetDryRunPrefix:
    """Tests for the get_dry_run_prefix function."""

    def test_prefix_when_dry_run_true(self):
        """Should return '[DRY-RUN] ' when in dry-run mode."""
        assert get_dry_run_prefix(True) == "[DRY-RUN] "

    def test_prefix_when_dry_run_false(self):
        """Should return empty string when not in dry-run mode."""
        assert get_dry_run_prefix(False) == ""


class TestPrintDryRunNotice:
    """Tests for the print_dry_run_notice function."""

    def test_notice_printed_in_dry_run_mode(self, capsys):
        """Should print notice when in dry-run mode."""
        print_dry_run_notice(True)
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "--apply" in captured.out or "--no-dry-run" in captured.out

    def test_no_notice_when_not_dry_run(self, capsys):
        """Should print nothing when not in dry-run mode."""
        print_dry_run_notice(False)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with old --dry-run=true/false syntax."""

    def test_old_style_dry_run_true(self):
        """Old style --dry-run=true should still work."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=true"])
        assert args.dry_run is True

    def test_old_style_dry_run_false(self):
        """Old style --dry-run=false should still work."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=false"])
        assert args.dry_run is False

    def test_old_style_apply_changes(self):
        """--apply with resolve_dry_run should work like old effective_dry_run."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        add_apply_argument(parser)

        # Old behavior: effective_dry_run = args.dry_run and not args.apply_changes
        args = parser.parse_args(["--dry-run", "--apply"])

        # New behavior should match
        assert resolve_dry_run(args) is False


class TestHelpText:
    """Tests for help text generation."""

    def test_custom_help_text(self):
        """Custom help text should be used."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser, help_text="Custom dry-run help")

        # Check that help action has our custom text
        for action in parser._actions:
            if action.dest == "dry_run" and action.option_strings == ["--dry-run"]:
                assert action.help == "Custom dry-run help"
                break
        else:
            pytest.fail("--dry-run action not found")

    def test_default_help_text(self):
        """Default help text should mention 'preview' or 'changes'."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)

        for action in parser._actions:
            if action.dest == "dry_run" and action.option_strings == ["--dry-run"]:
                assert "preview" in action.help.lower() or "changes" in action.help.lower()
                break


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_unknown_string_treated_as_true(self):
        """Unknown string values should be treated as True (consistent with old behavior)."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run=unknown"])
        assert args.dry_run is True

    def test_empty_string_treated_as_true(self):
        """Empty string should be treated as True."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        # Note: argparse may handle empty string differently
        # This tests the behavior when we get an empty string value
        args = parser.parse_args(["--dry-run="])
        # Empty string != "false", so it should be True
        assert args.dry_run is True

    def test_on_off_values(self):
        """'on' and 'off' should work as boolean aliases."""
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)

        args_on = parser.parse_args(["--dry-run=on"])
        assert args_on.dry_run is True

        args_off = parser.parse_args(["--dry-run=off"])
        assert args_off.dry_run is False
