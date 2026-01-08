#!/usr/bin/env python3
"""
agentic_provenance.py

Provenance tracking for agentic content conversions.
Tracks source files, conversion outputs, and enables update detection.

Part of Agentic Discovery & Conversion
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import _init_shared

# Import safe I/O utilities
try:
    from hash_helpers import hash_file
    from safe_io import safe_load_json, safe_write_json
except ImportError:
    # Should not happen in production with _init_shared
    raise ImportError("Could not import safe_io utilities. Ensure _shared module is available.")


# Provenance version for format compatibility
PROVENANCE_VERSION = "1.0"


class AgenticProvenance:
    """Manages provenance tracking for agentic conversions."""

    def __init__(
        self,
        provenance_dir: Path,
        verbose: bool = False,
    ):
        """
        Initialize provenance manager.

        Args:
            provenance_dir: Directory to store provenance files
            verbose: Enable verbose logging
        """
        self.provenance_dir = Path(provenance_dir)
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(f"[AGENTIC-PROVENANCE] {message}", file=sys.stderr)

    def write_provenance(
        self,
        conversions: List[Dict[str, Any]],
        repo_id: str,
        source_url: str,
    ) -> Path:
        """
        Write provenance record for agentic conversions.

        Note: URLs are sanitized before storage to prevent credential persistence.

        Args:
            conversions: List of conversion result dicts from AgenticConverter
            repo_id: Unique repository identifier
            source_url: Source repository URL or path

        Returns:
            Path to created provenance file
        """
        # Import URL sanitization utility
        try:
            from url_utils import sanitize_json_urls
        except ImportError:
            sanitize_json_urls = lambda x: x

        provenance_file = self.provenance_dir / f"agentic.{repo_id}.json"

        provenance = {
            "version": PROVENANCE_VERSION,
            "type": "agentic_conversion",
            "repo_id": repo_id,
            "source_url": source_url,
            "conversion_time": datetime.now().isoformat(),
            "converter_version": PROVENANCE_VERSION,
            "conversions": [],
        }

        for conv in conversions:
            if conv is None:
                continue

            source_path = Path(conv.get("source_path", ""))
            output_path = Path(conv.get("output_path", ""))

            conversion_record = {
                "source_path": str(source_path),
                "source_hash": hash_file(source_path) or "" if source_path.exists() else "",
                "output_path": str(output_path),
                "output_hash": hash_file(output_path) or "" if output_path.exists() else "",
                "type": conv.get("type", "unknown"),
                "classification": conv.get("classification", {}),
            }
            provenance["conversions"].append(conversion_record)

        # Sanitize URL credentials before writing to disk
        provenance = sanitize_json_urls(provenance)

        # Ensure directory exists
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

        ok = safe_write_json(provenance_file, provenance, indent=2)
        if not ok:
            raise RuntimeError(f"Failed to write agentic provenance: {provenance_file}")

        self._log(f"Wrote provenance for {len(provenance['conversions'])} conversions to {provenance_file}")
        return provenance_file

    def read_provenance(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """
        Read provenance record for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            Provenance dict or None if not found
        """
        provenance_file = self.provenance_dir / f"agentic.{repo_id}.json"
        return safe_load_json(provenance_file)

    def list_provenance(self) -> List[Dict[str, Any]]:
        """
        List all agentic provenance records.

        Returns:
            List of provenance summary dicts
        """
        records = []

        if not self.provenance_dir.exists():
            return records

        for provenance_file in self.provenance_dir.glob("agentic.*.json"):
            provenance = safe_load_json(provenance_file)
            if provenance:
                records.append(
                    {
                        "repo_id": provenance.get("repo_id", ""),
                        "source_url": provenance.get("source_url", ""),
                        "conversion_time": provenance.get("conversion_time", ""),
                        "conversion_count": len(provenance.get("conversions", [])),
                        "provenance_file": str(provenance_file),
                    }
                )

        return records

    def check_updates(self, repo_id: str) -> List[Dict[str, Any]]:
        """
        Check for changes in agentic source files that need reconversion.

        Args:
            repo_id: Repository identifier

        Returns:
            List of update dicts describing needed changes
        """
        updates = []

        provenance = self.read_provenance(repo_id)
        if not provenance:
            self._log(f"No provenance found for {repo_id}")
            return updates

        for conversion in provenance.get("conversions", []):
            source_path = Path(conversion.get("source_path", ""))

            if not source_path.exists():
                updates.append(
                    {
                        "type": "source_deleted",
                        "source_path": str(source_path),
                        "output_path": conversion.get("output_path", ""),
                        "action": "orphan_or_delete",
                    }
                )
                continue

            current_hash = hash_file(source_path) or ""
            stored_hash = conversion.get("source_hash", "")

            if current_hash != stored_hash:
                updates.append(
                    {
                        "type": "source_changed",
                        "source_path": str(source_path),
                        "output_path": conversion.get("output_path", ""),
                        "old_hash": stored_hash,
                        "new_hash": current_hash,
                        "action": "reconvert",
                    }
                )

        self._log(f"Found {len(updates)} update(s) for {repo_id}")
        return updates

    def delete_provenance(self, repo_id: str) -> bool:
        """
        Delete provenance record for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            True if deleted, False if not found
        """
        provenance_file = self.provenance_dir / f"agentic.{repo_id}.json"
        if provenance_file.exists():
            provenance_file.unlink()
            self._log(f"Deleted provenance for {repo_id}")
            return True
        return False


def write_agentic_provenance(
    conversions: List[Dict[str, Any]],
    repo_id: str,
    source_url: str,
    provenance_dir: str,
    verbose: bool = False,
) -> str:
    """
    Convenience function to write agentic provenance.

    Args:
        conversions: List of conversion result dicts
        repo_id: Repository identifier
        source_url: Source repository URL
        provenance_dir: Directory for provenance files
        verbose: Enable verbose logging

    Returns:
        Path to provenance file
    """
    manager = AgenticProvenance(
        provenance_dir=Path(provenance_dir),
        verbose=verbose,
    )
    return str(manager.write_provenance(conversions, repo_id, source_url))


def check_agentic_updates(
    repo_id: str,
    provenance_dir: str,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Convenience function to check for agentic updates.

    Args:
        repo_id: Repository identifier
        provenance_dir: Directory containing provenance files
        verbose: Enable verbose logging

    Returns:
        List of update dicts
    """
    manager = AgenticProvenance(
        provenance_dir=Path(provenance_dir),
        verbose=verbose,
    )
    return manager.check_updates(repo_id)


