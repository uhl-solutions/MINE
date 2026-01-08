#!/usr/bin/env python3
"""
test_update_path_safety.py

Tests for path safety in update_integrations.py.
Verifies that registry/provenance data is treated as untrusted input.
"""

import sys
import os
import json
from pathlib import Path
import pytest

# Add shared modules to path
SHARED_DIR = Path(__file__).resolve().parent.parent / "skills" / "_shared"
MINE_MINE_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "mine-mine" / "scripts"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
if str(MINE_MINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MINE_MINE_SCRIPTS))

from path_safety import PathSafetyError

# This test file proves the following claims:
DOC_CLAIMS = [
    "path_safety_traversal_blocked",  # Update paths are validated
]


class TestRegistryPathValidation:
    """Tests that registry entries with malicious paths are blocked."""

    def test_registry_entry_with_traversal_blocked(self, tmp_path):
        """Registry entry with ../../ traversal path should be blocked."""
        # Create a mock integration with a malicious dest_abspath
        root = tmp_path / "root" / ".claude"
        root.mkdir(parents=True)

        # Import the validation function
        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        # Create a minimal registry
        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "project",
                    "target_repo_path": str(tmp_path / "root"),
                    "artifact_mappings": [
                        {
                            "source_relpath": ".claude/commands/evil.md",
                            # Malicious path trying to escape
                            "dest_abspath": str(tmp_path / "root" / ".claude" / ".." / ".." / "evil.md"),
                            "type": "command",
                        }
                    ],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]
        dest_path = Path(integration["artifact_mappings"][0]["dest_abspath"])

        # Validation should raise PathSafetyError
        with pytest.raises(PathSafetyError) as exc_info:
            updater._validate_destination_path(dest_path, integration)

        assert "traversal" in str(exc_info.value).lower() or "outside" in str(exc_info.value).lower()

    def test_path_outside_root_blocked(self, tmp_path):
        """Absolute path outside install root should be blocked."""
        root = tmp_path / "project" / ".claude"
        root.mkdir(parents=True)

        outside = tmp_path / "other_location"
        outside.mkdir()

        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "project",
                    "target_repo_path": str(tmp_path / "project"),
                    "artifact_mappings": [],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]

        # Path completely outside install root
        evil_path = outside / "malicious.md"

        with pytest.raises(PathSafetyError):
            updater._validate_destination_path(evil_path, integration)

    def test_valid_path_inside_root_allowed(self, tmp_path):
        """Valid path inside install root should be allowed."""
        root = tmp_path / "project" / ".claude"
        root.mkdir(parents=True)

        # Create a file inside root
        valid_file = root / "commands" / "good.md"
        valid_file.parent.mkdir(parents=True, exist_ok=True)
        valid_file.touch()

        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "project",
                    "target_repo_path": str(tmp_path / "project"),
                    "artifact_mappings": [],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]

        # This should NOT raise
        result = updater._validate_destination_path(valid_file, integration)
        assert result is not None


class TestUpdateScopeEnforcement:
    """Tests that updates respect scope boundaries."""

    def test_user_scope_respects_home_boundary(self, tmp_path, monkeypatch):
        """User scope updates should only write under ~/.claude."""
        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        # Mock home directory
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Create .claude dir
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir()

        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "user",
                    "artifact_mappings": [],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]

        # Path inside .claude - should work
        valid_path = claude_dir / "commands" / "test.md"
        valid_path.parent.mkdir(parents=True, exist_ok=True)
        valid_path.touch()

        result = updater._validate_destination_path(valid_path, integration)
        assert result is not None

        # Path outside .claude - should fail
        outside_path = fake_home / "Documents" / "evil.md"
        outside_path.parent.mkdir(parents=True, exist_ok=True)
        outside_path.touch()

        with pytest.raises(PathSafetyError):
            updater._validate_destination_path(outside_path, integration)

    def test_project_scope_respects_repo_boundary(self, tmp_path):
        """Project scope updates should only write under <repo>/.claude."""
        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        project_root = tmp_path / "my_project"
        project_root.mkdir()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "project",
                    "target_repo_path": str(project_root),
                    "artifact_mappings": [],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]

        # Path inside project/.claude - should work
        valid_path = claude_dir / "agents" / "helper.md"
        valid_path.parent.mkdir(parents=True, exist_ok=True)
        valid_path.touch()

        result = updater._validate_destination_path(valid_path, integration)
        assert result is not None

        # Path outside project - should fail
        outside_path = tmp_path / "other_project" / "secret.md"
        outside_path.parent.mkdir(parents=True, exist_ok=True)
        outside_path.touch()

        with pytest.raises(PathSafetyError):
            updater._validate_destination_path(outside_path, integration)


class TestSymlinkEscapeBlocked:
    """Tests that symlink-based escapes are blocked."""

    def test_symlink_escape_blocked(self, tmp_path):
        """Symlinks pointing outside root should be blocked."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        outside = tmp_path / "outside"
        outside.mkdir()
        secret_file = outside / "secret.md"
        secret_file.touch()

        # Create a symlink inside .claude pointing outside
        link = claude_dir / "escape_link"

        try:
            os.symlink(secret_file, link)
        except OSError:
            pytest.skip("Symlinks not supported on this system")

        sys.path.insert(0, str(MINE_MINE_SCRIPTS))
        import _init_shared
        from update_integrations import IntegrationUpdater

        registry_path = tmp_path / "registry.json"
        registry = {
            "integrations": {
                "test-integration": {
                    "source_url": "https://github.com/test/repo",
                    "target_scope": "project",
                    "target_repo_path": str(project_root),
                    "artifact_mappings": [],
                }
            }
        }
        registry_path.write_text(json.dumps(registry))

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=False)
        integration = registry["integrations"]["test-integration"]

        # Symlink pointing outside should be blocked
        with pytest.raises(PathSafetyError):
            updater._validate_destination_path(link, integration)
