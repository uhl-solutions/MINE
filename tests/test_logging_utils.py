"""Tests for the logging_utils module."""

import argparse
import logging
import sys

import pytest

# Add skills/_shared to path for imports
sys.path.insert(0, str(__file__).replace("/tests/test_logging_utils.py", "/skills/_shared"))

from logging_utils import (
    MINEFormatter,
    setup_logging,
    get_logger,
    add_logging_arguments,
    log_action,
    log_skip,
)


class TestMINEFormatter:
    """Tests for the custom log formatter."""

    def test_format_info_clean(self):
        """INFO level should produce clean output without prefix."""
        formatter = MINEFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result == "Test message"

    def test_format_error_with_prefix(self):
        """ERROR level should have ERROR: prefix."""
        formatter = MINEFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Something went wrong",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result == "ERROR: Something went wrong"

    def test_format_warning_with_prefix(self):
        """WARNING level should have WARNING: prefix."""
        formatter = MINEFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Be careful",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result == "WARNING: Be careful"

    def test_format_debug_with_name(self):
        """DEBUG level should include module name."""
        formatter = MINEFormatter()
        record = logging.LogRecord(
            name="mine.module",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Debug info",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "[DEBUG]" in result
        assert "mine.module" in result
        assert "Debug info" in result


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_default_level_is_info(self):
        """Default logging level should be INFO."""
        logger = setup_logging()
        assert logger.level == logging.INFO

    def test_verbose_enables_debug(self):
        """--verbose should enable DEBUG level."""
        logger = setup_logging(verbose=True)
        assert logger.level == logging.DEBUG

    def test_quiet_enables_error_only(self):
        """--quiet should enable ERROR level only."""
        logger = setup_logging(quiet=True)
        assert logger.level == logging.ERROR

    def test_quiet_takes_precedence_over_verbose(self):
        """When both quiet and verbose are set, quiet takes precedence."""
        logger = setup_logging(verbose=True, quiet=True)
        assert logger.level == logging.ERROR

    def test_reconfiguration_clears_handlers(self):
        """Reconfiguring should clear and replace handlers."""
        logger1 = setup_logging()
        handler_count_1 = len(logger1.handlers)

        logger2 = setup_logging(verbose=True)
        handler_count_2 = len(logger2.handlers)

        # Should not accumulate handlers
        assert handler_count_1 == handler_count_2

    def test_logging_to_file(self, tmp_path):
        """Setup logging with file output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(log_file=str(log_file))

        logger.info("Test log message")

        # Verify file creation and content
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test log message" in content
        assert "mine" in content  # Logger name


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_returns_child_logger(self):
        """Should return a child of the MINE root logger."""
        setup_logging()  # Ensure configured
        logger = get_logger("test_module")
        assert logger.name == "mine.test_module"

    def test_mine_prefixed_names_unchanged(self):
        """Names starting with 'mine' should be used as-is."""
        setup_logging()
        logger = get_logger("mine.something")
        assert logger.name == "mine.something"

    def test_shared_prefixed_names_unchanged(self):
        """Names starting with '_shared' should be used as-is."""
        setup_logging()
        logger = get_logger("_shared.module")
        assert logger.name == "_shared.module"


class TestAddLoggingArguments:
    """Tests for the add_logging_arguments function."""

    def test_adds_verbose_flag(self):
        """Should add --verbose / -v flag."""
        parser = argparse.ArgumentParser()
        add_logging_arguments(parser)

        args = parser.parse_args(["-v"])
        assert args.verbose is True

        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    def test_adds_quiet_flag(self):
        """Should add --quiet / -q flag."""
        parser = argparse.ArgumentParser()
        add_logging_arguments(parser)

        args = parser.parse_args(["-q"])
        assert args.quiet is True

        args = parser.parse_args(["--quiet"])
        assert args.quiet is True

    def test_verbose_and_quiet_mutually_exclusive(self):
        """--verbose and --quiet should be mutually exclusive."""
        parser = argparse.ArgumentParser()
        add_logging_arguments(parser)

        with pytest.raises(SystemExit):
            parser.parse_args(["--verbose", "--quiet"])


class TestLogAction:
    """Tests for the log_action helper."""

    def test_log_action_normal(self, caplog):
        """Should log action without dry-run prefix."""
        setup_logging()
        with caplog.at_level(logging.INFO):
            log_action("Creating", "/path/to/file.md", dry_run=False)
        assert "Creating /path/to/file.md" in caplog.text
        assert "[DRY-RUN]" not in caplog.text

    def test_log_action_dry_run(self, caplog):
        """Should log action with dry-run prefix."""
        setup_logging()
        with caplog.at_level(logging.INFO):
            log_action("Creating", "/path/to/file.md", dry_run=True)
        assert "[DRY-RUN] Creating /path/to/file.md" in caplog.text


class TestLogSkip:
    """Tests for the log_skip helper."""

    def test_log_skip_with_reason(self, caplog):
        """Should log skip with reason in parentheses."""
        setup_logging()
        with caplog.at_level(logging.INFO):
            log_skip("Already exists", "/path/to/file.md")
        assert "SKIP: /path/to/file.md (Already exists)" in caplog.text