def main():
    """CLI entry point for provenance management."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage agentic conversion provenance")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List provenance records")
    list_parser.add_argument("--provenance-dir", required=True, help="Directory containing provenance files")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check for updates")
    check_parser.add_argument("--repo-id", required=True, help="Repository identifier")
    check_parser.add_argument("--provenance-dir", required=True, help="Directory containing provenance files")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete provenance record")
    delete_parser.add_argument("--repo-id", required=True, help="Repository identifier")
    delete_parser.add_argument("--provenance-dir", required=True, help="Directory containing provenance files")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.command == "list":
        manager = AgenticProvenance(
            provenance_dir=Path(args.provenance_dir),
            verbose=args.verbose,
        )
        records = manager.list_provenance()
        if records:
            print(json.dumps(records, indent=2))
        else:
            print("No provenance records found.")
        return 0

    elif args.command == "check":
        updates = check_agentic_updates(
            repo_id=args.repo_id,
            provenance_dir=args.provenance_dir,
            verbose=args.verbose,
        )
        if updates:
            print(json.dumps(updates, indent=2))
        else:
            print("No updates needed.")
        return 0

    elif args.command == "delete":
        manager = AgenticProvenance(
            provenance_dir=Path(args.provenance_dir),
            verbose=args.verbose,
        )
        if manager.delete_provenance(args.repo_id):
            print(f"Deleted provenance for {args.repo_id}")
            return 0
        else:
            print(f"No provenance found for {args.repo_id}")
            return 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
