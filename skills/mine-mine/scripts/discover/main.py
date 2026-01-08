"""
Main orchestration entrypoint for integration discovery.

Provides run_discovery() which orchestrates the entire discovery flow
and returns structured results for easy testing and CLI usage.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from .config import DiscoverConfig
from .errors import (
    DiscoveryError,
    InvalidConfigError,
    InvalidRootError,
    OutputError,
    RegistryError,
    SafetyError,
)
from .markers import find_markers, infer_repo_name
from .registry import (
    add_integration,
    generate_integration_id,
    load_registry,
    save_registry,
)
from .scanner import scan_for_integrations
from .types import (
    DiscoveredIntegration,
    DiscoveryResult,
    DiscoveryStats,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
    EXIT_SAFETY_BLOCKED,
    EXIT_SUCCESS,
    EXIT_UNEXPECTED,
)


def run_discovery(cfg: DiscoverConfig) -> DiscoveryResult:
    """
    Orchestrate discovery end-to-end.

    This function:
    1. Validates configuration
    2. Scans configured locations for integration candidates
    3. Processes discoveries and builds integration records
    4. Updates registry (unless dry_run)
    5. Returns structured results

    Guarantees:
    - Never writes outside registry_path (path safety enforced)
    - If cfg.dry_run is True, performs NO writes
    - Returns structured results (stats, warnings/errors) for easy testing
    - Uses deterministic ordering for outputs

    Args:
        cfg: Discovery configuration

    Returns:
        DiscoveryResult with stats, integrations, and any errors/warnings
    """
    stats = DiscoveryStats()
    errors: List[str] = []
    warnings: List[str] = []
    integrations: List[Dict[str, Any]] = []

    def log(msg: str) -> None:
        if cfg.verbose:
            print(f"[DISCOVER] {msg}", file=sys.stderr)

    # Step 1: Validate configuration
    try:
        _validate_config(cfg)
    except InvalidConfigError as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_INVALID_ARGS,
            stats=stats,
            errors=[str(e)],
            dry_run=cfg.dry_run,
        )

    # Step 2: Load registry
    try:
        registry = load_registry(cfg.registry_path, log_fn=log if cfg.verbose else None)
    except Exception as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_RUNTIME_ERROR,
            stats=stats,
            errors=[f"Failed to load registry: {e}"],
            dry_run=cfg.dry_run,
        )

    # Step 3: Get search locations
    locations = cfg.get_search_locations()
    stats.locations_scanned = len(locations)
    log(f"Scanning {len(locations)} location(s)")

    # Step 4: Scan for candidates
    try:
        discoveries = scan_for_integrations(
            locations=locations,
            skip_dirs=cfg.skip_dirs,
            verbose=cfg.verbose,
            log_fn=log if cfg.verbose else None,
        )
        stats.candidates_found = len(discoveries)
    except SafetyError as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_SAFETY_BLOCKED,
            stats=stats,
            errors=[str(e)],
            dry_run=cfg.dry_run,
        )
    except Exception as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_RUNTIME_ERROR,
            stats=stats,
            errors=[f"Scan failed: {e}"],
            dry_run=cfg.dry_run,
        )

    log(f"Found {len(discoveries)} candidate(s)")

    # Step 5: Process discoveries
    for discovery in discoveries:
        try:
            integration = _process_discovery(
                discovery=discovery,
                registry=registry,
                log_fn=log if cfg.verbose else None,
            )

            if integration:
                integrations.append(integration.to_dict())
                stats.integrations_added += 1
                log(f"Added integration: {integration.id}")
            else:
                stats.integrations_skipped += 1
        except Exception as e:
            stats.errors += 1
            errors.append(f"Failed to process {discovery.get('inferred_name', 'unknown')}: {e}")

    # Step 6: Sort integrations deterministically
    integrations.sort(key=lambda x: (x.get("scope", ""), x.get("id", "")))

    # Step 7: Save registry (unless dry-run)
    if not cfg.dry_run and stats.integrations_added > 0:
        try:
            save_registry(cfg.registry_path, registry, log_fn=log if cfg.verbose else None)
            log(f"Registry saved to {cfg.registry_path}")
        except Exception as e:
            return DiscoveryResult(
                ok=False,
                exit_code=EXIT_RUNTIME_ERROR,
                stats=stats,
                integrations=integrations,
                errors=[f"Failed to save registry: {e}"],
                dry_run=cfg.dry_run,
            )

    return DiscoveryResult(
        ok=True,
        exit_code=EXIT_SUCCESS,
        stats=stats,
        integrations=integrations,
        errors=errors,
        warnings=warnings,
        dry_run=cfg.dry_run,
    )


def _validate_config(cfg: DiscoverConfig) -> None:
    """
    Validate discovery configuration.

    Args:
        cfg: Configuration to validate

    Raises:
        InvalidConfigError: If configuration is invalid
    """
    # Validate registry path
    if not cfg.registry_path:
        raise InvalidConfigError("Registry path is required")

    # Validate target_repo if specified
    if cfg.target_repo:
        if not cfg.target_repo.exists():
            raise InvalidConfigError(f"Target repository does not exist: {cfg.target_repo}")
        if not cfg.target_repo.is_dir():
            raise InvalidConfigError(f"Target repository is not a directory: {cfg.target_repo}")


def _process_discovery(
    discovery: Dict[str, Any],
    registry: Dict[str, Any],
    log_fn: Optional[Callable[[str], None]] = None,
) -> Optional[DiscoveredIntegration]:
    """
    Process a single discovery and add to registry.

    Args:
        discovery: Discovery dictionary from scanner
        registry: Registry dictionary to update
        log_fn: Optional logging function

    Returns:
        DiscoveredIntegration if added, None if skipped
    """
    inferred_name = discovery.get("inferred_name", "unknown")
    scope = discovery.get("scope", "user")
    markers = discovery.get("markers", [])

    # Generate unique ID
    integration_id = generate_integration_id(registry, scope, inferred_name)

    # Extract data from provenance markers (if present)
    source_url = None
    source_path = None
    last_import_commit = None
    artifact_mappings = []

    for marker in markers:
        if marker.get("type") == "provenance":
            source_url = marker.get("source_url") or source_url
            source_path = marker.get("source_path") or source_path
            last_import_commit = marker.get("import_commit") or last_import_commit
            artifact_mappings.extend(marker.get("artifact_mappings", []))

    # Create integration
    integration = DiscoveredIntegration(
        id=integration_id,
        name=inferred_name,
        path=Path(discovery.get("target_path", "")),
        scope=scope,
        source_url=source_url,
        source_path=source_path,
        markers=markers,
        artifact_mappings=artifact_mappings,
    )

    # Create registry entry
    entry = {
        "id": integration_id,
        "source_url": source_url,
        "source_path": source_path,
        "target_scope": scope,
        "target_repo_path": str(integration.path),
        "local_cache_clone_path": None,
        "last_import_commit": last_import_commit,
        "last_checked_commit": last_import_commit,
        "markers": markers,
        "artifact_mappings": artifact_mappings,
        "notes": f"Auto-discovered: {len(markers)} markers found",
        "update_plugins": False,
    }

    # Add to registry
    add_integration(registry, integration_id, entry)

    if log_fn and artifact_mappings:
        log_fn(f"  Loaded {len(artifact_mappings)} artifact mappings from provenance")

    return integration


def run_list(
    cfg: DiscoverConfig,
    verbose: bool = False,
) -> DiscoveryResult:
    """
    List all registered integrations.

    Args:
        cfg: Discovery configuration
        verbose: Show detailed information

    Returns:
        DiscoveryResult with integrations list
    """
    stats = DiscoveryStats()

    def log(msg: str) -> None:
        if cfg.verbose:
            print(f"[DISCOVER] {msg}", file=sys.stderr)

    try:
        registry = load_registry(cfg.registry_path, log_fn=log if cfg.verbose else None)
    except Exception as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_RUNTIME_ERROR,
            stats=stats,
            errors=[f"Failed to load registry: {e}"],
        )

    integrations_dict = registry.get("integrations", {})
    integrations = []

    for int_id, int_data in sorted(integrations_dict.items()):
        integrations.append(
            {
                "id": int_id,
                **int_data,
            }
        )

    stats.candidates_found = len(integrations)

    return DiscoveryResult(
        ok=True,
        exit_code=EXIT_SUCCESS,
        stats=stats,
        integrations=integrations,
    )


def run_register(
    cfg: DiscoverConfig,
    source_url: str,
    scope: str,
    target_repo: Optional[str] = None,
) -> DiscoveryResult:
    """
    Manually register an integration.

    Args:
        cfg: Discovery configuration
        source_url: Source repository URL
        scope: Target scope ("user" or "project")
        target_repo: Optional target repository path

    Returns:
        DiscoveryResult indicating success/failure
    """
    import re

    stats = DiscoveryStats()

    def log(msg: str) -> None:
        if cfg.verbose:
            print(f"[DISCOVER] {msg}", file=sys.stderr)

    try:
        registry = load_registry(cfg.registry_path, log_fn=log if cfg.verbose else None)
    except Exception as e:
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_RUNTIME_ERROR,
            stats=stats,
            errors=[f"Failed to load registry: {e}"],
        )

    # Extract repo name from URL
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(\.git)?$", source_url)
    if match:
        repo_name = match.group(1).replace("/", "-")
    else:
        repo_name = "manual-integration"

    # Generate ID
    integration_id = generate_integration_id(registry, scope, repo_name)

    # Determine target path
    if scope == "user":
        target_path = str(Path.home() / ".claude")
    else:
        target_path = target_repo or str(Path.cwd())

    # Create entry
    entry = {
        "id": integration_id,
        "source_url": source_url,
        "source_path": None,
        "target_scope": scope,
        "target_repo_path": target_path,
        "local_cache_clone_path": None,
        "last_import_commit": None,
        "last_checked_commit": None,
        "markers": [],
        "artifact_mappings": [],
        "notes": "Manually registered",
        "update_plugins": False,
    }

    add_integration(registry, integration_id, entry)
    stats.integrations_added = 1

    if not cfg.dry_run:
        try:
            save_registry(cfg.registry_path, registry, log_fn=log if cfg.verbose else None)
        except Exception as e:
            return DiscoveryResult(
                ok=False,
                exit_code=EXIT_RUNTIME_ERROR,
                stats=stats,
                errors=[f"Failed to save registry: {e}"],
                dry_run=cfg.dry_run,
            )

    return DiscoveryResult(
        ok=True,
        exit_code=EXIT_SUCCESS,
        stats=stats,
        integrations=[entry],
        dry_run=cfg.dry_run,
    )
