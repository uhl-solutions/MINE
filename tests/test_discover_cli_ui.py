"""
Tests for CLI UI formatting functions.

Tests the format_* functions in discover/cli_ui.py.
"""

import sys
import io
from pathlib import Path

import pytest

# Setup path for modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mine-mine" / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

from discover.cli_ui import (
    format_discovery_result,
    format_list_result,
    format_register_result,
    format_integration_summary,
    print_discovery_result,
    print_list_result,
    print_register_result,
)
from discover.types import DiscoveryResult, DiscoveryStats


class TestFormatDiscoveryResult:
    """Tests for format_discovery_result()."""

    def test_format_empty_discovery(self):
        """Empty discovery should show zero integrations."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            stats=DiscoveryStats(locations_scanned=3, candidates_found=0, integrations_added=0),
        )
        output = format_discovery_result(result)

        assert "Discovered 0 integration(s)" in output
        assert "Locations scanned: 3" in output

    def test_format_discovery_with_integrations(self):
        """Discovery with integrations should show count."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            stats=DiscoveryStats(locations_scanned=2, candidates_found=5, integrations_added=3),
        )
        output = format_discovery_result(result)

        assert "Discovered 3 integration(s)" in output
        assert "Candidates found: 5" in output

    def test_format_discovery_dry_run(self):
        """Dry-run should show DRY-RUN tag."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            dry_run=True,
            stats=DiscoveryStats(),
        )
        output = format_discovery_result(result)

        assert "[DRY-RUN]" in output

    def test_format_discovery_with_errors(self):
        """Errors should be formatted properly."""
        result = DiscoveryResult(
            ok=False,
            exit_code=2,
            errors=["Invalid config", "Path not found"],
        )
        output = format_discovery_result(result)

        assert "Invalid config" in output
        assert "Path not found" in output

    def test_format_discovery_with_warnings(self):
        """Warnings should be listed."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            stats=DiscoveryStats(),
            warnings=["Possible duplicate", "Stale marker"],
        )
        output = format_discovery_result(result)

        assert "Warnings:" in output
        assert "Possible duplicate" in output
        assert "Stale marker" in output


class TestFormatListResult:
    """Tests for format_list_result()."""

    def test_format_empty_list(self):
        """Empty list should show help message."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            integrations=[],
        )
        output = format_list_result(result)

        assert "No integrations found" in output
        assert "--discover" in output

    def test_format_list_with_integrations(self):
        """List with integrations should show grouped by scope."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            integrations=[
                {
                    "id": "user-test-repo",
                    "target_scope": "user",
                    "source_url": "https://github.com/test/repo",
                    "artifact_mappings": [{"type": "command"}, {"type": "command"}],
                },
                {
                    "id": "project-other",
                    "target_scope": "project",
                    "source_url": "https://github.com/other/repo",
                    "artifact_mappings": [],
                    "markers": [{"type": "settings"}, {"type": "claude_md"}],
                },
            ],
        )
        output = format_list_result(result)

        assert "Found 2 integration(s)" in output
        assert "User-scope integrations:" in output
        assert "Project-scope integrations:" in output
        assert "user-test-repo" in output
        assert "project-other" in output

    def test_format_list_errors(self):
        """Errors in list should be formatted."""
        result = DiscoveryResult(
            ok=False,
            exit_code=4,
            errors=["Registry corrupted"],
        )
        output = format_list_result(result)

        assert "Registry corrupted" in output


class TestFormatRegisterResult:
    """Tests for format_register_result()."""

    def test_format_register_success(self):
        """Successful register should show check mark."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            integrations=[
                {
                    "id": "user-new-repo",
                    "source_url": "https://github.com/new/repo",
                    "target_repo_path": "~/.claude",
                }
            ],
        )
        output = format_register_result(result)

        assert "✓" in output
        assert "user-new-repo" in output
        assert "github.com/new/repo" in output

    def test_format_register_dry_run(self):
        """Dry-run register should show DRY-RUN tag."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            dry_run=True,
            integrations=[{"id": "test"}],
        )
        output = format_register_result(result)

        assert "[DRY-RUN]" in output

    def test_format_register_error(self):
        """Register error should be formatted."""
        result = DiscoveryResult(
            ok=False,
            exit_code=1,
            errors=["Source not accessible"],
        )
        output = format_register_result(result)

        assert "Source not accessible" in output


class TestFormatIntegrationSummary:
    """Tests for format_integration_summary()."""

    def test_format_integration_basic(self):
        """Basic integration should show ID and source."""
        integration = {
            "id": "user-my-repo",
            "source_url": "https://github.com/me/repo",
            "artifact_mappings": [{"type": "command"}, {"type": "agent"}],
        }
        output = format_integration_summary(integration)

        assert "user-my-repo" in output
        assert "github.com/me/repo" in output

    def test_format_integration_verbose(self):
        """Verbose mode should show more details."""
        integration = {
            "id": "user-my-repo",
            "source_url": "https://github.com/me/repo",
            "import_time": "2025-01-01T12:00:00",
            "artifact_mappings": [{"type": "skill"}],
        }
        output = format_integration_summary(integration, verbose=True)

        assert "user-my-repo" in output
        assert "Imported:" in output
        assert "Artifacts:" in output

    def test_format_integration_with_markers_only(self):
        """Integration with only markers should show marker count."""
        integration = {
            "id": "project-test",
            "source_path": "/path/to/repo",
            "artifact_mappings": [],
            "markers": [{"type": "settings"}, {"type": "hooks"}],
        }
        output = format_integration_summary(integration)

        assert "project-test" in output
        assert "2 marker(s)" in output


class TestPrintFunctions:
    """Tests for print_* functions with custom streams."""

    def test_print_discovery_result_to_stream(self):
        """print_discovery_result should write to provided stream."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            stats=DiscoveryStats(integrations_added=1),
        )
        stream = io.StringIO()
        print_discovery_result(result, stream=stream)

        output = stream.getvalue()
        assert "Discovered 1 integration" in output

    def test_print_list_result_to_stream(self):
        """print_list_result should write to provided stream."""
        result = DiscoveryResult(ok=True, exit_code=0, integrations=[])
        stream = io.StringIO()
        print_list_result(result, stream=stream)

        output = stream.getvalue()
        assert "No integrations found" in output

    def test_print_register_result_to_stream(self):
        """print_register_result should write to provided stream."""
        result = DiscoveryResult(
            ok=True,
            exit_code=0,
            integrations=[{"id": "test", "source_url": "http://x", "target_repo_path": "/y"}],
        )
        stream = io.StringIO()
        print_register_result(result, stream=stream)

        output = stream.getvalue()
        assert "test" in output
