#!/usr/bin/env python3
"""
test_scan_safety.py - Tests for scan safety and traversal protection

Verifies symlink handling and resource limits in scanning.
"""

import os
import sys
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import modules under test
from scan_repo import RepoScanner, MAX_ARTIFACTS, MAX_SCAN_TIME

DOC_CLAIMS = ["security_resource_limits"]


class TestSymlinkNotFollowed:
    """Tests that symlinks are not followed during scan."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_symlink_pointing_outside_skipped(self, tmp_path):
        """Symlinks pointing outside scan root are skipped."""
        # Create structure:
        #   scan_root/
        #     .claude/
        #       skills/
        #         legit/SKILL.md
        #         sneaky -> /etc (symlink to outside)
        #   outside/
        #     secret.txt

        scan_root = tmp_path / "scan_root"
        outside_dir = tmp_path / "outside"

        scan_root.mkdir()
        outside_dir.mkdir()

        # Create legit skill
        legit_skill = scan_root / ".claude" / "skills" / "legit"
        legit_skill.mkdir(parents=True)
        (legit_skill / "SKILL.md").write_text("---\nname: legit\n---\n# Legit")

        # Create outside content
        secret_file = outside_dir / "secret.txt"
        secret_file.write_text("SECRET DATA")

        # Create sneaky symlink to outside
        sneaky_link = scan_root / ".claude" / "skills" / "sneaky"
        sneaky_link.symlink_to(outside_dir)

        # Scan should find only the legit skill, not follow symlink
        scanner = RepoScanner(str(scan_root), verbose=False)
        scanner.repo_path = scan_root
        scanner.start_time = time.monotonic()

        report = {"detected_artifacts": [], "truncated": False, "truncation_reason": None}

        scanner._scan_skills(report)

        # Should find only the legit skill
        skill_paths = [a["source_path"] for a in report["detected_artifacts"]]

        assert any("legit" in p for p in skill_paths)
        # Sneaky symlink should not be followed
        assert not any("sneaky" in p for p in skill_paths)
        assert not any("secret" in p for p in skill_paths)

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_symlink_skill_file_skipped(self, tmp_path):
        """Symlinked SKILL.md files are skipped."""
        scan_root = tmp_path / "repo"
        scan_root.mkdir()

        skills_dir = scan_root / ".claude" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)

        # Create actual skill file elsewhere
        real_skill = tmp_path / "real_skill.md"
        real_skill.write_text("---\nname: test\n---\n# Test")

        # Symlink the SKILL.md
        (skills_dir / "SKILL.md").symlink_to(real_skill)

        scanner = RepoScanner(str(scan_root), verbose=True)
        scanner.repo_path = scan_root
        scanner.start_time = time.monotonic()

        report = {"detected_artifacts": [], "truncated": False, "truncation_reason": None}

        scanner._scan_skills(report)

        # Symlinked skill should be skipped
        assert len(report["detected_artifacts"]) == 0


class TestResourceLimits:
    """Tests for scan resource limits."""

    def test_max_artifacts_limit_exists(self):
        """MAX_ARTIFACTS constant is defined and reasonable."""
        assert MAX_ARTIFACTS is not None
        assert MAX_ARTIFACTS > 0
        assert MAX_ARTIFACTS <= 10000  # Reasonable upper bound

    def test_max_scan_time_limit_exists(self):
        """MAX_SCAN_TIME constant is defined and reasonable."""
        assert MAX_SCAN_TIME is not None
        assert MAX_SCAN_TIME > 0
        assert MAX_SCAN_TIME <= 600  # 10 minutes max

    def test_scanner_respects_artifact_limit(self, tmp_path):
        """Scanner stops when hitting artifact limit."""
        scan_root = tmp_path / "repo"
        scan_root.mkdir()

        # Create many skills (more than a small limit)
        skills_dir = scan_root / ".claude" / "skills"

        for i in range(10):
            skill_dir = skills_dir / f"skill-{i}"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"---\nname: skill-{i}\n---\n# Skill {i}")

        # Create scanner with small limit
        scanner = RepoScanner(str(scan_root), max_artifacts=3)
        scanner.repo_path = scan_root
        scanner.start_time = time.monotonic()

        report = {"detected_artifacts": [], "truncated": False, "truncation_reason": None}

        scanner._scan_skills(report)

        # Should stop at limit
        assert len(report["detected_artifacts"]) <= 3
        assert report["truncated"] is True
        assert report["truncation_reason"] == "max_artifacts"


class TestPathGlobSafety:
    """Tests that Path.glob/rglob don't follow symlinks by default."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_glob_does_not_follow_symlinks(self, tmp_path):
        """Verify Path.glob behavior with symlinks."""
        # Setup
        main_dir = tmp_path / "main"
        outside_dir = tmp_path / "outside"

        main_dir.mkdir()
        outside_dir.mkdir()

        (outside_dir / "secret.txt").write_text("SECRET")

        # Create symlink in main pointing to outside
        (main_dir / "link").symlink_to(outside_dir)

        # Create normal file in main
        (main_dir / "normal.txt").write_text("normal")

        # Glob should find normal.txt but not traverse symlink
        results = list(main_dir.glob("*.txt"))
        result_names = [r.name for r in results]

        assert "normal.txt" in result_names
        # Secret should not be found (symlink not followed by glob)
        assert "secret.txt" not in result_names


class TestNoOsWalkWithFollowlinks:
    """Verify no os.walk with followlinks=True exists."""

    def test_scan_repo_no_followlinks(self):
        """scan_repo.py should not use os.walk with followlinks=True."""
        import inspect
        from scan_repo import RepoScanner

        source = inspect.getsource(RepoScanner)

        # Should not contain followlinks=True
        assert "followlinks=True" not in source
        assert "followlinks = True" not in source
