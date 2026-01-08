#!/usr/bin/env python3
"""
test_artifact_types.py - Tests for the artifact_types shared module
"""

import pytest
import sys
from pathlib import Path

# Add _shared to path
_shared_dir = Path(__file__).resolve().parent.parent / "skills" / "_shared"
if str(_shared_dir) not in sys.path:
    sys.path.insert(0, str(_shared_dir))

from artifact_types import (
    ArtifactType,
    Scope,
    ImportMode,
    FrameworkType,
    get_destination,
    sanitize_repo_id,
    is_importable_artifact,
    is_convertible_artifact,
    MAX_ARTIFACTS,
    MAX_SCAN_TIME,
    SKILL_PATTERNS,
    COMMAND_PATTERNS,
)


class TestArtifactType:
    """Tests for ArtifactType enum."""

    def test_artifact_type_values(self):
        """Verify core artifact type values."""
        assert ArtifactType.SKILL.value == "skill"
        assert ArtifactType.COMMAND.value == "command"
        assert ArtifactType.AGENT.value == "agent"
        assert ArtifactType.HOOK.value == "hook"
        assert ArtifactType.MCP_CONFIG.value == "mcp_config"

    def test_artifact_type_is_string_enum(self):
        """ArtifactType should be usable as string comparison."""
        # String enum allows value comparison
        assert ArtifactType.SKILL.value == "skill"
        assert ArtifactType.COMMAND.value == "command"


class TestScope:
    """Tests for Scope enum."""

    def test_scope_values(self):
        """Verify scope values."""
        assert Scope.USER.value == "user"
        assert Scope.PROJECT.value == "project"


class TestImportMode:
    """Tests for ImportMode enum."""

    def test_import_mode_values(self):
        """Verify import mode values."""
        assert ImportMode.AUTO.value == "auto"
        assert ImportMode.IMPORT.value == "import"
        assert ImportMode.CONVERT.value == "convert"
        assert ImportMode.GENERATE.value == "generate"


class TestFrameworkType:
    """Tests for FrameworkType enum."""

    def test_framework_type_values(self):
        """Verify framework type values."""
        assert FrameworkType.FABRIC.value == "fabric"
        assert FrameworkType.LANGCHAIN.value == "langchain"
        assert FrameworkType.AUTOGEN.value == "autogen"


class TestGetDestination:
    """Tests for get_destination function."""

    def test_skill_destination_user_scope(self):
        """Get skill destination for user scope."""
        dest = get_destination(ArtifactType.SKILL, Scope.USER, "my-skill")
        assert dest == "~/.claude/skills/my-skill/"

    def test_skill_destination_project_scope(self):
        """Get skill destination for project scope."""
        dest = get_destination(ArtifactType.SKILL, Scope.PROJECT, "my-skill")
        assert dest == ".claude/skills/my-skill/"

    def test_command_destination(self):
        """Get command destination."""
        dest = get_destination(ArtifactType.COMMAND, Scope.USER, "build.md")
        assert dest == "~/.claude/commands/build.md"

    def test_agent_destination(self):
        """Get agent destination."""
        dest = get_destination(ArtifactType.AGENT, Scope.PROJECT, "reviewer.md")
        assert dest == ".claude/agents/reviewer.md"

    def test_hook_destination_with_repo_id(self):
        """Get hook destination with repo ID."""
        dest = get_destination(ArtifactType.HOOK, Scope.USER, "pre-commit.sh", "user-repo")
        assert dest == "~/.claude/hooks.imported.user-repo/pre-commit.sh"

    def test_unknown_artifact_type_returns_empty(self):
        """Unknown artifact type returns empty string."""
        dest = get_destination(ArtifactType.DOCUMENTATION, Scope.USER, "README.md")
        assert dest == ""


class TestSanitizeRepoId:
    """Tests for sanitize_repo_id function."""

    def test_github_url(self):
        """Sanitize GitHub URL to repo ID."""
        repo_id = sanitize_repo_id("https://github.com/owner/repo")
        assert repo_id == "owner-repo"

    def test_github_url_with_git_suffix(self):
        """Sanitize GitHub URL with .git suffix."""
        repo_id = sanitize_repo_id("https://github.com/owner/repo.git")
        assert repo_id == "owner-repo"

    def test_local_path(self):
        """Sanitize local path to repo ID."""
        repo_id = sanitize_repo_id("/home/user/projects/my-project")
        assert repo_id == "my-project"

    def test_relative_path(self):
        """Sanitize relative path to repo ID."""
        repo_id = sanitize_repo_id("./my-project")
        assert repo_id == "my-project"

    def test_unknown_repo_url(self):
        """Sanitize unknown URL (non-GitHub) defaults to 'unknown-repo'."""
        repo_id = sanitize_repo_id("https://gitlab.com/owner/repo.git")
        assert repo_id == "unknown-repo"


class TestIsImportableArtifact:
    """Tests for is_importable_artifact function."""

    def test_skill_is_importable(self):
        """Skills are importable."""
        assert is_importable_artifact(ArtifactType.SKILL) is True

    def test_command_is_importable(self):
        """Commands are importable."""
        assert is_importable_artifact(ArtifactType.COMMAND) is True

    def test_fabric_pattern_not_importable(self):
        """Fabric patterns require conversion, not direct import."""
        assert is_importable_artifact(ArtifactType.FABRIC_PATTERN) is False

    def test_documentation_not_importable(self):
        """Documentation is not directly importable."""
        assert is_importable_artifact(ArtifactType.DOCUMENTATION) is False


class TestIsConvertibleArtifact:
    """Tests for is_convertible_artifact function."""

    def test_fabric_pattern_is_convertible(self):
        """Fabric patterns are convertible."""
        assert is_convertible_artifact(ArtifactType.FABRIC_PATTERN) is True

    def test_langchain_chain_is_convertible(self):
        """LangChain chains are convertible."""
        assert is_convertible_artifact(ArtifactType.LANGCHAIN_CHAIN) is True

    def test_skill_not_convertible(self):
        """Skills are not convertible (already Claude format)."""
        assert is_convertible_artifact(ArtifactType.SKILL) is False


class TestConstants:
    """Tests for module constants."""

    def test_max_artifacts_is_reasonable(self):
        """MAX_ARTIFACTS should be a reasonable limit."""
        assert MAX_ARTIFACTS == 1000
        assert isinstance(MAX_ARTIFACTS, int)

    def test_max_scan_time_is_reasonable(self):
        """MAX_SCAN_TIME should be a reasonable timeout."""
        assert MAX_SCAN_TIME == 300  # 5 minutes
        assert isinstance(MAX_SCAN_TIME, int)

    def test_skill_patterns_exist(self):
        """Skill patterns should be defined."""
        assert len(SKILL_PATTERNS) > 0
        assert any("SKILL.md" in p for p in SKILL_PATTERNS)

    def test_command_patterns_exist(self):
        """Command patterns should be defined."""
        assert len(COMMAND_PATTERNS) > 0
        assert any("commands" in p for p in COMMAND_PATTERNS)
