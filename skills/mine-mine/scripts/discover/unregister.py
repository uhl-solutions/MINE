"""
Unregister functionality for integration discovery.

Provides run_unregister() which removes integrations from the registry
and optionally deletes imported artifacts.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import DiscoverConfig
from .registry import load_registry, save_registry
from .types import (
    DiscoveryResult,
    DiscoveryStats,
    EXIT_INVALID_ARGS,
    EXIT_RUNTIME_ERROR,
    EXIT_SUCCESS,
)


def run_unregister(
    cfg: DiscoverConfig,
    integration_id: str,
    delete_files: bool = False,
    force: bool = False,
) -> DiscoveryResult:
    """
    Unregister an integration from the registry.

    Removes the integration entry from the registry and optionally deletes
    imported artifacts. Local modifications are detected and protected.

    Args:
        cfg: Discovery configuration
        integration_id: ID of integration to remove
        delete_files: If True, also delete imported artifacts (with backup)
        force: If True, delete even locally modified files (with backup)

    Returns:
        DiscoveryResult indicating success/failure
    """

    def log(msg: str) -> None:
        if cfg.verbose:
            print(f"[UNREGISTER] {msg}", file=sys.stderr)

    # Load registry
    registry = load_registry(cfg.registry_path)
    integrations = registry.get("integrations", {})

    # Check if integration exists
    if integration_id not in integrations:
        available = list(integrations.keys())
        error_msg = (
            f"Integration not found: {integration_id}\n"
            f"Available integrations: {', '.join(available) if available else '(none)'}"
        )
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_INVALID_ARGS,
            errors=[error_msg],
            dry_run=cfg.dry_run,
        )

    integration = integrations[integration_id]
    log(f"Found integration: {integration_id}")

    # Collect file information
    files_to_delete: List[Path] = []
    modified_files: List[str] = []
    missing_files: List[str] = []
    staged_files: List[Tuple[str, Path]] = []

    # Process artifact mappings
    for mapping in integration.get("artifact_mappings", []):
        dest = mapping.get("dest_abspath", "")
        if not dest:
            continue

        dest_path = Path(dest)
        if not dest_path.exists():
            missing_files.append(str(dest_path))
            continue

        # Check if file was locally modified
        try:
            from hash_helpers import hash_file

            current_hash = hash_file(dest_path)
            expected_hash = mapping.get("last_import_hash")

            if expected_hash and current_hash != expected_hash:
                modified_files.append(str(dest_path))
            else:
                files_to_delete.append(dest_path)
        except Exception:
            modified_files.append(str(dest_path))

    # Collect staged files
    for marker in integration.get("markers", []):
        if marker.get("type") == "hooks_import":
            hooks_dir = Path(marker.get("dir", ""))
            if hooks_dir.exists():
                staged_files.append(("hooks_dir", hooks_dir))
        elif marker.get("type") == "mcp_import":
            mcp_file = Path(marker.get("file", ""))
            if mcp_file.exists():
                staged_files.append(("mcp_file", mcp_file))
        elif marker.get("type") == "claude_md_import":
            claude_file = Path(marker.get("file", ""))
            if claude_file.exists():
                staged_files.append(("claude_md", claude_file))

    # Build summary output
    source = integration.get("source_url") or integration.get("source_path", "unknown")
    scope = integration.get("target_scope", "unknown")
    prefix = "[DRY-RUN] " if cfg.dry_run else ""

    output_lines: List[str] = []
    output_lines.append(f"\n{prefix}Unregistering integration: {integration_id}")
    output_lines.append(f"  Source: {source}")
    output_lines.append(f"  Scope: {scope}")

    artifact_count = len(files_to_delete) + len(modified_files) + len(missing_files)
    output_lines.append(f"\n  Artifacts tracked: {artifact_count}")

    if files_to_delete:
        output_lines.append(f"    Clean (can delete): {len(files_to_delete)}")
    if modified_files:
        output_lines.append(f"    Locally modified: {len(modified_files)}")
        if not force:
            output_lines.append("      → Will be SKIPPED (use --force to include)")
    if missing_files:
        output_lines.append(f"    Already missing: {len(missing_files)}")
    if staged_files:
        output_lines.append(f"    Staged imports: {len(staged_files)}")

    # Determine what to delete
    to_delete: List[Path] = []
    if delete_files:
        to_delete.extend(files_to_delete)
        if force:
            to_delete.extend([Path(f) for f in modified_files])

    # Show what will happen
    if delete_files:
        if to_delete:
            output_lines.append(f"\n  {prefix}Files to delete: {len(to_delete)}")
            for f in to_delete[:5]:
                output_lines.append(f"    - {f}")
            if len(to_delete) > 5:
                output_lines.append(f"    ... and {len(to_delete) - 5} more")

        if staged_files:
            output_lines.append(f"\n  {prefix}Staged imports to delete: {len(staged_files)}")
            for ftype, fpath in staged_files[:3]:
                output_lines.append(f"    - [{ftype}] {fpath}")
            if len(staged_files) > 3:
                output_lines.append(f"    ... and {len(staged_files) - 3} more")
    else:
        output_lines.append("\n  Files will NOT be deleted (use --delete-files)")

    output_lines.append(f"\n  {prefix}Registry entry will be removed")

    # Print summary
    print("\n".join(output_lines))

    # Dry-run: report what would happen without changes
    if cfg.dry_run:
        print(f"\n{prefix}No changes made. Use --dry-run=false to execute.")
        return DiscoveryResult(
            ok=True,
            exit_code=EXIT_SUCCESS,
            integrations=[integration],
            dry_run=True,
            stats=DiscoveryStats(
                integrations_skipped=len(modified_files) if not force else 0,
            ),
        )

    # Execute deletions
    files_deleted: List[str] = []
    files_backed_up: List[str] = []
    staged_deleted: List[str] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        from transaction import TransactionError, UpdateTransaction

        with UpdateTransaction(verbose=cfg.verbose) as txn:
            if delete_files and to_delete:
                print(f"\n  Deleting {len(to_delete)} artifact file(s)...")

                for dest in to_delete:
                    if dest.exists():
                        backup_path = Path(str(dest) + f".unregister-bak.{timestamp}")
                        txn.copy_file(dest, backup_path)
                        files_backed_up.append(str(backup_path))

                        txn.delete_file(dest)
                        files_deleted.append(str(dest))
                        print(f"    ✓ Deleted: {dest}")
                        print(f"      Backup: {backup_path}")

            if delete_files and staged_files:
                import shutil

                print(f"\n  Deleting {len(staged_files)} staged import(s)...")
                for ftype, fpath in staged_files:
                    if fpath.is_dir():
                        backup_dir = Path(str(fpath) + f".unregister-bak.{timestamp}")
                        shutil.copytree(fpath, backup_dir)
                        shutil.rmtree(fpath)
                        staged_deleted.append(str(fpath))
                        print(f"    ✓ Deleted dir: {fpath}")
                    elif fpath.exists():
                        backup_path = Path(str(fpath) + f".unregister-bak.{timestamp}")
                        txn.copy_file(fpath, backup_path)
                        txn.delete_file(fpath)
                        staged_deleted.append(str(fpath))
                        print(f"    ✓ Deleted: {fpath}")

            txn.commit()

    except Exception as e:
        error_msg = f"Transaction failed: {e}"
        print(f"\n❌ {error_msg}")
        print("↺ All file changes have been rolled back.")
        return DiscoveryResult(
            ok=False,
            exit_code=EXIT_RUNTIME_ERROR,
            errors=[error_msg],
            dry_run=False,
        )

    # Remove from registry
    del integrations[integration_id]
    save_registry(cfg.registry_path, registry)

    # Success output
    print(f"\n✓ Successfully unregistered: {integration_id}")
    if files_deleted:
        print(f"  Deleted: {len(files_deleted)} file(s)")
        print(f"  Backups created with .unregister-bak.{timestamp} suffix")
    if modified_files and not force:
        print(f"  Skipped (modified): {len(modified_files)} file(s)")

    return DiscoveryResult(
        ok=True,
        exit_code=EXIT_SUCCESS,
        integrations=[integration],
        dry_run=False,
        stats=DiscoveryStats(
            integrations_added=0,
            integrations_skipped=len(modified_files) if not force else 0,
        ),
    )
