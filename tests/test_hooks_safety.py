#!/usr/bin/env python3
"""
test_hooks_safety.py

Tests for Hooks Safety (Claims: hooks_staged).
Verifies that hooks are never auto-enabled but staged for review.
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

# Rely on conftest.py for sys.path setup
# But if running standalone, might need it. conftest handles pytest runs.

DOC_CLAIMS = ["hooks_staged", "security_no_execution"]


class TestHooksSafety:
    """Tests that verify hooks are staged and not enabled."""

    def test_hooks_are_staged_not_installed(self, tmp_path):
        """Hooks should be imported to .claude/hooks.imported.<repo> not .claude/hooks."""
        from import_assets import AssetImporter

        # Setup source repo with hooks
        source_repo = tmp_path / "source"
        source_repo.mkdir()
        (source_repo / ".git").mkdir()
        hooks_src = source_repo / ".claude" / "hooks"
        hooks_src.mkdir(parents=True)
        (hooks_src / "pre-commit").write_text("#!/bin/bash\necho evil")

        # Setup target
        target_repo = tmp_path / "target"
        target_repo.mkdir()

        # Init importer
        importer = AssetImporter(
            source=str(source_repo), scope="project", target_repo=str(target_repo), dry_run=False, verbose=True
        )
        importer.repo_id = "user/repo"

        # Mock scanner report to include hooks
        report = {
            "repo_id": "user/repo",
            "source": str(source_repo),
            "detected_artifacts": [
                {
                    "type": "hook",
                    "path": ".claude/hooks/pre-commit",
                    "source_path": str(hooks_src / "pre-commit"),
                    "content": "#!/bin/bash\necho evil",
                    "destination_suggestions": {
                        "project": ".claude/hooks.imported.user-repo/pre-commit"  # Expected staging path
                    },
                }
            ],
            "risks": [],
        }

        # Mock scanner check
        with patch("import_assets.RepoScanner._clone_repo", return_value=source_repo):
            importer._import_mode(report)

        # Verify hook is NOT in active hooks dir
        active_hooks = target_repo / ".claude" / "hooks" / "pre-commit"
        assert not active_hooks.exists(), "Hook should not be in active hooks directory"

        # Verify hook IS in staged dir
        staged_hook = target_repo / ".claude" / "hooks.imported.user-repo" / "pre-commit"
        assert staged_hook.exists(), f"Hook should be staged at {staged_hook}"
        assert staged_hook.read_text() == "#!/bin/bash\necho evil"
