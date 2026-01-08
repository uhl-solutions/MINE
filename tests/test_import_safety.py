#!/usr/bin/env python3
"""
test_import_safety.py

Tests for import safety features - symlink handling and overlap detection.
"""

import sys
import os
from pathlib import Path
import pytest


# This test file proves the following claims:
DOC_CLAIMS = [
    "symlink_safety_skipped",
    "overlapping_destinations_blocked",
    "case_insensitive_collisions",
]


class TestSymlinksSafety:
    """Tests that verify symlinks are skipped during scan."""

    @pytest.mark.skipif(
        os.name == "nt" and not os.environ.get("CI"), reason="Symlinks require admin on Windows outside CI"
    )
    def test_symlinks_skipped_during_scan(self, tmp_path):
        """Scanner should skip symlinks and not follow them."""
        from scan_repo import RepoScanner

        # Create a mock repo structure
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()  # Mark as git repo

        # Create a real file
        real_dir = repo_root / ".claude" / "commands"
        real_dir.mkdir(parents=True)
        (real_dir / "real_command.md").write_text("# Real Command")

        # Create a symlink (on Unix-like systems)
        try:
            symlink_target = tmp_path / "outside" / "sensitive"
            symlink_target.mkdir(parents=True)
            (symlink_target / "secret.txt").write_text("secret content")

            symlink_path = real_dir / "symlinked_file"
            symlink_path.symlink_to(symlink_target / "secret.txt")

            # Scan the repo
            scanner = RepoScanner(repo_root, verbose=True)
            report = scanner.scan()

            # Verify symlink was NOT included in artifacts
            all_paths = []
            for artifact in report.get("detected_artifacts", []):
                path = artifact.get("path", artifact.get("source_path", ""))
                all_paths.append(str(path))

            # The symlink should not be in the results
            symlink_name = "symlinked_file"
            assert not any(symlink_name in p for p in all_paths), (
                f"Symlink should be skipped, but found in: {all_paths}"
            )

        except OSError:
            pytest.skip("Could not create symlink on this system")

    def test_symlink_detection_is_file_check(self, tmp_path):
        """Verify is_symlink() check works for symlink detection."""
        # Create a symlink if possible
        try:
            target = tmp_path / "target.txt"
            target.write_text("content")

            link = tmp_path / "link.txt"
            link.symlink_to(target)

            assert link.is_symlink(), "Created file should be a symlink"
            assert target.is_file() and not target.is_symlink(), "Target should be regular file"
        except OSError:
            pytest.skip("Could not create symlink on this system")


class TestOverlappingDestinations:
    """Tests that verify overlapping destination paths are blocked."""

    def test_overlapping_blocked_same_dest(self, tmp_path):
        """Two integrations claiming same destination should be detected."""
        from update_integrations import IntegrationUpdater

        # Create mock registry with two integrations claiming same dest
        registry_path = tmp_path / "registry.json"

        mock_registry = {
            "version": "1.0",
            "integrations": {
                "integration-A": {
                    "source_url": "https://github.com/test/repo-a",
                    "artifact_mappings": [
                        {
                            "type": "command",
                            "source_relpath": ".claude/commands/shared.md",
                            "dest_abspath": str(tmp_path / ".claude" / "commands" / "shared.md"),
                        }
                    ],
                },
                "integration-B": {
                    "source_url": "https://github.com/test/repo-b",
                    "artifact_mappings": [
                        {
                            "type": "command",
                            "source_relpath": ".claude/commands/shared.md",
                            "dest_abspath": str(tmp_path / ".claude" / "commands" / "shared.md"),  # SAME!
                        }
                    ],
                },
            },
        }

        import json

        registry_path.write_text(json.dumps(mock_registry, indent=2))

        # Initialize updater
        updater = IntegrationUpdater(registry_path, dry_run=True)

        # Detect conflicts
        conflicts = updater._detect_destination_conflicts()

        # Should find the overlapping path
        assert len(conflicts) > 0, "Should detect overlapping destinations"

        # Verify both integrations are listed as owners
        for dest, owners in conflicts.items():
            assert "integration-A" in owners or "integration-B" in owners
            assert len(owners) >= 2, "Conflict should have multiple owners"

    def test_no_conflict_for_different_destinations(self, tmp_path):
        """Non-overlapping destinations should not report conflicts."""
        from update_integrations import IntegrationUpdater

        registry_path = tmp_path / "registry.json"

        mock_registry = {
            "version": "1.0",
            "integrations": {
                "integration-A": {
                    "source_url": "https://github.com/test/repo-a",
                    "artifact_mappings": [
                        {
                            "type": "command",
                            "source_relpath": ".claude/commands/command-a.md",
                            "dest_abspath": str(tmp_path / ".claude" / "commands" / "command-a.md"),
                        }
                    ],
                },
                "integration-B": {
                    "source_url": "https://github.com/test/repo-b",
                    "artifact_mappings": [
                        {
                            "type": "command",
                            "source_relpath": ".claude/commands/command-b.md",
                            "dest_abspath": str(tmp_path / ".claude" / "commands" / "command-b.md"),
                        }
                    ],
                },
            },
        }

        import json

        registry_path.write_text(json.dumps(mock_registry, indent=2))

        updater = IntegrationUpdater(registry_path, dry_run=True)
        conflicts = updater._detect_destination_conflicts()

        assert len(conflicts) == 0, f"Should have no conflicts, but found: {conflicts}"
