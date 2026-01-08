#!/usr/bin/env python3
"""
test_initial_import_safety.py

Tests for AssetImporter safety features: overlap protection and re-import detection.
"""

import sys
import os
import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

# Add scripts dirs to path for imports
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "skills" / "mine" / "scripts"
UPDATE_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "skills" / "mine-mine" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(UPDATE_SCRIPTS_DIR))

from import_assets import AssetImporter
from logging_utils import setup_logging

DOC_CLAIMS = [
    "overlapping_destinations_blocked",  # Extended to initial import
]


class TestInitialImportSafety:
    @pytest.fixture
    def mock_discovery(self, tmp_path):
        """Create a mock registry with an existing integration."""
        registry_path = tmp_path / "registry.json"
        dest_path = tmp_path / "project" / ".claude" / "commands" / "existing.md"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.touch()

        mock_registry = {
            "version": "1.0",
            "integrations": {
                "existing-repo": {
                    "repo_id": "user/existing",
                    "source_url": "https://github.com/user/existing",
                    "artifact_mappings": [{"type": "command", "dest_abspath": str(dest_path.resolve())}],
                }
            },
        }
        registry_path.write_text(json.dumps(mock_registry, indent=2))
        return registry_path

    def test_overlap_with_existing_integration_blocked(self, tmp_path, mock_discovery):
        """Initial import should block if destinations overlap with existing integration."""
        # Setup importer
        importer = AssetImporter(
            source="https://github.com/user/new",
            scope="project",
            target_repo=str(tmp_path / "project"),
            dry_run=True,
            verbose=True,
        )

        # Override registry path for test
        importer.discovery.registry_path = mock_discovery
        importer.discovery.registry = json.loads(mock_discovery.read_text())

        # Mock report with overlapping artifact
        report = {
            "repo_id": "user/new",
            "source": "https://github.com/user/new",
            "detected_artifacts": [
                {
                    "type": "command",
                    "destination_suggestions": {
                        "project": ".claude/commands/existing.md"  # OVERLAP!
                    },
                }
            ],
        }

        # Act
        result = importer._import_mode(report)

        # Assert
        assert result == 4  # Overlap error code

    def test_reimport_detection_warning(self, tmp_path, mock_discovery, capsys):
        """Initial import should detect if the repo is already integrated."""
        # Ensure logging is enabled (since we bypass main)
        setup_logging(verbose=True)

        # Setup importer for the SAME repo
        importer = AssetImporter(
            source="https://github.com/user/existing",
            scope="project",
            target_repo=str(tmp_path / "project"),
            dry_run=True,
            verbose=True,
        )

        # Override registry path
        importer.discovery.registry_path = mock_discovery
        importer.discovery.registry = json.loads(mock_discovery.read_text())

        # Mock scanner to return matching repo_id
        with patch("import_assets.RepoScanner") as MockScanner:
            mock_scanner = MockScanner.return_value
            mock_scanner.scan.return_value = {
                "repo_id": "user/existing",
                "source": "https://github.com/user/existing",
                "detected_artifacts": [],
                "suggested_actions": ["import"],
            }

            # Act
            importer.import_assets()

        # Assert
        captured = capsys.readouterr()
        # Logging might go to stderr or stdout depending on configuration
        output = captured.out + captured.err
        assert "Repository already integrated as: existing-repo" in output
        assert "Suggestion: Use 'mine-mine --check'" in output

    def test_no_overlap_for_disjoint_paths(self, tmp_path, mock_discovery):
        """Initial import should proceed if paths don't overlap."""
        importer = AssetImporter(
            source="https://github.com/user/new", scope="project", target_repo=str(tmp_path / "project"), dry_run=True
        )
        importer.discovery.registry_path = mock_discovery
        importer.discovery.registry = json.loads(mock_discovery.read_text())

        report = {
            "repo_id": "user/new",
            "source": "https://github.com/user/new",
            "detected_artifacts": [
                {
                    "type": "command",
                    "destination_suggestions": {
                        "project": ".claude/commands/new_command.md"  # NO OVERLAP
                    },
                }
            ],
            "risks": [],
        }

        # Mock clone and process
        with (
            patch("import_assets.RepoScanner._clone_repo", return_value=tmp_path / "repo"),
            patch.object(importer, "_process_artifact"),
        ):
            result = importer._import_mode(report)
            assert result == 0
