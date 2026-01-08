#!/usr/bin/env python3
"""
test_file_lifecycle.py

Tests for New/Deleted File Lifecycle (Phase 1, Item #11, #12).
Verifies auto_import_new and delete_policy logic.
"""

import sys
import json
import subprocess
from pathlib import Path
import os
import shutil
import pytest


from update_integrations import IntegrationUpdater
from git_helpers import hash_file

DOC_CLAIMS = ["local_mods_protected"]


def _write_registry(registry_path: Path, integrations: dict) -> None:
    registry_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "config": {"search_roots": [], "auto_track": True, "ask_confirmation": False},
                "integrations": integrations,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


class TestFileLifecycle:
    @pytest.fixture
    def setup_repo(self, tmp_path):
        """Setup a source repo and install dir."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        install_root = tmp_path / "install"
        install_root.mkdir()
        (install_root / ".claude").mkdir()

        return repo, install_root

    def test_auto_import_new(self, setup_repo, tmp_path):
        repo, install_root = setup_repo

        # Initial commit
        (repo / "existing.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        # New commit with new file
        (repo / "new_file.txt").write_text("new content")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add new"], cwd=repo, check=True, capture_output=True)

        # Setup registry
        registry_path = tmp_path / "registry.json"
        integrations = {
            "test-new": {
                "source_url": str(repo),
                "target_scope": "project",  # Simplifies path calc
                "target_repo_path": str(install_root),
                "last_import_commit": "HEAD^",  # Treat as imported at prev commit
                "artifact_mappings": [
                    # Empty or containing only existing
                    {"source_relpath": "existing.txt", "dest_abspath": str(install_root / ".claude" / "existing.txt")}
                ],
            }
        }
        _write_registry(registry_path, integrations)

        # Test with auto_import_new=True
        updater = IntegrationUpdater(registry_path=registry_path, dry_run=False, verbose=True, auto_import_new=True)

        updates = updater.check_updates("test-new")
        assert len(updates) == 1

        # Apply
        updater.apply_update(updates[0])

        # Verify new file exists
        new_dest = install_root / ".claude" / "new_file.txt"
        assert new_dest.exists()
        assert new_dest.read_text() == "new content"

        # Verify mapping added (reload registry)
        with open(registry_path) as f:
            reg = json.load(f)
        mappings = reg["integrations"]["test-new"]["artifact_mappings"]
        assert any(m["source_relpath"] == "new_file.txt" for m in mappings)

    def test_auto_import_new_off(self, setup_repo, tmp_path):
        repo, install_root = setup_repo
        (repo / "new_file.txt").write_text("new content")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add new"], cwd=repo, check=True, capture_output=True)

        registry_path = tmp_path / "registry.json"
        integrations = {
            "test-no-new": {
                "source_url": str(repo),
                "target_scope": "project",
                "target_repo_path": str(install_root),
                "last_import_commit": "HEAD^",  # Pretend new file is new
                "artifact_mappings": [],
            }
        }
        _write_registry(registry_path, integrations)

        updater = IntegrationUpdater(registry_path=registry_path, dry_run=False, verbose=True, auto_import_new=False)

        updates = updater.check_updates("test-no-new")
        updater.apply_update(updates[0])

        new_dest = install_root / ".claude" / "new_file.txt"
        assert not new_dest.exists()

    def test_delete_policy_hard(self, setup_repo, tmp_path):
        repo, install_root = setup_repo

        # Setup existing file
        file_path = repo / "todelete.txt"
        file_path.write_text("original")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        # Install it first
        dest_file = install_root / ".claude" / "todelete.txt"
        dest_file.parent.mkdir(exist_ok=True, parents=True)
        dest_file.write_text("original")

        # Delete upstream
        file_path.unlink()
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "deleted"], cwd=repo, check=True, capture_output=True)

        # Modify local
        dest_file.write_text("modified_locally")
        last_hash = hash_file(dest_file)  # Hash of 'modified_locally' is NOT what we stored?
        # Actually we should store hash of 'original' in mapping to simulate clean state...
        # Wait, if we modify locally, hash changes.
        # We need to simulate that we imported 'original'.

        import hashlib

        original_hash = hashlib.sha256(b"original").hexdigest()

        registry_path = tmp_path / "registry.json"
        integrations = {
            "test-hard": {
                "source_url": str(repo),
                "target_scope": "project",
                "target_repo_path": str(install_root),
                "last_import_commit": "HEAD^",
                "artifact_mappings": [
                    {
                        "source_relpath": "todelete.txt",
                        "dest_abspath": str(dest_file),
                        "last_import_hash": original_hash,
                    }
                ],
            }
        }
        _write_registry(registry_path, integrations)

        updater = IntegrationUpdater(registry_path=registry_path, dry_run=False, verbose=True, delete_policy="hard")

        updates = updater.check_updates("test-hard")
        updater.apply_update(updates[0])

        assert not dest_file.exists(), "Hard delete should remove modified file"

    def test_delete_policy_skip(self, setup_repo, tmp_path):
        repo, install_root = setup_repo
        file_path = repo / "todelete.txt"
        file_path.write_text("original")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        dest_file = install_root / ".claude" / "todelete.txt"
        dest_file.parent.mkdir(exist_ok=True, parents=True)
        dest_file.write_text("modified_locally")

        import hashlib

        original_hash = hashlib.sha256(b"original").hexdigest()

        file_path.unlink()
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "deleted"], cwd=repo, check=True, capture_output=True)

        registry_path = tmp_path / "registry.json"
        integrations = {
            "test-skip": {
                "source_url": str(repo),
                "target_scope": "project",
                "target_repo_path": str(install_root),
                "last_import_commit": "HEAD^",
                "artifact_mappings": [
                    {
                        "source_relpath": "todelete.txt",
                        "dest_abspath": str(dest_file),
                        "last_import_hash": original_hash,
                    }
                ],
            }
        }
        _write_registry(registry_path, integrations)

        updater = IntegrationUpdater(registry_path=registry_path, dry_run=False, verbose=True, delete_policy="skip")

        updates = updater.check_updates("test-skip")
        updater.apply_update(updates[0])

        assert dest_file.exists()
        assert dest_file.read_text() == "modified_locally"

    def test_delete_policy_soft(self, setup_repo, tmp_path):
        repo, install_root = setup_repo
        file_path = repo / "todelete.txt"
        file_path.write_text("original")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        dest_file = install_root / ".claude" / "todelete.txt"
        dest_file.parent.mkdir(exist_ok=True, parents=True)
        dest_file.write_text("modified_locally")

        import hashlib

        original_hash = hashlib.sha256(b"original").hexdigest()

        file_path.unlink()
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "deleted"], cwd=repo, check=True, capture_output=True)

        registry_path = tmp_path / "registry.json"
        integrations = {
            "test-soft": {
                "source_url": str(repo),
                "target_scope": "project",
                "target_repo_path": str(install_root),
                "last_import_commit": "HEAD^",
                "artifact_mappings": [
                    {
                        "source_relpath": "todelete.txt",
                        "dest_abspath": str(dest_file),
                        "last_import_hash": original_hash,
                    }
                ],
            }
        }
        _write_registry(registry_path, integrations)

        updater = IntegrationUpdater(registry_path=registry_path, dry_run=False, verbose=True, delete_policy="soft")

        updates = updater.check_updates("test-soft")
        updater.apply_update(updates[0])

        assert not dest_file.exists()
        # Check for backup
        backups = list(dest_file.parent.glob("todelete.txt.bak.*"))
        assert len(backups) > 0
