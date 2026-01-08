"""
Type definitions for integration discovery.

Provides structured types for discovery candidates, integrations, and results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class IntegrationCandidate:
    """
    A candidate integration found during scanning.

    Attributes:
        path: File or directory path representing the integration
        kind: Type of integration (e.g., "skill", "settings", "hooks")
        source: Scanner rule that found this candidate
        inferred_repo: Inferred repository name
    """

    path: Path
    kind: str
    source: str
    inferred_repo: str = "unknown"


@dataclass
class DiscoveredIntegration:
    """
    A fully parsed and validated integration.

    Attributes:
        id: Unique integration identifier
        name: Human-readable name
        path: Path to integration artifacts
        scope: Target scope ("user" or "project")
        source_url: Source repository URL (if known)
        metadata: Additional metadata dictionary
        markers: List of marker dictionaries
        artifact_mappings: List of artifact mapping dictionaries
    """

    id: str
    name: str
    path: Path
    scope: str
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    markers: List[Dict[str, Any]] = field(default_factory=list)
    artifact_mappings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "path": str(self.path),
            "scope": self.scope,
            "source_url": self.source_url,
            "source_path": self.source_path,
            "metadata": self.metadata,
            "markers": self.markers,
            "artifact_mappings": self.artifact_mappings,
        }


@dataclass
class DiscoveryStats:
    """
    Statistics from a discovery run.

    Attributes:
        locations_scanned: Number of locations scanned
        candidates_found: Number of candidate integrations found
        integrations_added: Number of integrations added to registry
        integrations_skipped: Number of integrations skipped (already registered)
        errors: Number of errors encountered
    """

    locations_scanned: int = 0
    candidates_found: int = 0
    integrations_added: int = 0
    integrations_skipped: int = 0
    errors: int = 0


@dataclass
class DiscoveryResult:
    """
    Result of a discovery operation.

    Attributes:
        ok: True if operation completed successfully
        exit_code: Exit code (0 for success)
        stats: Discovery statistics
        integrations: List of discovered integrations (JSON-serializable)
        errors: List of error messages
        warnings: List of warning messages
        dry_run: Whether this was a dry-run
    """

    ok: bool
    exit_code: int
    stats: DiscoveryStats = field(default_factory=DiscoveryStats)
    integrations: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dry_run: bool = False

    def __post_init__(self):
        """Set ok based on exit_code if not explicitly set."""
        if self.exit_code != 0:
            self.ok = False


# Exit codes (stable + testable)
EXIT_SUCCESS = 0
EXIT_INVALID_ARGS = 2
EXIT_SAFETY_BLOCKED = 3
EXIT_RUNTIME_ERROR = 4
EXIT_UNEXPECTED = 5
