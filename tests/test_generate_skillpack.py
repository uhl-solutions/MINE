#!/usr/bin/env python3
"""
test_generate_skillpack.py

Tests for skill pack generation, specifically reproducible builds.
"""

import sys
import os
import zipfile
import time
from pathlib import Path
import pytest
import shutil

# Add scripts directory to path to import generate_skillpack
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "mine" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_skillpack import create_reproducible_zip


class TestReproducibleZip:
    """Verify that skillpack zips are deterministic."""

    def test_zip_is_deterministic(self, tmp_path):
        """Two zips created from the same content must have identical hashes."""
        # Create source content
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Add some files with different timestamps
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        dir1 = source_dir / "subdir"
        dir1.mkdir()
        (dir1 / "file3.txt").write_text("content3")

        # Set random mtimes to ensure we ignore them
        os.utime(source_dir / "file1.txt", (10000, 10000))
        os.utime(source_dir / "file2.txt", (20000, 20000))

        # Generate two zips
        zip1 = tmp_path / "pack1.zip"
        zip2 = tmp_path / "pack2.zip"

        # Wait a bit or change system time if possible (not easy in test)
        # But create_reproducible_zip handles timestamp normalization

        create_reproducible_zip(zip1, source_dir)

        # Modify mtime again to be sure
        os.utime(source_dir / "file1.txt", (30000, 30000))

        create_reproducible_zip(zip2, source_dir)

        # Compare binary content
        assert zip1.read_bytes() == zip2.read_bytes(), (
            "Zip files should be identical regardless of input file timestamps"
        )

    def test_zip_timestamps_are_fixed(self, tmp_path):
        """Entries in zip should have the fixed timestamp (2025-01-01)."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("content")

        zip_path = tmp_path / "test.zip"
        create_reproducible_zip(zip_path, source_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            info = zf.getinfo("test.txt")
            # 2025-01-01 00:00:00
            assert info.date_time == (2025, 1, 1, 0, 0, 0), f"Expected fixed timestamp, got {info.date_time}"

    def test_zip_permissions_are_normalized(self, tmp_path):
        """Permissions should be normalized to 644/755."""
        if os.name == "nt":
            pytest.skip("Permission normalization test requires Unix-like OS")

        source_dir = tmp_path / "source_perms"
        source_dir.mkdir()

        script = source_dir / "script.sh"
        script.write_text("#!/bin/sh\nexit 0")
        script.chmod(0o777)  # rwxrwxrwx

        data = source_dir / "data.txt"
        data.write_text("data")
        data.chmod(0o600)  # rw-------

        zip_path = tmp_path / "perms.zip"
        create_reproducible_zip(zip_path, source_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Check script (should retain execute bit -> 755)
            # External attr: high byte is Unix mode
            # 0o755 << 16
            script_info = zf.getinfo("script.sh")
            mode = script_info.external_attr >> 16
            assert mode == 0o100755, f"Expected 0o100755, got {oct(mode)}"

            # Check data (should be 644)
            data_info = zf.getinfo("data.txt")
            mode = data_info.external_attr >> 16
            assert mode == 0o100644, f"Expected 0o100644, got {oct(mode)}"
