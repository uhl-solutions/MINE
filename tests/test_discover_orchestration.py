"""
Orchestration-path tests for discover module.

Tests the run_discovery() function and related orchestration entrypoints.
"""

import json
import sys
from pathlib import Path

import pytest

# Setup path for modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mine-mine" / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

from discover import (
    DiscoverConfig,
    DiscoveryResult,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
    EXIT_SUCCESS,
    run_discovery,
    run_list,
    run_register,
)


class TestRunDiscoveryHappyPath:
    """Tests for run_discovery() happy path scenarios."""

    def test_discovery_with_empty_locations(self, tmp_path):
        """Discovery with no integrations should succeed with zero results."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=tmp_path,
            verbose=False,
        )

        result = run_discovery(cfg)

        assert result.ok is True
        assert result.exit_code == EXIT_SUCCESS
        assert len(result.integrations) == 0
        assert result.stats.locations_scanned > 0

    def test_discovery_finds_integration_markers(self, tmp_path):
        """Discovery should find integrations with markers."""
        # Create project with markers
        project = tmp_path / "project"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.test-repo.json").write_text("{}")

        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=project,
            verbose=False,
            ask_confirmation=False,
        )

        result = run_discovery(cfg)

        assert result.ok is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.stats.candidates_found >= 1
        assert result.stats.integrations_added >= 1

    def test_discovery_saves_registry(self, tmp_path):
        """Discovery should save registry when integrations are found."""
        # Create project with markers
        project = tmp_path / "project"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.my-repo.json").write_text("{}")

        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=project,
            ask_confirmation=False,
        )

        result = run_discovery(cfg)

        assert result.ok is True
        # Registry should be saved
        assert registry.exists()

        # Verify registry content
        data = json.loads(registry.read_text())
        assert "integrations" in data
        assert len(data["integrations"]) >= 1

    def test_discovery_deterministic_order(self, tmp_path):
        """Discovery results should be deterministically ordered."""
        # Create multiple projects with markers
        for name in ["alpha", "beta", "gamma"]:
            project = tmp_path / name
            project.mkdir()
            claude_dir = project / ".claude"
            claude_dir.mkdir()
            (claude_dir / f"settings.imported.{name}-repo.json").write_text("{}")

        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            search_roots=[str(tmp_path)],
            ask_confirmation=False,
        )

        # Run discovery
        result = run_discovery(cfg)

        # Get IDs
        ids = [i.get("id") for i in result.integrations]

        # IDs should be sorted (scope, then id)
        assert ids == sorted(ids)

        # Should find all three integrations
        assert len(ids) == 3
        assert all("alpha" in ids[0] or "beta" in ids[0] or "gamma" in ids[0] for _ in [1])


class TestRunDiscoveryDryRun:
    """Tests for run_discovery() dry-run mode."""

    def test_dry_run_no_writes(self, tmp_path):
        """Dry-run mode should not create or modify any files."""
        # Create project with markers
        project = tmp_path / "project"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.test.json").write_text("{}")

        registry = tmp_path / "registry.json"

        # Snapshot before
        def get_file_count():
            return len(list(tmp_path.rglob("*")))

        before_count = get_file_count()
        registry_exists_before = registry.exists()

        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=project,
            dry_run=True,
            ask_confirmation=False,
        )

        result = run_discovery(cfg)

        # Snapshot after
        after_count = get_file_count()
        registry_exists_after = registry.exists()

        assert result.ok is True
        assert result.dry_run is True
        # No new files created
        assert after_count == before_count
        # Registry not created in dry-run
        assert registry_exists_after == registry_exists_before

    def test_dry_run_returns_integrations(self, tmp_path):
        """Dry-run should still return discovered integrations."""
        # Create project with markers
        project = tmp_path / "project"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.test.json").write_text("{}")

        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=project,
            dry_run=True,
            ask_confirmation=False,
        )

        result = run_discovery(cfg)

        assert result.ok is True
        assert result.stats.candidates_found >= 1
        # Integrations listed even in dry-run
        assert result.stats.integrations_added >= 1


class TestRunDiscoveryErrorHandling:
    """Tests for run_discovery() error handling."""

    def test_invalid_target_repo(self, tmp_path):
        """Invalid target_repo should return error."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=tmp_path / "nonexistent",
        )

        result = run_discovery(cfg)

        assert result.ok is False
        assert result.exit_code == EXIT_INVALID_ARGS
        assert len(result.errors) > 0

    def test_target_repo_is_file(self, tmp_path):
        """target_repo pointing to file should return error."""
        registry = tmp_path / "registry.json"
        target_file = tmp_path / "not_a_dir.txt"
        target_file.write_text("test")

        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=target_file,
        )

        result = run_discovery(cfg)

        assert result.ok is False
        assert result.exit_code == EXIT_INVALID_ARGS


