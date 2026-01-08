"""
Tests for the modular discover package components.

Tests the config, markers, scanner, and registry modules.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Setup path for modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mine-mine" / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

from discover.config import DiscoverConfig, DEFAULT_REGISTRY_PATH
from discover.markers import (
    find_markers,
    infer_repo_name,
    group_markers_by_repo,
    MARKER_PATTERNS,
)
from discover.scanner import (
    scan_location,
    scan_for_integrations,
    filter_discoveries,
)
from discover.registry import (
    load_registry,
    save_registry,
    get_integration,
    add_integration,
    remove_integration,
    list_integrations,
    generate_integration_id,
    DEFAULT_REGISTRY_STRUCTURE,
)


class TestDiscoverConfig:
    """Tests for the DiscoverConfig dataclass."""

    def test_default_values(self):
        """Default config should have sensible values."""
        config = DiscoverConfig()
        assert config.verbose is False
        assert config.auto_track is True
        assert config.ask_confirmation is True
        assert config.target_repo is None
        assert "node_modules" in config.skip_dirs

    def test_registry_path_expansion(self):
        """Registry path with ~ should be expanded."""
        config = DiscoverConfig(registry_path="~/.claude/test.json")
        assert "~" not in str(config.registry_path)
        assert str(config.registry_path).startswith(str(Path.home()))

    def test_from_args(self):
        """Config should be creatable from argparse namespace."""
        args = argparse.Namespace(
            registry="~/.claude/mine/registry.json",
            verbose=True,
            search_roots="~/code,~/projects",
            target_repo="/tmp/repo",
            no_confirm=True,
        )
        config = DiscoverConfig.from_args(args)
        assert config.verbose is True
        assert len(config.search_roots) == 2
        assert config.ask_confirmation is False

    def test_get_search_locations(self, tmp_path):
        """get_search_locations should return proper location tuples."""
        config = DiscoverConfig(target_repo=tmp_path)
        locations = config.get_search_locations()

        # Should include target repo as project scope
        assert ("project", tmp_path) in locations

        # Should always include user scope
        user_scopes = [loc for loc in locations if loc[0] == "user"]
        assert len(user_scopes) == 1


class TestMarkers:
    """Tests for marker detection functions."""

    def test_find_settings_import_markers(self, tmp_path):
        """Should find settings.imported.*.json files."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.my-repo.json").write_text("{}")

        markers = find_markers(claude_dir)

        assert len(markers) == 1
        assert markers[0]["type"] == "settings_import"
        assert markers[0]["inferred_repo"] == "my-repo"

    def test_find_hooks_import_markers(self, tmp_path):
        """Should find hooks.imported.* directories."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "hooks.imported.test-repo").mkdir()

        markers = find_markers(claude_dir)

        assert len(markers) == 1
        assert markers[0]["type"] == "hooks_import"
        assert markers[0]["inferred_repo"] == "test-repo"

    def test_find_claude_md_import_markers(self, tmp_path):
        """Should find CLAUDE.imported.*.md files."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.imported.docs-repo.md").write_text("# Docs")

        markers = find_markers(claude_dir)

        assert len(markers) == 1
        assert markers[0]["type"] == "claude_md_import"
        assert markers[0]["inferred_repo"] == "docs-repo"

    def test_find_generated_skill_markers(self, tmp_path):
        """Should find *-workflow skill directories."""
        claude_dir = tmp_path / ".claude"
        skills_dir = claude_dir / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "my-project-workflow").mkdir()

        markers = find_markers(claude_dir)

        assert len(markers) == 1
        assert markers[0]["type"] == "generated_skill"
        assert markers[0]["inferred_repo"] == "my-project"

    def test_find_provenance_markers(self, tmp_path):
        """Should find provenance JSON files."""
        claude_dir = tmp_path / ".claude"
        prov_dir = claude_dir / "mine" / ".provenance"
        prov_dir.mkdir(parents=True)

        prov_data = {
            "repo_id": "test-repo",
            "source_url": "https://github.com/user/repo",
            "import_time": "2025-01-01T00:00:00",
            "artifact_mappings": [],
        }
        (prov_dir / "test-repo.json").write_text(json.dumps(prov_data))

        markers = find_markers(claude_dir)

        assert len(markers) == 1
        assert markers[0]["type"] == "provenance"
        assert markers[0]["inferred_repo"] == "test-repo"
        assert markers[0]["source_url"] == "https://github.com/user/repo"

    def test_find_multiple_markers(self, tmp_path):
        """Should find all marker types."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.repo1.json").write_text("{}")
        (claude_dir / "CLAUDE.imported.repo2.md").write_text("# Doc")
        (claude_dir / "hooks.imported.repo3").mkdir()

        markers = find_markers(claude_dir)

        assert len(markers) == 3
        types = {m["type"] for m in markers}
        assert types == {"settings_import", "claude_md_import", "hooks_import"}

    def test_infer_repo_name(self):
        """Should return most common repo name."""
        markers = [
            {"inferred_repo": "main-repo"},
            {"inferred_repo": "main-repo"},
            {"inferred_repo": "other-repo"},
        ]
        assert infer_repo_name(markers) == "main-repo"

    def test_infer_repo_name_empty(self):
        """Should return 'unknown' for empty markers."""
        assert infer_repo_name([]) == "unknown"

    def test_group_markers_by_repo(self):
        """Should group markers by repo name."""
        markers = [
            {"type": "settings_import", "inferred_repo": "repo1"},
            {"type": "hooks_import", "inferred_repo": "repo1"},
            {"type": "settings_import", "inferred_repo": "repo2"},
        ]
        groups = group_markers_by_repo(markers)

        assert len(groups) == 2
        assert len(groups["repo1"]) == 2
        assert len(groups["repo2"]) == 1


class TestScanner:
    """Tests for scanner functions."""

    def test_scan_location_empty(self, tmp_path):
        """Scanning empty directory should return no discoveries."""
        discoveries = scan_location(tmp_path, "project")
        assert discoveries == []

    def test_scan_location_with_markers(self, tmp_path):
        """Should find integrations with markers."""
        # Create a project directory with .claude inside
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.imported.test.json").write_text("{}")

        # Scan from project_dir which contains .claude
        discoveries = scan_location(project_dir, "project")

        assert len(discoveries) == 1
        assert discoveries[0]["scope"] == "project"
        assert discoveries[0]["inferred_name"] == "test"

    def test_scan_location_user_scope(self, tmp_path):
        """User scope should group by repo."""
        claude_dir = tmp_path
        (claude_dir / "settings.imported.repo1.json").write_text("{}")
        (claude_dir / "settings.imported.repo2.json").write_text("{}")

        discoveries = scan_location(claude_dir, "user")

        assert len(discoveries) == 2
        names = {d["inferred_name"] for d in discoveries}
        assert names == {"repo1", "repo2"}

    def test_scan_for_integrations(self, tmp_path):
        """Should scan multiple locations."""
        # Create two project directories with .claude inside subfolders
        # so scanner finds them during walk
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"

        proj1 = root1 / "proj1"
        proj2 = root2 / "proj2"

        (proj1 / ".claude").mkdir(parents=True)
        (proj1 / ".claude" / "settings.imported.p1.json").write_text("{}")

        (proj2 / ".claude").mkdir(parents=True)
        (proj2 / ".claude" / "settings.imported.p2.json").write_text("{}")

        # Scan from the project directories which contain .claude
        locations = [("project", proj1), ("project", proj2)]
        discoveries = scan_for_integrations(locations)

        assert len(discoveries) == 2

    def test_filter_discoveries_by_scope(self):
        """Should filter by scope."""
        discoveries = [
            {"scope": "user", "markers_found": 1, "inferred_name": "u1"},
            {"scope": "project", "markers_found": 1, "inferred_name": "p1"},
        ]
        filtered = filter_discoveries(discoveries, scopes=["user"])

        assert len(filtered) == 1
        assert filtered[0]["scope"] == "user"

    def test_filter_discoveries_by_min_markers(self):
        """Should filter by minimum markers."""
        discoveries = [
            {"scope": "user", "markers_found": 3, "inferred_name": "r1"},
            {"scope": "user", "markers_found": 1, "inferred_name": "r2"},
        ]
        filtered = filter_discoveries(discoveries, min_markers=2)

        assert len(filtered) == 1
        assert filtered[0]["markers_found"] == 3


class TestRegistry:
    """Tests for registry management functions."""

    def test_default_registry_structure(self):
        """Default structure should have required keys."""
        assert "version" in DEFAULT_REGISTRY_STRUCTURE
        assert "config" in DEFAULT_REGISTRY_STRUCTURE
        assert "integrations" in DEFAULT_REGISTRY_STRUCTURE

    def test_load_nonexistent_registry(self, tmp_path):
        """Loading nonexistent file should return default."""
        registry_path = tmp_path / "registry.json"
        registry = load_registry(registry_path)

        assert registry["version"] == "1.0"
        assert registry["integrations"] == {}

    def test_save_and_load_registry(self, tmp_path):
        """Should save and load registry correctly."""
        registry_path = tmp_path / "registry.json"
        registry = {
            "version": "1.0",
            "config": {"auto_track": True},
            "integrations": {"test-id": {"source_url": "http://example.com"}},
        }

        save_registry(registry_path, registry)
        loaded = load_registry(registry_path)

        assert loaded["integrations"]["test-id"]["source_url"] == "http://example.com"

    def test_add_integration(self):
        """Should add integration to registry."""
        registry = {"integrations": {}}
        integration = {"source_url": "http://test.com"}

        add_integration(registry, "test-id", integration)

        assert "test-id" in registry["integrations"]

    def test_remove_integration(self):
        """Should remove integration from registry."""
        registry = {"integrations": {"test-id": {"source_url": "http://test.com"}}}

        removed = remove_integration(registry, "test-id")

        assert removed is not None
        assert "test-id" not in registry["integrations"]

    def test_remove_nonexistent_integration(self):
        """Removing nonexistent integration should return None."""
        registry = {"integrations": {}}
        removed = remove_integration(registry, "nonexistent")
        assert removed is None

    def test_list_integrations_all(self):
        """Should list all integrations."""
        registry = {
            "integrations": {
                "user-repo1": {"target_scope": "user"},
                "project-repo2": {"target_scope": "project"},
            }
        }

        all_integrations = list_integrations(registry)
        assert len(all_integrations) == 2

    def test_list_integrations_by_scope(self):
        """Should filter by scope."""
        registry = {
            "integrations": {
                "user-repo1": {"target_scope": "user"},
                "project-repo2": {"target_scope": "project"},
            }
        }

        user_only = list_integrations(registry, scope="user")
        assert len(user_only) == 1
        assert "user-repo1" in user_only

    def test_generate_integration_id_unique(self):
        """Should generate unique IDs."""
        registry = {"integrations": {"user-repo": {}}}

        new_id = generate_integration_id(registry, "user", "repo")

        assert new_id != "user-repo"
        assert new_id.startswith("user-repo")

    def test_generate_integration_id_available(self):
        """Should use base ID if available."""
        registry = {"integrations": {}}

        new_id = generate_integration_id(registry, "user", "myrepo")

        assert new_id == "user-myrepo"


class TestMarkerPatterns:
    """Tests for marker pattern definitions."""

    def test_all_patterns_have_required_keys(self):
        """All patterns should have pattern, extract_name, type."""
        for name, pattern in MARKER_PATTERNS.items():
            assert "pattern" in pattern, f"Pattern {name} missing 'pattern'"
            assert "extract_name" in pattern, f"Pattern {name} missing 'extract_name'"
            assert "type" in pattern, f"Pattern {name} missing 'type'"

    def test_extract_name_functions(self):
        """Extract name functions should work correctly."""
        patterns = MARKER_PATTERNS

        # Test settings import
        name_fn = patterns["settings_import"]["extract_name"]
        assert name_fn("settings.imported.my-repo.json") == "my-repo"

        # Test hooks import
        name_fn = patterns["hooks_import"]["extract_name"]
        assert name_fn("hooks.imported.test-repo") == "test-repo"

        # Test generated skill
        name_fn = patterns["generated_skill"]["extract_name"]
        assert name_fn("project-workflow") == "project"
