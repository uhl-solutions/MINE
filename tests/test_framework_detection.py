#!/usr/bin/env python3
"""
test_framework_detection.py

Tests for framework detection logic in scan_repo.py.
Verifies that Fabric, LangChain, and AutoGen detection avoids false positives.
"""

import sys
import os
from pathlib import Path
import pytest

# Add scripts modules to path
MINE_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "mine" / "scripts"
SHARED_DIR = Path(__file__).resolve().parent.parent / "skills" / "_shared"
if str(MINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MINE_SCRIPTS))
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))


class TestFabricDetection:
    """Tests for Fabric repository detection."""

    def test_fabric_readme_only_is_false(self, tmp_path):
        """Repository with README mentioning 'fabric' and 'patterns' but no structure should NOT be detected as Fabric."""
        # Create a repo with only a README mentioning Fabric
        readme = tmp_path / "README.md"
        readme.write_text("""
        # My Project
        
        This project uses fabric patterns for various things.
        It integrates with the fabric ecosystem.
        
        ## Features
        - Uses patterns from fabric
        - Great patterns
        """)

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should NOT detect as Fabric (no structural indicators)
        assert scanner._is_fabric_repo() is False

    def test_fabric_with_patterns_dir_only_is_false(self, tmp_path):
        """Repository with 'patterns' directory but no system.md files should NOT be detected as Fabric."""
        # Create patterns dir without Fabric-style structure
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create a pattern without system.md
        pattern1 = patterns_dir / "my_pattern"
        pattern1.mkdir()
        (pattern1 / "config.json").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should NOT detect as Fabric (no system.md)
        assert scanner._is_fabric_repo() is False

    def test_fabric_with_patterns_and_system_md_is_true(self, tmp_path):
        """Repository with 'patterns/*/system.md' structure should be detected as Fabric."""
        # Create proper Fabric pattern structure
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create a Fabric-style pattern
        pattern1 = patterns_dir / "analyze_code"
        pattern1.mkdir()
        (pattern1 / "system.md").write_text("You are an expert code analyst...")

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should detect as Fabric
        assert scanner._is_fabric_repo() is True

    def test_fabric_with_cmd_fabric_is_true(self, tmp_path):
        """Repository with 'cmd/fabric' directory should be detected as Fabric."""
        # Create cmd/fabric structure (official Fabric layout)
        cmd_dir = tmp_path / "cmd" / "fabric"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "main.go").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should detect as Fabric
        assert scanner._is_fabric_repo() is True

    def test_generic_patterns_word_in_readme_is_false(self, tmp_path):
        """Repository mentioning 'patterns' in README without fabric should NOT be detected."""
        readme = tmp_path / "README.md"
        readme.write_text("""
        # Design Patterns
        
        This project demonstrates common design patterns:
        - Factory pattern
        - Observer pattern
        - Singleton pattern
        
        All patterns are implemented in TypeScript.
        """)

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should NOT detect as Fabric
        assert scanner._is_fabric_repo() is False

    def test_fabric_readme_with_danielmiessler_and_structure_is_true(self, tmp_path):
        """Repository with README mentioning 'danielmiessler' and some structure should be detected."""
        # Create minimal structure
        (tmp_path / "patterns").mkdir()
        (tmp_path / "client").mkdir()

        readme = tmp_path / "README.md"
        readme.write_text("""
        # Fabric Patterns Collection
        
        Inspired by danielmiessler/fabric.
        
        These are prompts for AI systems.
        """)

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should detect (README tie-breaker with structure)
        assert scanner._is_fabric_repo() is True


class TestLangChainDetection:
    """Tests for LangChain repository detection."""

    def test_langchain_with_langchain_dir_is_true(self, tmp_path):
        """Repository with 'langchain' directory should be detected as LangChain."""
        langchain_dir = tmp_path / "langchain"
        langchain_dir.mkdir()
        (langchain_dir / "__init__.py").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_langchain_repo() is True

    def test_langchain_with_libs_langchain_is_true(self, tmp_path):
        """Repository with 'libs/langchain' directory should be detected as LangChain."""
        libs_dir = tmp_path / "libs" / "langchain"
        libs_dir.mkdir(parents=True)
        (libs_dir / "__init__.py").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_langchain_repo() is True

    def test_langchain_without_structure_is_false(self, tmp_path):
        """Repository without LangChain directories should NOT be detected."""
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("Uses langchain library")

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_langchain_repo() is False


class TestAutoGenDetection:
    """Tests for AutoGen repository detection."""

    def test_autogen_with_autogen_dir_is_true(self, tmp_path):
        """Repository with 'autogen' directory should be detected as AutoGen."""
        autogen_dir = tmp_path / "autogen"
        autogen_dir.mkdir()
        (autogen_dir / "__init__.py").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_autogen_repo() is True

    def test_autogen_with_notebook_and_autogen_is_true(self, tmp_path):
        """Repository with 'notebook' and 'autogen' directories should be detected."""
        (tmp_path / "notebook").mkdir()
        (tmp_path / "autogen").mkdir()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_autogen_repo() is True

    def test_autogen_without_structure_is_false(self, tmp_path):
        """Repository without AutoGen directories should NOT be detected."""
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("Uses autogen for automation")

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_autogen_repo() is False


class TestFrameworkDetectionEdgeCases:
    """Edge case tests for framework detection."""

    def test_empty_repo_no_detection(self, tmp_path):
        """Empty repository should not be detected as any framework."""
        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_fabric_repo() is False
        assert scanner._is_langchain_repo() is False
        assert scanner._is_autogen_repo() is False

    def test_hidden_directories_ignored(self, tmp_path):
        """Hidden directories starting with . should not trigger detection."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create a hidden pattern (should be ignored)
        hidden_pattern = patterns_dir / ".hidden_pattern"
        hidden_pattern.mkdir()
        (hidden_pattern / "system.md").touch()

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        # Should NOT detect (only hidden pattern exists)
        assert scanner._is_fabric_repo() is False

    def test_multiple_patterns_detected(self, tmp_path):
        """Repository with multiple valid patterns should be detected."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create multiple Fabric patterns
        for name in ["analyze", "summarize", "explain"]:
            pattern = patterns_dir / name
            pattern.mkdir()
            (pattern / "system.md").write_text(f"You are a {name} expert...")

        from scan_repo import RepoScanner

        scanner = RepoScanner(str(tmp_path))
        scanner.repo_path = tmp_path

        assert scanner._is_fabric_repo() is True