class TestRunList:
    """Tests for run_list() function."""

    def test_list_empty_registry(self, tmp_path):
        """Listing empty registry should succeed."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(registry_path=registry)

        result = run_list(cfg)

        assert result.ok is True
        assert result.exit_code == EXIT_SUCCESS
        assert len(result.integrations) == 0

    def test_list_with_integrations(self, tmp_path):
        """Listing registry with integrations should return them."""
        registry = tmp_path / "registry.json"
        registry.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "config": {},
                    "integrations": {
                        "user-test": {
                            "id": "user-test",
                            "source_url": "https://github.com/test/repo",
                            "target_scope": "user",
                        },
                        "project-other": {
                            "id": "project-other",
                            "source_url": "https://github.com/other/repo",
                            "target_scope": "project",
                        },
                    },
                }
            )
        )

        cfg = DiscoverConfig(registry_path=registry)
        result = run_list(cfg)

        assert result.ok is True
        assert len(result.integrations) == 2


class TestRunRegister:
    """Tests for run_register() function."""

    def test_register_github_url(self, tmp_path):
        """Registering a GitHub URL should create entry."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(registry_path=registry)

        result = run_register(
            cfg,
            source_url="https://github.com/test/repo",
            scope="user",
        )

        assert result.ok is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.stats.integrations_added == 1

        # Verify registry
        data = json.loads(registry.read_text())
        assert "user-test-repo" in data["integrations"]

    def test_register_dry_run(self, tmp_path):
        """Register in dry-run should not save registry."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            dry_run=True,
        )

        result = run_register(
            cfg,
            source_url="https://github.com/test/repo",
            scope="user",
        )

        assert result.ok is True
        assert result.dry_run is True
        # Registry should not be created
        assert not registry.exists()

    def test_register_unique_ids(self, tmp_path):
        """Registering same URL twice should generate unique IDs."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(registry_path=registry)

        # Register twice
        result1 = run_register(cfg, source_url="https://github.com/test/repo", scope="user")
        result2 = run_register(cfg, source_url="https://github.com/test/repo", scope="user")

        assert result1.ok is True
        assert result2.ok is True

        # Verify unique IDs
        data = json.loads(registry.read_text())
        ids = list(data["integrations"].keys())
        assert len(ids) == 2
        assert ids[0] != ids[1]


class TestDiscoveryStats:
    """Tests for discovery statistics."""

    def test_stats_locations_scanned(self, tmp_path):
        """Stats should track locations scanned."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=tmp_path,
            search_roots=[str(tmp_path)],
        )

        result = run_discovery(cfg)

        assert result.stats.locations_scanned >= 1

    def test_stats_candidates_found(self, tmp_path):
        """Stats should track candidates found."""
        # Create project with markers
        project = tmp_path / "project"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.test.json").write_text("{}")

        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=project,
            ask_confirmation=False,
        )

        result = run_discovery(cfg)

        assert result.stats.candidates_found >= 1


class TestDiscoveryResult:
    """Tests for DiscoveryResult structure."""

    def test_result_has_required_fields(self, tmp_path):
        """Result should have all required fields."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(registry_path=registry)

        result = run_discovery(cfg)

        assert hasattr(result, "ok")
        assert hasattr(result, "exit_code")
        assert hasattr(result, "stats")
        assert hasattr(result, "integrations")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "dry_run")

    def test_result_ok_matches_exit_code(self, tmp_path):
        """ok should be False when exit_code is non-zero."""
        registry = tmp_path / "registry.json"
        cfg = DiscoverConfig(
            registry_path=registry,
            target_repo=tmp_path / "nonexistent",
        )

        result = run_discovery(cfg)

        assert result.exit_code != EXIT_SUCCESS
        assert result.ok is False
