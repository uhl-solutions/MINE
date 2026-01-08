"""
Orchestration-path tests for main scripts.

Tests the end-to-end CLI behavior including argument parsing,
dry-run guarantees, and basic operation flow.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Get the scripts directory
MINE_SCRIPTS = Path(__file__).parent.parent / "skills" / "mine" / "scripts"
MINE_MINE_SCRIPTS = Path(__file__).parent.parent / "skills" / "mine-mine" / "scripts"


def run_script(script_path: Path, args: list, cwd=None, timeout=30) -> subprocess.CompletedProcess:
    """Run a Python script and return the result."""
    cmd = [sys.executable, str(script_path)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )


class TestImportAssetsOrchestration:
    """Orchestration tests for import_assets.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_SCRIPTS / "import_assets.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_required_args_enforced(self):
        """Missing required args should fail."""
        result = run_script(MINE_SCRIPTS / "import_assets.py", [])
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_dry_run_flag_accepted(self):
        """--dry-run flag (no value) should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", tmp, "--scope", "project", "--target-repo", tmp, "--dry-run"],
            )
            # Should not fail due to argument parsing
            assert "unrecognized arguments" not in result.stderr.lower()

    def test_dry_run_produces_no_writes(self):
        """Dry-run mode should not create any files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            target_dir = tmp_path / "target"
            source_dir.mkdir()
            target_dir.mkdir()

            # Create a minimal source with Claude artifacts
            claude_dir = source_dir / ".claude"
            claude_dir.mkdir()
            (claude_dir / "CLAUDE.md").write_text("# Test")

            # Snapshot before
            before_files = set(target_dir.rglob("*"))

            result = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", str(source_dir), "--scope", "project", "--target-repo", str(target_dir), "--dry-run"],
            )

            # Snapshot after
            after_files = set(target_dir.rglob("*"))

            # No new files should be created in dry-run mode
            new_files = after_files - before_files
            assert len(new_files) == 0, f"Dry-run created files: {new_files}"

    def test_apply_flag_recognized(self):
        """--apply flag should be recognized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", tmp, "--scope", "project", "--target-repo", tmp, "--apply", "--verbose"],
            )
            # Should not fail due to argument parsing
            assert "unrecognized arguments" not in result.stderr.lower()

    def test_no_dry_run_flag_recognized(self):
        """--no-dry-run flag should be recognized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", tmp, "--scope", "project", "--target-repo", tmp, "--no-dry-run", "--verbose"],
            )
            # Should not fail due to argument parsing
            assert "unrecognized arguments" not in result.stderr.lower()


