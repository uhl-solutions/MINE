#!/usr/bin/env python3
"""
test_build_dist.py

Tests for the build_dist.py distribution script.
Verifies that the dist-manifest.json is properly enforced.
"""

import json
import sys
from pathlib import Path
import pytest

# Add the scripts directory to path for build_dist import
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DOC_CLAIMS = ["security_clean_artifacts"]


class TestDistManifestLoading:
    """Tests for manifest loading and validation."""

    def test_manifest_file_exists(self):
        """dist-manifest.json should exist in project root."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        assert manifest_path.exists(), "dist-manifest.json should exist"

    def test_manifest_is_valid_json(self):
        """dist-manifest.json should be valid JSON."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert isinstance(manifest, dict), "Manifest should be a dict"

    def test_manifest_has_required_fields(self):
        """Manifest should have include and exclude fields."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert "include" in manifest, "Manifest should have 'include' field"
        assert "exclude" in manifest, "Manifest should have 'exclude' field"
        assert isinstance(manifest["include"], list), "'include' should be a list"
        assert isinstance(manifest["exclude"], list), "'exclude' should be a list"


class TestDistManifestPatterns:
    """Tests for manifest pattern validation."""

    def test_skills_dirs_included(self):
        """Manifest should include skills directories."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        include = manifest["include"]

        # Should include _shared, mine, and mine-mine
        include_str = " ".join(include)
        assert "skills/_shared" in include_str or "_shared" in include_str
        assert "skills/mine" in include_str or "mine/" in include_str
        assert "skills/mine-mine" in include_str or "mine-mine" in include_str

    def test_tests_excluded(self):
        """Manifest should exclude tests directory."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        exclude = manifest["exclude"]

        # Should exclude tests
        assert any("test" in pattern.lower() for pattern in exclude), "Manifest should exclude tests"

    def test_coverage_artifacts_excluded(self):
        """Manifest should exclude coverage artifacts."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        exclude = manifest["exclude"]
        exclude_str = " ".join(exclude)

        # Should exclude coverage files
        assert ".coverage" in exclude_str or "coverage" in exclude_str

    def test_pycache_excluded(self):
        """Manifest should exclude __pycache__ directories."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        exclude = manifest["exclude"]

        assert any("__pycache__" in pattern for pattern in exclude), "Manifest should exclude __pycache__"

    def test_github_excluded(self):
        """Manifest should exclude .github directory."""
        manifest_path = REPO_ROOT / "config" / "dist-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        exclude = manifest["exclude"]

        assert any(".github" in pattern for pattern in exclude), "Manifest should exclude .github"


class TestBuildDistFunctions:
    """Tests for build_dist.py helper functions."""

    def test_load_manifest_function(self, tmp_path):
        """load_manifest should correctly load a valid manifest."""
        from build_dist import load_manifest

        manifest_data = {"version": "1.0", "include": ["skills/**"], "exclude": ["tests/**"]}

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        loaded = load_manifest(manifest_file)

        assert loaded["version"] == "1.0"
        assert loaded["include"] == ["skills/**"]
        assert loaded["exclude"] == ["tests/**"]

    def test_load_manifest_missing_include_raises(self, tmp_path):
        """load_manifest should raise if include is missing."""
        from build_dist import load_manifest

        manifest_data = {"version": "1.0", "exclude": ["tests/**"]}

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        with pytest.raises(ValueError, match="missing 'include'"):
            load_manifest(manifest_file)

    def test_collect_files_includes_matching(self, tmp_path):
        """collect_files should include files matching patterns."""
        from build_dist import collect_files

        # Create test structure
        skills_dir = tmp_path / "skills" / "mine"
        skills_dir.mkdir(parents=True)
        (skills_dir / "script.py").write_text("# test")
        (skills_dir / "SKILL.md").write_text("# Skill")

        files = collect_files(tmp_path, include_patterns=["skills/**"], exclude_patterns=[])

        file_names = [f.name for f in files]
        assert "script.py" in file_names
        assert "SKILL.md" in file_names

    def test_collect_files_excludes_matching(self, tmp_path):
        """collect_files should exclude files matching exclude patterns."""
        from build_dist import collect_files

        # Create test structure
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "script.py").write_text("# test")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_script.py").write_text("# test")

        files = collect_files(tmp_path, include_patterns=["skills/**", "tests/**"], exclude_patterns=["tests/**"])

        file_paths = [str(f) for f in files]
        assert not any("tests" in p for p in file_paths), "tests directory should be excluded"

    def test_verify_distribution_passes_clean(self, tmp_path):
        """verify_distribution should pass for clean dist."""
        from build_dist import verify_distribution

        # Create clean distribution
        dist = tmp_path / "dist"
        skills = dist / "skills" / "mine"
        skills.mkdir(parents=True)
        (skills / "script.py").write_text("# clean")

        manifest = {"include": ["skills/**"], "exclude": ["tests/**", "*.pyc"]}

        result = verify_distribution(dist, manifest)
        assert result is True

    def test_verify_distribution_fails_with_excluded(self, tmp_path):
        """verify_distribution should fail if excluded files present."""
        from build_dist import verify_distribution

        # Create distribution with excluded file
        dist = tmp_path / "dist"
        tests = dist / "tests"
        tests.mkdir(parents=True)
        (tests / "test.py").write_text("# should not be here")

        manifest = {"include": ["skills/**"], "exclude": ["tests/**"]}

        result = verify_distribution(dist, manifest)
        assert result is False


class TestReproducibleBuilds:
    """Tests for reproducible build functionality."""

    def test_create_reproducible_zip_deterministic(self, tmp_path):
        """Two builds of same content should produce identical ZIPs."""
        from build_dist import create_reproducible_zip
        import hashlib

        # Create source
        source = tmp_path / "source"
        source.mkdir()
        (source / "file1.txt").write_text("content 1")
        (source / "file2.txt").write_text("content 2")

        # Create two zips
        zip1 = tmp_path / "build1.zip"
        zip2 = tmp_path / "build2.zip"

        create_reproducible_zip(source, zip1)
        create_reproducible_zip(source, zip2)

        # Compare hashes
        hash1 = hashlib.sha256(zip1.read_bytes()).hexdigest()
        hash2 = hashlib.sha256(zip2.read_bytes()).hexdigest()

        assert hash1 == hash2, "Reproducible ZIPs should have identical hashes"

    def test_zip_excludes_timestamps(self, tmp_path):
        """ZIP should use fixed timestamps, not system time."""
        from build_dist import create_reproducible_zip, REPRODUCIBLE_TIMESTAMP
        import zipfile

        # Create source
        source = tmp_path / "source"
        source.mkdir()
        (source / "test.txt").write_text("test content")

        # Create zip
        zip_path = tmp_path / "test.zip"
        create_reproducible_zip(source, zip_path)

        # Check timestamp
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == REPRODUCIBLE_TIMESTAMP, (
                    f"ZIP entry should use fixed timestamp, got {info.date_time}"
                )
