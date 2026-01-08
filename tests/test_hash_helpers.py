"""
Tests for hash_helpers.py module.

Covers file hashing, string hashing, directory hashing, and file comparison utilities.
"""

import sys
from pathlib import Path

import pytest

# Setup path for modules
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "_shared"))

from hash_helpers import (
    files_match,
    has_file_changed,
    hash_directory_files,
    hash_file,
    hash_string,
)


class TestHashFile:
    """Tests for hash_file()."""

    def test_hash_file_success(self, tmp_path):
        """Hash a valid file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = hash_file(test_file)

        assert result is not None
        assert len(result) == 64  # SHA-256 hex digest length
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_hash_file_nonexistent(self, tmp_path):
        """Returns None for nonexistent file."""
        nonexistent = tmp_path / "does_not_exist.txt"

        result = hash_file(nonexistent)

        assert result is None

    def test_hash_file_directory(self, tmp_path):
        """Returns None for directory path."""
        result = hash_file(tmp_path)

        assert result is None

    def test_hash_file_empty(self, tmp_path):
        """Hash an empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = hash_file(empty_file)

        assert result is not None
        # SHA-256 of empty string
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_hash_file_binary(self, tmp_path):
        """Hash a binary file."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")

        result = hash_file(binary_file)

        assert result is not None
        assert len(result) == 64

    def test_hash_file_oserror(self, tmp_path):
        """Hash file handles OSError/IOError gracefully."""
        test_file = tmp_path / "protected.txt"
        test_file.write_text("content")

        from unittest.mock import patch

        # Mock open to raise OSError
        with patch("builtins.open", side_effect=OSError("Read error")):
            result = hash_file(test_file)
            assert result is None


class TestHashString:
    """Tests for hash_string()."""

    def test_hash_string_basic(self):
        """Hash a basic string."""
        result = hash_string("hello world")

        assert len(result) == 64
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_hash_string_empty(self):
        """Hash an empty string."""
        result = hash_string("")

        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_hash_string_unicode(self):
        """Hash a unicode string."""
        result = hash_string("こんにちは世界 🌍")

        assert result is not None
        assert len(result) == 64


class TestHashDirectoryFiles:
    """Tests for hash_directory_files()."""

    def test_hash_directory_all_files(self, tmp_path):
        """Hash all files in directory."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.txt").write_text("content3")

        result = hash_directory_files(tmp_path)

        assert len(result) == 3
        assert "file1.txt" in result
        assert "file2.txt" in result
        # Subdir file should have relative path
        assert any("file3.txt" in k for k in result.keys())

    def test_hash_directory_with_patterns(self, tmp_path):
        """Hash only files matching patterns."""
        (tmp_path / "file.txt").write_text("text")
        (tmp_path / "file.py").write_text("python")
        (tmp_path / "file.md").write_text("markdown")

        result = hash_directory_files(tmp_path, patterns=["*.py", "*.md"])

        assert len(result) == 2
        assert "file.py" in result
        assert "file.md" in result
        assert "file.txt" not in result

    def test_hash_directory_with_excludes(self, tmp_path):
        """Hash files excluding certain patterns."""
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "exclude.txt").write_text("exclude")
        (tmp_path / "also_keep.md").write_text("keep")

        result = hash_directory_files(tmp_path, exclude_patterns=["exclude.txt"])

        assert "keep.txt" in result
        assert "also_keep.md" in result
        assert "exclude.txt" not in result

    def test_hash_directory_nonexistent(self, tmp_path):
        """Returns empty dict for nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"

        result = hash_directory_files(nonexistent)

        assert result == {}

    def test_hash_directory_empty(self, tmp_path):
        """Returns empty dict for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = hash_directory_files(empty_dir)

        assert result == {}


class TestFilesMatch:
    """Tests for files_match()."""

    def test_files_match_identical(self, tmp_path):
        """Two files with same content match."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("same content")
        file2.write_text("same content")

        assert files_match(file1, file2) is True

    def test_files_match_different(self, tmp_path):
        """Two files with different content don't match."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content A")
        file2.write_text("content B")

        assert files_match(file1, file2) is False

    def test_files_match_one_missing(self, tmp_path):
        """Returns False if one file is missing."""
        file1 = tmp_path / "exists.txt"
        file2 = tmp_path / "missing.txt"
        file1.write_text("content")

        assert files_match(file1, file2) is False
        assert files_match(file2, file1) is False

    def test_files_match_both_missing(self, tmp_path):
        """Returns False if both files are missing."""
        file1 = tmp_path / "missing1.txt"
        file2 = tmp_path / "missing2.txt"

        assert files_match(file1, file2) is False


class TestHasFileChanged:
    """Tests for has_file_changed()."""

    def test_file_unchanged(self, tmp_path):
        """File with matching hash is unchanged."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        expected_hash = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        assert has_file_changed(test_file, expected_hash) is False

    def test_file_changed(self, tmp_path):
        """File with different hash has changed."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("new content")
        old_hash = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        assert has_file_changed(test_file, old_hash) is True

    def test_file_missing(self, tmp_path):
        """Missing file is considered changed."""
        missing = tmp_path / "missing.txt"
        some_hash = "abc123"

        assert has_file_changed(missing, some_hash) is True