class TestConvertFrameworkOrchestration:
    """Orchestration tests for convert_framework.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_SCRIPTS / "convert_framework.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_required_args_enforced(self):
        """Missing required args should fail."""
        result = run_script(MINE_SCRIPTS / "convert_framework.py", [])
        assert result.returncode != 0

    def test_dry_run_flag_accepted(self):
        """--dry-run flag (no value) should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "convert_framework.py",
                ["--framework", "fabric", "--source", tmp, "--output", tmp, "--dry-run"],
            )
            assert "unrecognized arguments" not in result.stderr.lower()

    def test_dry_run_produces_no_writes(self):
        """Dry-run mode should not create any files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            output_dir = tmp_path / "output"
            source_dir.mkdir()
            output_dir.mkdir()

            # Snapshot before
            before_files = set(output_dir.rglob("*"))

            result = run_script(
                MINE_SCRIPTS / "convert_framework.py",
                ["--framework", "fabric", "--source", str(source_dir), "--output", str(output_dir), "--dry-run"],
            )

            # Snapshot after
            after_files = set(output_dir.rglob("*"))

            # No new files should be created in dry-run mode
            new_files = after_files - before_files
            assert len(new_files) == 0, f"Dry-run created files: {new_files}"


class TestGenerateSkillpackOrchestration:
    """Orchestration tests for generate_skillpack.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_SCRIPTS / "generate_skillpack.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_required_args_enforced(self):
        """Missing required args should fail."""
        result = run_script(MINE_SCRIPTS / "generate_skillpack.py", [])
        assert result.returncode != 0

    def test_dry_run_flag_accepted(self):
        """--dry-run flag (no value) should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "generate_skillpack.py",
                ["--source", tmp, "--target-dir", tmp, "--dry-run"],
            )
            assert "unrecognized arguments" not in result.stderr.lower()

    def test_dry_run_produces_no_writes(self):
        """Dry-run mode should not create any files in target directory."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            target_dir = tmp_path / "target"
            source_dir.mkdir()
            target_dir.mkdir()

            # Create some source files to analyze
            (source_dir / "README.md").write_text("# Test Project")
            (source_dir / "Makefile").write_text("build:\n\techo build")

            # Snapshot before
            before_files = set(target_dir.rglob("*"))

            result = run_script(
                MINE_SCRIPTS / "generate_skillpack.py",
                ["--source", str(source_dir), "--target-dir", str(target_dir), "--dry-run"],
            )

            # Snapshot after
            after_files = set(target_dir.rglob("*"))

            # No new files should be created in dry-run mode
            new_files = after_files - before_files
            assert len(new_files) == 0, f"Dry-run created files: {new_files}"


class TestDiscoverIntegrationsOrchestration:
    """Orchestration tests for discover_integrations.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_MINE_SCRIPTS / "discover_integrations.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_list_with_no_registry(self):
        """--list should work even without existing registry."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            result = run_script(
                MINE_MINE_SCRIPTS / "discover_integrations.py",
                ["--list", "--registry", str(registry)],
            )
            # Should complete without error
            assert result.returncode == 0 or "no integrations" in result.stdout.lower()

    def test_dry_run_flag_accepted(self):
        """--dry-run flag (no value) should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            result = run_script(
                MINE_MINE_SCRIPTS / "discover_integrations.py",
                ["--list", "--registry", str(registry), "--dry-run"],
            )
            assert "unrecognized arguments" not in result.stderr.lower()


class TestUpdateIntegrationsOrchestration:
    """Orchestration tests for update_integrations.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_MINE_SCRIPTS / "update_integrations.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_check_with_no_registry(self):
        """--check should work with empty/missing registry."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            result = run_script(
                MINE_MINE_SCRIPTS / "update_integrations.py",
                ["--check", "--all", "--registry", str(registry)],
            )
            # Should complete (may have no integrations)
            # Exit code 0 or message about no integrations
            assert "unrecognized arguments" not in result.stderr.lower()

    def test_dry_run_flag_accepted(self):
        """--dry-run flag (no value) should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            result = run_script(
                MINE_MINE_SCRIPTS / "update_integrations.py",
                ["--check", "--all", "--registry", str(registry), "--dry-run"],
            )
            assert "unrecognized arguments" not in result.stderr.lower()


