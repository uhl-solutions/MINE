#!/usr/bin/env python3
"""
artifact_types.py - Shared constants and types for Claude Code artifacts

Centralizes artifact type definitions, destination patterns, and
validation logic used across scan_repo.py, import_assets.py, and
other scripts.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ArtifactType(str, Enum):
    """Standard Claude Code artifact types."""

    SKILL = "skill"
    COMMAND = "command"
    AGENT = "agent"
    HOOK = "hook"
    HOOK_CONFIG = "hook_config"
    MCP_CONFIG = "mcp_config"
    CLAUDE_MD = "claude_md"
    DOCUMENTATION = "documentation"
    BUILD_FILE = "build_file"
    PLUGIN = "plugin"
    # Framework-specific
    FABRIC_PATTERN = "fabric_pattern"
    LANGCHAIN_CHAIN = "langchain_chain"
    AUTOGEN_AGENT = "autogen_agent"
    # Agentic discovery
    AGENTIC_COMMAND = "agentic_command"
    AGENTIC_AGENT = "agentic_agent"


class Scope(str, Enum):
    """Installation scope for artifacts."""

    USER = "user"
    PROJECT = "project"


class ImportMode(str, Enum):
    """Import operation modes."""

    AUTO = "auto"
    IMPORT = "import"
    CONVERT = "convert"
    GENERATE = "generate"


class FrameworkType(str, Enum):
    """Supported AI frameworks for conversion."""

    FABRIC = "fabric"
    LANGCHAIN = "langchain"
    AUTOGEN = "autogen"


@dataclass
class DestinationPattern:
    """Destination path pattern for an artifact type."""

    user_pattern: str
    project_pattern: str


# Artifact type to destination mapping
ARTIFACT_DESTINATIONS: Dict[ArtifactType, DestinationPattern] = {
    ArtifactType.SKILL: DestinationPattern(
        user_pattern="~/.claude/skills/{name}/", project_pattern=".claude/skills/{name}/"
    ),
    ArtifactType.COMMAND: DestinationPattern(
        user_pattern="~/.claude/commands/{name}", project_pattern=".claude/commands/{name}"
    ),
    ArtifactType.AGENT: DestinationPattern(
        user_pattern="~/.claude/agents/{name}", project_pattern=".claude/agents/{name}"
    ),
    ArtifactType.HOOK: DestinationPattern(
        user_pattern="~/.claude/hooks.imported.{repo_id}/{name}",
        project_pattern=".claude/hooks.imported.{repo_id}/{name}",
    ),
    ArtifactType.MCP_CONFIG: DestinationPattern(
        user_pattern="~/.mcp.imported.{repo_id}.json", project_pattern=".mcp.imported.{repo_id}.json"
    ),
    ArtifactType.CLAUDE_MD: DestinationPattern(
        user_pattern="~/.claude/CLAUDE.imported.{repo_id}.md", project_pattern=".claude/CLAUDE.imported.{repo_id}.md"
    ),
}

# Scan limits
MAX_ARTIFACTS = 1000
MAX_SCAN_TIME = 300  # 5 minutes

# Glob patterns for artifact detection
SKILL_PATTERNS = [".claude/skills/**/SKILL.md", "skills/**/SKILL.md"]

COMMAND_PATTERNS = [".claude/commands/*.md", "commands/*.md"]

AGENT_PATTERNS = [".claude/agents/*.md", "agents/*.md"]

HOOK_PATTERNS = [".claude/hooks/*", ".claude/hooks/**/*"]

MCP_PATTERNS = [".mcp.json", ".claude-plugin/mcp.json", "mcp.json"]

DOC_PATTERNS = ["CLAUDE.md", "README.md", "README.rst", "README.txt", "CONTRIBUTING.md"]

BUILD_PATTERNS = ["Makefile", "package.json", "pyproject.toml", "setup.py", "requirements.txt", "Cargo.toml", "go.mod"]


def get_destination(artifact_type: ArtifactType, scope: Scope, name: str, repo_id: Optional[str] = None) -> str:
    """Get destination path for an artifact.

    Args:
        artifact_type: Type of artifact
        scope: User or project scope
        name: Artifact name (filename or directory)
        repo_id: Repository identifier for imported artifacts

    Returns:
        Destination path string
    """
    pattern = ARTIFACT_DESTINATIONS.get(artifact_type)
    if not pattern:
        return ""

    template = pattern.user_pattern if scope == Scope.USER else pattern.project_pattern
    return template.format(name=name, repo_id=repo_id or "unknown")


def sanitize_repo_id(source: str) -> str:
    """Sanitize a source URL/path into a safe repo ID.

    Converts 'owner/repo' to 'owner-repo' for filesystem safety.
    """
    import re

    # Extract from GitHub URL
    if source.startswith("http"):
        match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", source)
        if match:
            return match.group(1).replace("/", "-")
        return "unknown-repo"
    # Local path: use directory name
    from pathlib import Path

    return Path(source).name


def is_importable_artifact(artifact_type: ArtifactType) -> bool:
    """Check if an artifact type can be directly imported."""
    return artifact_type in {
        ArtifactType.SKILL,
        ArtifactType.COMMAND,
        ArtifactType.AGENT,
        ArtifactType.HOOK,
        ArtifactType.MCP_CONFIG,
    }


def is_convertible_artifact(artifact_type: ArtifactType) -> bool:
    """Check if an artifact type requires conversion."""
    return artifact_type in {
        ArtifactType.FABRIC_PATTERN,
        ArtifactType.LANGCHAIN_CHAIN,
        ArtifactType.AUTOGEN_AGENT,
    }
