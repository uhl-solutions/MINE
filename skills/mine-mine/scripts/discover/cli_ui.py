"""
CLI UI formatting and printing functions for discover_integrations.

Provides testable formatting functions that return strings,
and print functions that output to configurable streams.
"""

import os
import sys
from typing import Any, Dict, List, TextIO

from .types import DiscoveryResult


def format_discovery_result(result: DiscoveryResult, verbose: bool = False) -> str:
    """
    Format discovery result as a string.

    Args:
        result: DiscoveryResult from run_discovery()
        verbose: Whether to include verbose output

    Returns:
        Formatted string for display
    """
    lines: List[str] = []

    if not result.ok:
        for error in result.errors:
            lines.append(f"Error: {error}")
        return "\n".join(lines)

    if result.dry_run:
        lines.append("[DRY-RUN] No changes made.")

    lines.append(f"\nDiscovered {result.stats.integrations_added} integration(s)")
    lines.append(f"  Locations scanned: {result.stats.locations_scanned}")
    lines.append(f"  Candidates found: {result.stats.candidates_found}")

    if result.warnings:
        lines.append("\nWarnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def format_list_result(result: DiscoveryResult, verbose: bool = False) -> str:
    """
    Format list result as a string.

    Args:
        result: DiscoveryResult from run_list()
        verbose: Whether to include verbose output

    Returns:
        Formatted string for display
    """
    lines: List[str] = []

    if not result.ok:
        for error in result.errors:
            lines.append(f"Error: {error}")
        return "\n".join(lines)

    if not result.integrations:
        lines.append("No integrations found.")
        lines.append("\nTo import Claude artifacts from a repository:")
        lines.append("  python discover_integrations.py --discover")
        lines.append("  python import_assets.py --source <url> --scope <user|project>")
        return "\n".join(lines)

    lines.append(f"Found {len(result.integrations)} integration(s):\n")

    # Group by scope
    user_scope = [i for i in result.integrations if i.get("target_scope") == "user"]
    project_scope = [i for i in result.integrations if i.get("target_scope") == "project"]

    if user_scope:
        lines.append("User-scope integrations:")
        for integration in sorted(user_scope, key=lambda x: x.get("id", "")):
            lines.append(format_integration_summary(integration, verbose))
        lines.append("")

    if project_scope:
        lines.append("Project-scope integrations:")
        for integration in sorted(project_scope, key=lambda x: x.get("id", "")):
            lines.append(format_integration_summary(integration, verbose))
        lines.append("")

    # Overall summary
    total_artifacts = sum(len(i.get("artifact_mappings", [])) for i in result.integrations)
    lines.append(f"Total: {len(result.integrations)} integration(s), {total_artifacts} artifact(s)")

    return "\n".join(lines)


def format_integration_summary(integration: Dict[str, Any], verbose: bool = False) -> str:
    """
    Format a single integration summary.

    Args:
        integration: Integration dictionary
        verbose: Whether to include verbose output

    Returns:
        Formatted string for display
    """
    lines: List[str] = []
    int_id = integration.get("id", "unknown")
    source = integration.get("source_url") or integration.get("source_path", "unknown")
    import_time = integration.get("import_time", integration.get("last_import_time", "unknown"))

    # Count artifacts
    mappings = integration.get("artifact_mappings", [])
    stale_count = sum(1 for m in mappings if m.get("dest_abspath") and not os.path.exists(m["dest_abspath"]))
    stale_tag = f" [STALE: {stale_count} file(s) missing]" if stale_count > 0 else ""

    # Format artifact summary
    artifact_counts: Dict[str, int] = {}
    for mapping in mappings:
        artifact_type = mapping.get("type", "unknown")
        artifact_counts[artifact_type] = artifact_counts.get(artifact_type, 0) + 1

    if artifact_counts:
        artifact_parts = [f"{count} {atype}(s)" for atype, count in sorted(artifact_counts.items())]
        artifact_summary = ", ".join(artifact_parts)
    else:
        marker_count = len(integration.get("markers", []))
        artifact_summary = f"{marker_count} marker(s)" if marker_count else "No artifacts tracked"

    if verbose:
        lines.append(f"  {int_id}{stale_tag}")
        lines.append(f"    Source: {source}")
        if import_time != "unknown":
            lines.append(f"    Imported: {import_time}")
        lines.append(f"    Artifacts: {artifact_summary}")
        lines.append("")
    else:
        lines.append(f"  {int_id} ({artifact_summary}){stale_tag}")
        lines.append(f"    Source: {source}")
        if import_time != "unknown":
            lines.append(f"    Imported: {import_time}")

    return "\n".join(lines)


def format_register_result(result: DiscoveryResult) -> str:
    """
    Format register result as a string.

    Args:
        result: DiscoveryResult from run_register()

    Returns:
        Formatted string for display
    """
    lines: List[str] = []

    if not result.ok:
        for error in result.errors:
            lines.append(f"Error: {error}")
        return "\n".join(lines)

    if result.dry_run:
        lines.append("[DRY-RUN] No changes made.")

    if result.integrations:
        entry = result.integrations[0]
        lines.append(f"✓ Registered integration: {entry.get('id')}")
        lines.append(f"  Source: {entry.get('source_url')}")
        lines.append(f"  Target: {entry.get('target_repo_path')}")

    return "\n".join(lines)


def print_discovery_result(result: DiscoveryResult, verbose: bool = False, stream: TextIO = sys.stdout) -> None:
    """Print discovery result to stream."""
    output = format_discovery_result(result, verbose)
    if not result.ok:
        print(output, file=sys.stderr)
    else:
        print(output, file=stream)


def print_list_result(result: DiscoveryResult, verbose: bool = False, stream: TextIO = sys.stdout) -> None:
    """Print list result to stream."""
    output = format_list_result(result, verbose)
    if not result.ok:
        print(output, file=sys.stderr)
    else:
        print(output, file=stream)


def print_register_result(result: DiscoveryResult, stream: TextIO = sys.stdout) -> None:
    """Print register result to stream."""
    output = format_register_result(result)
    if not result.ok:
        print(output, file=sys.stderr)
    else:
        print(output, file=stream)