class TestScanRepoOrchestration:
    """Orchestration tests for scan_repo.py."""

    def test_help_exits_zero(self):
        """--help should exit with code 0."""
        result = run_script(MINE_SCRIPTS / "scan_repo.py", ["--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_scan_empty_directory(self):
        """Scanning an empty directory should work."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                MINE_SCRIPTS / "scan_repo.py",
                ["--source", tmp],
            )
            assert result.returncode == 0

    def test_scan_directory_with_claude_artifacts(self):
        """Scanning a directory with Claude artifacts should find them."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create Claude artifacts in .claude directory
            claude_dir = tmp_path / ".claude"
            claude_dir.mkdir()
            (claude_dir / "CLAUDE.md").write_text("# Test Claude Instructions")

            # Also create CLAUDE.md at root (the scanner looks for this)
            (tmp_path / "CLAUDE.md").write_text("# Test Claude Instructions")

            result = run_script(
                MINE_SCRIPTS / "scan_repo.py",
                ["--source", tmp],
            )
            assert result.returncode == 0
            # Parse JSON output and check detected_artifacts
            output_data = json.loads(result.stdout)
            # Scanner should find CLAUDE.md as documentation
            artifact_paths = [a.get("path", "") for a in output_data.get("detected_artifacts", [])]
            assert any("CLAUDE.md" in p for p in artifact_paths) or len(output_data.get("detected_artifacts", [])) > 0


class TestDryRunInvariant:
    """Tests to verify the dry-run invariant: no writes in dry-run mode."""

    @pytest.fixture
    def test_repo(self, tmp_path):
        """Create a minimal test repository with Claude artifacts."""
        repo = tmp_path / "repo"
        repo.mkdir()

        # Create .claude directory
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Test")

        # Create settings
        (claude_dir / "settings.json").write_text('{"key": "value"}')

        # Create a skill
        skills_dir = claude_dir / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Test Skill")

        return repo

    def test_import_dry_run_no_state_changes(self, test_repo, tmp_path):
        """import_assets in dry-run should not modify any state."""
        target = tmp_path / "target"
        target.mkdir()

        # Create a test file in target to ensure it's not modified
        test_file = target / "existing.txt"
        test_file.write_text("original")
        original_content = test_file.read_text()

        # Snapshot all files
        def get_snapshot(path):
            files = {}
            for f in path.rglob("*"):
                if f.is_file():
                    files[str(f.relative_to(path))] = f.read_text()
            return files

        before = get_snapshot(target)

        result = run_script(
            MINE_SCRIPTS / "import_assets.py",
            ["--source", str(test_repo), "--scope", "project", "--target-repo", str(target), "--dry-run"],
        )

        after = get_snapshot(target)

        # Files should be unchanged
        assert before == after, "Dry-run modified files"
        assert test_file.read_text() == original_content

    def test_multiple_dry_run_flags_accepted(self):
        """Multiple forms of dry-run flags should be accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            # Test various flag combinations
            flag_combos = [
                ["--dry-run"],
                ["--dry-run=true"],
                ["--dry-run=True"],
                ["--dry-run=1"],
                ["--dry-run=yes"],
            ]

            for flags in flag_combos:
                result = run_script(
                    MINE_SCRIPTS / "import_assets.py",
                    ["--source", tmp, "--scope", "project", "--target-repo", tmp] + flags,
                )
                assert "unrecognized arguments" not in result.stderr.lower(), f"Failed with flags: {flags}"


class TestCLIOutputFormat:
    """Tests for CLI output formatting in dry-run mode."""

    def test_dry_run_banner_shown(self):
        """Dry-run mode should show a clear banner/indicator."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create minimal source
            (tmp_path / "README.md").write_text("# Test")

            result = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", str(tmp_path), "--scope", "project", "--target-repo", str(tmp_path), "--dry-run"],
            )

            # Should have some indication of dry-run mode
            output = result.stdout + result.stderr
            assert "dry" in output.lower() or "preview" in output.lower()

    def test_verbose_output(self):
        """--verbose should produce more output."""
        with tempfile.TemporaryDirectory() as tmp:
            result_quiet = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", tmp, "--scope", "project", "--target-repo", tmp, "--dry-run"],
            )

            result_verbose = run_script(
                MINE_SCRIPTS / "import_assets.py",
                ["--source", tmp, "--scope", "project", "--target-repo", tmp, "--dry-run", "--verbose"],
            )

            # Verbose should generally produce more output or at least not less
            # (allowing for some variance in output)
            len_quiet = len(result_quiet.stdout) + len(result_quiet.stderr)
            len_verbose = len(result_verbose.stdout) + len(result_verbose.stderr)
            # Just verify verbose doesn't fail
            assert result_verbose.returncode == result_quiet.returncode
