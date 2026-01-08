"""
Discover module - Modular integration discovery components.

This package provides the building blocks for discovering and managing
integrated Claude Code repositories.
"""

from .cli_ui import (
    format_discovery_result,
    format_integration_summary,
    format_list_result,
    format_register_result,
    print_discovery_result,
    print_list_result,
    print_register_result,
)
from .config import DEFAULT_REGISTRY_PATH, DiscoverConfig
from .errors import (
    DiscoveryError,
    InvalidConfigError,
    InvalidRootError,
    OutputError,
    RegistryError,
    SafetyError,
)
from .main import run_discovery, run_list, run_register
from .markers import (
    MARKER_PATTERNS,
    find_markers,
    infer_repo_name,
)
from .registry import (
    DEFAULT_REGISTRY_STRUCTURE,
    load_registry,
    save_registry,
)
from .scanner import (
    scan_for_integrations,
    scan_location,
)
from .types import (
    DiscoveredIntegration,
    DiscoveryResult,
    DiscoveryStats,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
    EXIT_SAFETY_BLOCKED,
    EXIT_SUCCESS,
    EXIT_UNEXPECTED,
    IntegrationCandidate,
)
from .unregister import run_unregister

__all__ = [
    # Config
    "DiscoverConfig",
    "DEFAULT_REGISTRY_PATH",
    # Errors
    "DiscoveryError",
    "InvalidConfigError",
    "InvalidRootError",
    "OutputError",
    "RegistryError",
    "SafetyError",
    # Main orchestration
    "run_discovery",
    "run_list",
    "run_register",
    "run_unregister",
    # CLI UI
    "format_discovery_result",
    "format_list_result",
    "format_register_result",
    "format_integration_summary",
    "print_discovery_result",
    "print_list_result",
    "print_register_result",
    # Markers
    "find_markers",
    "infer_repo_name",
    "MARKER_PATTERNS",
    # Scanner
    "scan_location",
    "scan_for_integrations",
    # Registry
    "load_registry",
    "save_registry",
    "DEFAULT_REGISTRY_STRUCTURE",
    # Types
    "IntegrationCandidate",
    "DiscoveredIntegration",
    "DiscoveryStats",
    "DiscoveryResult",
    "EXIT_SUCCESS",
    "EXIT_INVALID_ARGS",
    "EXIT_SAFETY_BLOCKED",
    "EXIT_RUNTIME_ERROR",
    "EXIT_UNEXPECTED",
]
