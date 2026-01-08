#!/usr/bin/env python3
"""
update_integrations.py - Update integrated Claude Code repositories

Checks for upstream changes and updates local integrated artifacts safely.
"""

import argparse
import hashlib
import os
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import helpers
sys.path.insert(0, os.path.dirname(__file__))
from discover_integrations import IntegrationDiscovery
from git_helpers import *
from transaction import TransactionError, UpdateTransaction

from hash_helpers import *
from path_safety import PathSafetyError, validate_path

import _init_shared
from safe_io import safe_write_text
from cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run
from logging_utils import setup_logging, get_logger, add_logging_arguments

try:
    from . import platform_utils
except ImportError:
    import platform_utils

try:
    from cache_eviction import CacheManager, enforce_limits
except ImportError:
    # Allow running if cache_eviction is not found
    def enforce_limits(*args, **kwargs):
        pass

    class CacheManager:
        def __init__(self, *args, **kwargs):
            pass

        def touch(self, *args):
            pass


GIT_STATUS_HANDLERS = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",  # R<score> old\tnew
    "C": "copied",  # C<score> old\tnew
    "T": "typechange",  # File type changed (e.g., regular -> symlink)
    "U": "unmerged",  # Conflict marker
    "X": "unknown",  # Should never happen
    "B": "broken",  # Broken pairing
}


def _classify_git_status(status: str) -> tuple:
    """
    Parse git status code.
    Returns: (base_status, similarity_score or None)
    """
    if not status:
        return ("unknown", None)

    base = status[0]

    # R and C have similarity scores: R100, C075, etc.
    if base in ("R", "C") and len(status) > 1:
        try:
            score = int(status[1:])
            return (base, score)
        except ValueError:
            return (base, None)

    return (base, None)


class IntegrationUpdater:
    """Updates integrated repositories with upstream changes."""

    def __init__(
        self,
        registry_path: Path,
        dry_run: bool = True,
        auto_import_new: bool = False,
        delete_policy: str = "ask",
        verbose: bool = False,
    ):
        self.registry_path = registry_path
        self.dry_run = dry_run
        # verbose is deprecated, handled via logging, but kept for compatibility
        self.verbose = verbose
        self.auto_import_new = auto_import_new
        self.delete_policy = delete_policy
        self.logger = get_logger(__name__)
        self.discovery = IntegrationDiscovery(registry_path, self.logger.isEnabledFor(logging.DEBUG))
        self.registry = self.discovery.registry
        self.cache_dir = Path.home() / ".claude" / "mine" / "sources"
        self.cache_manager = CacheManager(self.cache_dir, verbose=self.logger.isEnabledFor(logging.DEBUG))

    def _log(self, message: str):
        self.logger.debug(message)

    def _save_registry(self):
        """Save registry to disk via discovery instance."""
        self.discovery._save_registry()

    def check_updates(self, integration_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Check for updates in one or all integrations."""
        updates_available = []

        integrations_to_check = {}
        if integration_id:
            if integration_id in self.registry["integrations"]:
                integrations_to_check[integration_id] = self.registry["integrations"][integration_id]
        else:
            integrations_to_check = self.registry["integrations"]

        for int_id, integration in integrations_to_check.items():
            self._log(f"Checking {int_id}...")
            update_info = self._check_single_integration(int_id, integration)
            if update_info:
                updates_available.append(update_info)

        return updates_available

    def _check_single_integration(self, int_id: str, integration: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check a single integration for updates."""
        source_url = integration.get("source_url")
        source_path = integration.get("source_path")

        # Handle local path sources - clone to cache
        if source_path and not source_url:
            source_path_resolved = Path(source_path).resolve()
            if not source_path_resolved.exists() or not (source_path_resolved / ".git").exists():
                self._log(f"Skipping {int_id}: source path not a git repo")
                return None

            # Clone local repo to cache (so we don't disturb user's repo)
            # Use hash-based cache name to prevent collisions (P0.2)
            # e.g., ~/code/foo and ~/work/foo will get different cache dirs
            path_hash = hashlib.sha256(str(source_path_resolved).encode()).hexdigest()[:12]
            cache_name = f"local__{source_path_resolved.name}__{path_hash}"
            cache_path = self.cache_dir / cache_name

            if not cache_path.exists():
                self._log(f"Cloning local repo {source_path_resolved} to cache...")
                if not clone_repo(str(source_path_resolved), cache_path, self.logger.isEnabledFor(logging.DEBUG)):
                    self.logger.error(f"✗ Failed to clone local repo {source_path_resolved}")
                    return None
                integration["local_cache_clone_path"] = str(cache_path)
            else:
                # Fetch from local source (in case they've made changes)
                self._log("Fetching updates from local repo...")
                try:
                    subprocess.run(
                        ["git", "-C", str(cache_path), "fetch", str(source_path_resolved)],
                        capture_output=True,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    print(f"✗ Failed to fetch from local repo {source_path_resolved}")
                    return None
        elif source_url:
            # Extract owner and repo from URL
            # Generate safe cache name using hash of URL to prevent collisions (P0.2)
            url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:8]

            # e.g., https://github.com/owner/repo.git -> owner__repo-abcdef12
            match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(\.git)?$", source_url)
            if match:
                owner = match.group(1)
                repo = match.group(2).replace(".git", "")
                cache_name = f"{owner}__{repo}-{url_hash}"
            else:
                # Fallback for non-GitHub URLs
                repo_name = source_url.split("/")[-1].replace(".git", "")
                cache_name = f"{repo_name}-{url_hash}"

            cache_path = self.cache_dir / cache_name

            if not cache_path.exists():
                self._log(f"Cloning {source_url} to cache...")
                if not clone_repo(source_url, cache_path, self.logger.isEnabledFor(logging.DEBUG)):
                    self.logger.error(f"✗ Failed to clone {source_url}")
                    return None
                integration["local_cache_clone_path"] = str(cache_path)
            else:
                self._log(f"Fetching updates for {cache_name}...")
                if not fetch_repo(cache_path, self.logger.isEnabledFor(logging.DEBUG)):
                    self.logger.error(f"✗ Failed to fetch updates for {cache_name}")
                    return None
        else:
            self._log(f"Skipping {int_id}: no source URL or path")
            return None

        # Touch cache to mark as recently used
        self.cache_manager.touch(cache_name)

        # Get current and remote commits
        current_commit = get_current_commit(cache_path)

        # Determine remote commit
        import_ref = integration.get("import_ref")
        if source_path and not source_url:
            # Local repo - get HEAD of the source repo itself
            remote_commit = get_current_commit(Path(source_path).resolve())
        else:
            # Remote repo - get actual remote HEAD
            remote_commit = get_remote_head(cache_path, branch=import_ref)

        if not remote_commit:
            ref_msg = f" ({import_ref})" if import_ref else ""
            self.logger.error(f"✗ Could not determine remote HEAD for {int_id}{ref_msg}")
            return None

        last_import = integration.get("last_import_commit") or current_commit

        if last_import == remote_commit:
            # #13.5: No-Updates Output - provide informative status
            artifact_count = len(integration.get("artifact_mappings", []))
            last_check = integration.get("last_check_time")
            last_import_time = integration.get("last_import_time")

            # Build informative message
            status_parts = [f"✓ {int_id}: Up to date ({remote_commit[:8]})"]
            status_parts.append(f"  {artifact_count} artifact(s) tracked")

            if last_import_time:
                status_parts.append(f"  Last import: {last_import_time}")
            if last_check:
                status_parts.append(f"  Last check: {last_check}")

            # Update last_check_time in registry
            integration["last_check_time"] = datetime.now().isoformat()
            self._save_registry()

            self.logger.info("\n".join(status_parts))
            return None

        # Check for force push (diverged history)
        # If last_import is NOT an ancestor of remote_commit, history was rewritten
        if last_import:
            try:
                subprocess.run(
                    ["git", "-C", str(cache_path), "merge-base", "--is-ancestor", last_import, remote_commit],
                    check=True,
                )
            except subprocess.CalledProcessError:
                self.logger.warning(f"⚠ WARNING: Force-push detected for {int_id}!")
                self.logger.warning(
                    f"  Local import {last_import[:8]} is not reachable from remote {remote_commit[:8]}"
                )
                self.logger.warning("  This indicates upstream history was rewritten.")
                self.logger.warning("  Recommended action: Re-import or proceed with caution.")
                integration["force_push_detected"] = True

        # Get changes
        commits = get_commit_log(cache_path, last_import or current_commit, remote_commit)
        changed_files = get_changed_files(cache_path, last_import or current_commit, remote_commit)

        return {
            "integration_id": int_id,
            "integration": integration,
            "cache_path": cache_path,
            "from_commit": last_import,
            "to_commit": remote_commit,
            "commits": commits,
            "changed_files": changed_files,
            "num_commits": len(commits),
            "num_files_changed": len(changed_files),
        }

    def _normalize_path_for_comparison(self, path_str: str) -> str:
        """
        Normalize a path for reliable comparison across platforms.

        Handles:
        - Resolving to absolute path
        - Case normalization on case-insensitive filesystems
        - Symlink resolution
        """
        try:
            path = Path(path_str).resolve()

            # On case-insensitive filesystems, normalize case
            if not self._is_case_sensitive_fs():
                return str(path).lower()

            return str(path)
        except (OSError, ValueError):
            # Fallback: just normalize separators
            return str(Path(path_str)).replace("\\", "/")

    def _is_case_sensitive_fs(self) -> bool:
        """Detect if filesystem is case-sensitive (cached)."""
        if not hasattr(self, "_case_sensitive"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / "CaSe_TeSt"
                test_file.touch()
                self._case_sensitive = not (Path(tmpdir) / "case_test").exists()
        return self._case_sensitive

    def _detect_destination_conflicts(self) -> Dict[str, List[str]]:
        """
        Detect destination paths owned by multiple integrations.

        Uses normalized paths for reliable comparison across platforms.

        Returns: Dict mapping normalized_dest_path -> list of integration_ids that claim it
        """
        dest_ownership = {}

        for int_id, integration in self.registry["integrations"].items():
            for mapping in integration.get("artifact_mappings", []):
                dest = mapping.get("dest_abspath")
                if dest:
                    # Normalize path for comparison
                    normalized = self._normalize_path_for_comparison(dest)
                    if normalized not in dest_ownership:
                        dest_ownership[normalized] = []
                    dest_ownership[normalized].append(int_id)

        # Filter to only conflicts (multiple owners)
        conflicts = {dest: owners for dest, owners in dest_ownership.items() if len(owners) > 1}

        return conflicts

    def _validate_update_safety(self, update_info: Dict[str, Any]) -> tuple:
        """
        Validate that an update won't conflict with other integrations.

        Returns: (list of conflict messages, is_hard_conflict)

        Hard conflicts BLOCK the update entirely.
        """
        conflicts = []
        int_id = update_info["integration_id"]
        integration = update_info["integration"]

        # Get all destinations this update will touch (normalized)
        update_dests = set()
        mapping_index = {}
        for mapping in integration.get("artifact_mappings", []):
            source_rel = Path(mapping.get("source_relpath", "")).as_posix()
            mapping_index[source_rel] = mapping

        for status, filepath in update_info.get("changed_files", []):
            filepath_posix = Path(filepath).as_posix()
            if filepath_posix in mapping_index:
                normalized = self._normalize_path_for_comparison(mapping_index[filepath_posix]["dest_abspath"])
                update_dests.add(normalized)

        # Check against global ownership
        all_conflicts = self._detect_destination_conflicts()

        for dest in update_dests:
            if dest in all_conflicts:
                other_owners = [o for o in all_conflicts[dest] if o != int_id]
                if other_owners:
                    conflicts.append(
                        f"CONFLICT: {dest} is owned by multiple integrations: {int_id}, {', '.join(other_owners)}"
                    )

        # Cross-integration conflicts are ALWAYS hard conflicts
        is_hard_conflict = len(conflicts) > 0

        return conflicts, is_hard_conflict

    def _get_install_root(self, integration: Dict[str, Any]) -> Path:
        """
        Get the installation root for an integration.

        This is the base path where .claude artifacts are installed:
        - User scope: ~/.claude
        - Project scope: <target_repo>/.claude
        """
        scope = integration.get("target_scope", "user")

        if scope == "user":
            return Path.home() / ".claude"
        else:
            target_repo = integration.get("target_repo_path")
            if target_repo:
                return Path(target_repo) / ".claude"
            return Path.cwd() / ".claude"

    def _validate_destination_path(self, dest_path: Path, integration: Dict[str, Any]) -> Path:
        """
        Validate that a destination path is safe for the integration's scope.

        Treats registry/provenance data as untrusted input and validates:
        - Path is within the allowed install root
        - No path traversal (../)
        - No symlink escapes (default behavior)

        Args:
            dest_path: The destination path to validate
            integration: The integration config containing scope info

        Returns:
            Path: The validated resolved path

        Raises:
            PathSafetyError: If path is unsafe or escapes allowed root
        """
        install_root = self._get_install_root(integration)

        # Ensure install root exists for validation (may not exist yet)
        # We need to validate even if paths don't exist yet
        try:
            return validate_path(dest_path, install_root, allow_symlinks=False)
        except PathSafetyError as e:
            raise PathSafetyError(f"Unsafe destination path in registry: {dest_path} (root: {install_root}): {e}")

    def _compute_dest_from_source_path(self, source_relpath: str, install_root: Path) -> Path:
        """
        Compute destination path from source relative path.

        Example:
            source_relpath = ".claude/agents/new.md"
            install_root = ~/.claude
            result = ~/.claude/agents/new.md

        This correctly handles cross-directory renames.
        """
        # source_relpath is relative to repo root, e.g., ".claude/commands/foo.md"
        source_path = Path(source_relpath)

        # Extract the part after .claude/
        try:
            # Find .claude in the path and get everything after it
            parts = source_path.parts
            claude_idx = parts.index(".claude")
            rel_to_claude = Path(*parts[claude_idx + 1 :])
            return install_root / rel_to_claude
        except (ValueError, IndexError):
            # Fallback: use filename only (shouldn't happen for valid artifacts)
            return install_root / source_path.name

    def _handle_rename(
        self,
        old_path: str,
        new_path: str,
        mapping_index: Dict,
        conflicts: List,
        updates_to_apply: List,
        new_artifacts: List,
        cache_path: Path,
        integration: Dict[str, Any],
        overwrite_with_backup: bool,
    ) -> None:
        """
        Handle a rename operation with conflict detection.

        IMPORTANT: Computes new_dest from new_path's directory structure,
        NOT from old_dest's parent. This correctly handles cross-directory
        renames like commands/x.md → agents/y.md.
        """
        old_path_posix = Path(old_path).as_posix()
        new_path_posix = Path(new_path).as_posix()

        # Check if we own the old path
        if old_path_posix not in mapping_index:
            # We don't track the old path - just report new path
            new_artifacts.append(new_path)
            return

        mapping = mapping_index[old_path_posix]
        old_dest = Path(mapping["dest_abspath"])

        # CRITICAL: Compute new_dest from new_path's full directory structure
        # NOT just old_dest.parent / new_name (which breaks cross-directory renames)
        install_root = self._get_install_root(integration)
        new_dest = self._compute_dest_from_source_path(new_path, install_root)

        # Validate destination path (treat registry as untrusted input)
        try:
            self._validate_destination_path(new_dest, integration)
        except PathSafetyError as e:
            conflicts.append(
                {"file": new_path, "dest": new_dest, "status": "path_unsafe", "reason": f"Unsafe destination path: {e}"}
            )
            return

        # Check if local file was modified
        if old_dest.exists():
            current_hash = hash_file(old_dest)
            expected_hash = mapping.get("last_import_hash")
            if expected_hash and current_hash != expected_hash:
                conflicts.append(
                    {
                        "file": old_path,
                        "dest": old_dest,
                        "new_dest": new_dest,
                        "status": "rename_local_modified",
                        "reason": "Local file was modified since last import",
                    }
                )
                return

        # Check if new destination already exists
        if new_dest.exists():
            # Check if it is the same file (case-only rename)
            is_case_rename_same_file = False
            try:
                if not platform_utils.is_path_case_sensitive(new_dest.parent):
                    # On case-insensitive FS, resolve() usually gives the casing on disk
                    # If they resolve to same path, it's the same file
                    if new_dest.resolve() == old_dest.resolve():
                        is_case_rename_same_file = True
            except OSError:
                pass

            if not is_case_rename_same_file:
                # Check if it's tracked by us (normal conflict check)
                new_dest_str = str(new_dest.resolve())
                new_dest_owned = any(
                    str(Path(m.get("dest_abspath")).resolve()) == new_dest_str for m in mapping_index.values()
                )

                if new_dest_owned:
                    # Another file we track is at the destination
                    conflicts.append(
                        {
                            "file": old_path,
                            "dest": old_dest,
                            "new_dest": new_dest,
                            "status": "rename_dest_tracked",
                            "reason": "Rename destination is another tracked file",
                        }
                    )
                    return
                else:
                    # Untracked file at destination
                    if overwrite_with_backup:
                        updates_to_apply.append(
                            {
                                "file": new_path,
                                "dest": new_dest,
                                "status": "R",
                                "mapping": mapping,
                                "needs_backup": True,
                                "rename_from": old_dest,
                                "backup_untracked": True,
                                "old_source_relpath": old_path_posix,  # For mapping update
                                "new_source_relpath": new_path_posix,  # For mapping update
                            }
                        )
                    else:
                        conflicts.append(
                            {
                                "file": old_path,
                                "dest": old_dest,
                                "new_dest": new_dest,
                                "status": "rename_dest_exists_untracked",
                                "reason": "Rename destination exists (untracked). Use --overwrite-with-backup.",
                            }
                        )
                    return

        # Safe to rename (or case-only rename) - queue the operation
        updates_to_apply.append(
            {
                "file": new_path,
                "dest": new_dest,
                "status": "R",
                "mapping": mapping,
                "needs_backup": False,
                "rename_from": old_dest,
                "old_source_relpath": old_path_posix,  # For mapping update
                "new_source_relpath": new_path_posix,  # For mapping update
            }
        )

    def apply_update(
        self, update_info: Dict[str, Any], overwrite_with_backup: bool = False, force_conflicting: bool = False
    ):
        """Apply an update to an integration."""
        int_id = update_info["integration_id"]
        integration = update_info["integration"]
        cache_path = update_info["cache_path"]

        # Pre-flight safety check - conflicts are HARD STOP by default
        conflicts, is_hard_conflict = self._validate_update_safety(update_info)

        if conflicts:
            self.logger.error("✗ DESTINATION CONFLICTS DETECTED:")
            for conflict in conflicts:
                self.logger.error(f"  - {conflict}")

            if is_hard_conflict and not force_conflicting:
                self.logger.error("\n" + "=" * 60)
                self.logger.error("UPDATE BLOCKED: Cross-integration conflicts detected.")
                self.logger.error("")
                self.logger.error("To resolve:")
                self.logger.error("  1. Remove one integration's claim on the conflicting file(s)")
                self.logger.error("  2. Or use --force-conflicting to proceed (NOT RECOMMENDED)")
                self.logger.error("=" * 60)
                return  # HARD STOP
            elif force_conflicting:
                self.logger.warning("⚠ WARNING: Proceeding despite conflicts (--force-conflicting)")

        self.logger.info(f"{'[DRY-RUN] ' if self.dry_run else ''}Updating {int_id}...")
        self.logger.info(f"  From: {update_info['from_commit'][:8]}")
        self.logger.info(f"  To:   {update_info['to_commit'][:8]}")
        self.logger.info(f"  Commits: {update_info['num_commits']}")
        self.logger.info(f"  Files changed: {update_info['num_files_changed']}")

        # Show commit log
        if update_info["commits"]:
            self.logger.info("  Recent commits:")
            for commit in update_info["commits"][:5]:
                self.logger.info(f"    - {commit['sha'][:8]}: {commit['message']}")

        # Analyze WHY changed (changelog, release notes, etc.)
        change_analysis = self._analyze_changes(cache_path, update_info)
        if change_analysis:
            self.logger.info("  Change Analysis:")
            self.logger.info(f"    Type: {change_analysis['type']}")
            if change_analysis.get("summary"):
                self.logger.info(f"    Summary: {change_analysis['summary']}")

        # Build a mapping of source_relpath -> mapping entry for fast lookup
        mapping_index = {}
        for mapping in integration.get("artifact_mappings", []):
            source_rel = Path(mapping.get("source_relpath", "")).as_posix()
            mapping_index[source_rel] = mapping

        # Categorize changes
        conflicts = []
        updates_to_apply = []
        new_artifacts = []
        deleted_artifacts = []

        # Checkout the new commit to scan for new artifacts
        if not self.dry_run:
            checkout_commit(cache_path, update_info["to_commit"], self.verbose)

        for raw_status, filepath in update_info["changed_files"]:
            filepath_posix = Path(filepath).as_posix()
            base_status, similarity = _classify_git_status(raw_status)

            # Handle different git statuses
            if base_status == "R":  # Renamed
                # Git rename format: "R<similarity>  old_path  new_path" with tab separators
                parts = filepath.split("\t")
                if len(parts) >= 2:
                    self._handle_rename(
                        old_path=parts[0],
                        new_path=parts[1],
                        mapping_index=mapping_index,
                        conflicts=conflicts,
                        updates_to_apply=updates_to_apply,
                        new_artifacts=new_artifacts,
                        cache_path=cache_path,
                        integration=integration,
                        overwrite_with_backup=overwrite_with_backup,
                    )
                continue

            if base_status == "C":  # Copied
                # Git copy: original still exists, new copy created
                # Treat like an addition of the new path
                parts = filepath.split("\t")
                if len(parts) >= 2:
                    new_path = parts[1]
                    if self.auto_import_new:
                        install_root = self._get_install_root(integration)
                        new_dest = self._compute_dest_from_source_path(new_path, install_root)

                        if new_dest.exists():
                            conflicts.append(
                                {
                                    "file": new_path,
                                    "dest": new_dest,
                                    "status": "copy_dest_exists",
                                    "reason": "Copied artifact destination already exists",
                                }
                            )
                        else:
                            updates_to_apply.append(
                                {
                                    "file": new_path,
                                    "dest": new_dest,
                                    "status": "C",
                                    "needs_backup": False,
                                    "is_new": True,
                                    "mapping": {
                                        "source_relpath": new_path,
                                        "dest_abspath": str(new_dest.resolve()),
                                        "type": "auto_imported_copy",
                                    },
                                }
                            )
                    else:
                        new_artifacts.append(new_path)
                continue

            if base_status == "T":  # Type change
                # File type changed (e.g., regular -> symlink)
                # Treat as modification with warning
                if filepath_posix in mapping_index:
                    mapping = mapping_index[filepath_posix]
                    dest_path = Path(mapping["dest_abspath"])

                    # Check what the new type is - need to check cache_path to see what it became
                    # For now, treat it as a modification that needs backup
                    updates_to_apply.append(
                        {
                            "file": filepath,
                            "dest": dest_path,
                            "status": "T",
                            "mapping": mapping,
                            "needs_backup": True,  # Always backup on typechange
                        }
                    )
                continue

            if base_status == "U":  # Unmerged
                self._log(f"Warning: Unmerged file in upstream: {filepath}")
                continue

            if base_status in ("X", "B"):  # Unknown or Broken
                print(f"  ⚠ Skipping unknown/broken git status '{raw_status}' for {filepath}")
                continue

            if base_status == "D":  # Deleted
                if filepath_posix in mapping_index:
                    mapping = mapping_index[filepath_posix]
                    dest_path = Path(mapping["dest_abspath"])

                    # Validate destination path (treat registry as untrusted input)
                    try:
                        self._validate_destination_path(dest_path, integration)
                    except PathSafetyError as e:
                        conflicts.append(
                            {
                                "file": filepath,
                                "dest": dest_path,
                                "status": "path_unsafe",
                                "reason": f"Unsafe path in delete request: {e}",
                            }
                        )
                        continue

                    if dest_path.exists():
                        current_hash = hash_file(dest_path)
                        expected_hash = mapping.get("last_import_hash")
                        is_modified = expected_hash and current_hash != expected_hash

                        should_delete = False
                        needs_backup = False
                        reason = None

                        if self.delete_policy == "skip":
                            reason = "Policy is skip"
                        elif self.delete_policy == "hard":
                            should_delete = True
                        elif self.delete_policy == "soft":
                            should_delete = True
                            needs_backup = True
                        elif self.delete_policy == "ask":
                            # Interactive check (simulated)
                            # In automated mode without input, we must be conservative
                            # If modified, skip. If clean, delete?
                            if is_modified:
                                reason = "Modified locally (ask policy defaulted to keep)"
                            else:
                                should_delete = True  # Auto-delete clean files even in ask mode?
                                # Conservatively, yes, standard behavior for sync is delete if clean.

                        if should_delete:
                            deleted_artifacts.append(
                                {"file": filepath, "dest": dest_path, "mapping": mapping, "needs_backup": needs_backup}
                            )
                        else:
                            conflicts.append(
                                {
                                    "file": filepath,
                                    "dest": dest_path,
                                    "status": "deleted_upstream_kept_local",
                                    "status_display": "kept_local",
                                    "mapping": mapping,
                                    "reason": reason or "Modified locally",
                                }
                            )
                continue

            # Added or Modified (A, M)
            if filepath_posix in mapping_index:
                # Existing artifact that changed
                mapping = mapping_index[filepath_posix]
                dest_path = Path(mapping["dest_abspath"])

                # Validate destination path (treat registry as untrusted input)
                try:
                    self._validate_destination_path(dest_path, integration)
                except PathSafetyError as e:
                    conflicts.append(
                        {
                            "file": filepath,
                            "dest": dest_path,
                            "status": "path_unsafe",
                            "reason": f"Unsafe destination path: {e}",
                        }
                    )
                    continue

                # Check if local file was modified
                if dest_path.exists():
                    current_hash = hash_file(dest_path)
                    expected_hash = mapping.get("last_import_hash")

                    # If no expected hash (old registry), treat as safe to update
                    if expected_hash and current_hash != expected_hash:
                        # Local modification detected
                        if overwrite_with_backup:
                            # Create backup then update
                            updates_to_apply.append(
                                {
                                    "file": filepath,
                                    "dest": dest_path,
                                    "status": raw_status,
                                    "mapping": mapping,
                                    "needs_backup": True,
                                }
                            )
                        else:
                            # Create .diff patch
                            conflicts.append(
                                {"file": filepath, "dest": dest_path, "status": "local_modified", "mapping": mapping}
                            )
                        continue

                # Safe to update
                updates_to_apply.append(
                    {
                        "file": filepath,
                        "dest": dest_path,
                        "status": raw_status,
                        "mapping": mapping,
                        "needs_backup": False,
                    }
                )
            else:
                # New artifact added upstream
                if base_status == "A":
                    if self.auto_import_new:
                        install_root = self._get_install_root(integration)
                        new_dest = self._compute_dest_from_source_path(filepath, install_root)

                        # Validate destination path (treat registry as untrusted input)
                        try:
                            self._validate_destination_path(new_dest, integration)
                        except PathSafetyError as e:
                            conflicts.append(
                                {
                                    "file": filepath,
                                    "dest": new_dest,
                                    "status": "path_unsafe",
                                    "reason": f"Unsafe destination path: {e}",
                                }
                            )
                            continue

                        if new_dest.exists():
                            conflicts.append(
                                {
                                    "file": filepath,
                                    "dest": new_dest,
                                    "status": "new_dest_exists",
                                    "reason": "New artifact destination already exists",
                                }
                            )
                        else:
                            updates_to_apply.append(
                                {
                                    "file": filepath,
                                    "dest": new_dest,
                                    "status": "A",
                                    "needs_backup": False,
                                    "is_new": True,
                                    "mapping": {
                                        "source_relpath": filepath,
                                        "dest_abspath": str(new_dest.resolve()),
                                        "type": "auto_imported",
                                    },
                                }
                            )
                    else:
                        new_artifacts.append(filepath)

        # Report conflicts
        if conflicts:
            print(f"\n  ⚠ Conflicts detected ({len(conflicts)}):")
            for conflict in conflicts:
                reason_str = f" - {conflict['reason']}" if "reason" in conflict else ""

                if conflict.get("status_display") == "kept_local":
                    print(f"    - {conflict['file']} (deleted upstream, kept local{reason_str})")
                elif conflict["status"] == "deleted_upstream_modified_local":  # Legacy check
                    print(f"    - {conflict['file']} (deleted upstream, modified locally - keeping local)")
                elif conflict.get("status") == "rename_dest_tracked":
                    print(f"    - {conflict['file']} -> {conflict['new_dest']} (destination tracked{reason_str})")
                elif conflict.get("status") == "rename_dest_exists_untracked":
                    print(f"    - {conflict['file']} -> {conflict['new_dest']} (destination exists{reason_str})")
                elif conflict.get("status") == "rename_local_modified":
                    print(f"    - {conflict['file']} (renamed upstream, modified locally{reason_str})")
                elif conflict.get("status") in ("new_dest_exists", "copy_dest_exists"):
                    print(f"    - {conflict['file']} (new artifact destination exists{reason_str})")
                elif conflict.get("status") == "path_unsafe":
                    print(f"    - {conflict['file']} (BLOCKED: unsafe path{reason_str})")
                else:
                    print(f"    - {conflict['file']} (locally modified{reason_str})")

                if not self.dry_run and conflict["status"] == "local_modified":
                    # Create .diff patch
                    diff_content = get_file_diff(
                        cache_path, update_info["from_commit"], update_info["to_commit"], conflict["file"]
                    )
                    if diff_content:
                        diff_path = Path(str(conflict["dest"]) + f".diff.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        safe_write_text(diff_path, diff_content)
                        print(f"      Created patch: {diff_path}")

        # Report new artifacts
        if new_artifacts:
            print(f"\n  ℹ New artifacts detected ({len(new_artifacts)}):")
            for artifact in new_artifacts[:10]:  # Limit display
                print(f"    + {artifact}")
            if len(new_artifacts) > 10:
                print(f"    ... and {len(new_artifacts) - 10} more")
            print("  Note: Re-import to include new artifacts")

        # Report deleted artifacts
        if deleted_artifacts:
            print(f"\n  ⚠ Deleted artifacts ({len(deleted_artifacts)}):")
            for item in deleted_artifacts:
                print(f"    - {item['file']}")

        # Apply updates
        if updates_to_apply or (deleted_artifacts and not self.dry_run):
            if updates_to_apply:
                print(f"\n  Updates to apply ({len(updates_to_apply)}):")
                for update in updates_to_apply:
                    backup_note = " (with backup)" if update.get("needs_backup") else ""
                    print(f"    - {update['status']}: {update['file']}{backup_note}")

            if not self.dry_run:
                try:
                    with UpdateTransaction(verbose=self.verbose) as txn:
                        # Checkout the target commit
                        checkout_commit(cache_path, update_info["to_commit"], self.verbose)

                        # Process deletions first
                        if deleted_artifacts:
                            print(f"\n  Processing deletions ({len(deleted_artifacts)}):")
                            for item in deleted_artifacts:
                                dest_file = Path(item["dest"])
                                if dest_file.exists():
                                    if item.get("needs_backup"):
                                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        backup_path = Path(str(dest_file) + f".bak.{timestamp}")
                                        txn.copy_file(dest_file, backup_path)
                                        print(f"    ✓ Backed up: {backup_path}")

                                    txn.delete_file(dest_file)
                                    print(f"    ✓ Deleted: {dest_file}")
                                    # Update in-memory registry
                                    integration["artifact_mappings"].remove(item["mapping"])

                        # Process updates
                        if updates_to_apply:
                            print(f"\n  Applying updates ({len(updates_to_apply)}):")
                            for update in updates_to_apply:
                                src_file = cache_path / update["file"]
                                dest_file = Path(update["dest"])

                                # Handle renames: delete old file
                                if "rename_from" in update:
                                    old_file = Path(update["rename_from"])
                                    if old_file.exists():
                                        txn.delete_file(old_file)
                                        print(f"    ✓ Renamed: {old_file} -> {dest_file}")

                                # Handle user backup
                                if update.get("needs_backup") and dest_file.exists():
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    backup_path = Path(str(dest_file) + f".bak.{timestamp}")
                                    txn.copy_file(dest_file, backup_path)
                                    print(f"    ✓ Backed up: {backup_path}")

                                # Update file
                                txn.copy_file(src_file, dest_file)

                                if "rename_from" not in update:
                                    status = update["status"]
                                    action = (
                                        "Updated"
                                        if status == "M"
                                        else "Created"
                                        if status in ("A", "C")
                                        else "Processed"
                                    )

                                    # Check for mode change
                                    import stat

                                    try:
                                        old_mode = update["mapping"].get("file_mode")
                                        new_mode = src_file.stat().st_mode
                                        mode_msg = ""
                                        if old_mode is not None:
                                            # Check Executable bit changes (User X bit)
                                            old_exec = bool(old_mode & stat.S_IXUSR)
                                            new_exec = bool(new_mode & stat.S_IXUSR)
                                            if old_exec != new_exec:
                                                mode_msg = f" (Exec {'+' if new_exec else '-'})"

                                        # Update mapping with new mode
                                        update["mapping"]["file_mode"] = new_mode
                                    except (OSError, KeyError, AttributeError):
                                        mode_msg = ""

                                    print(f"    ✓ {action}: {dest_file}{mode_msg}")

                                # Update mapping in memory
                                new_hash = hash_file(dest_file)
                                update["mapping"]["last_import_hash"] = new_hash
                                update["mapping"]["last_import_time"] = datetime.now().isoformat()
                                if "rename_from" in update:
                                    update["mapping"]["source_relpath"] = update["file"]
                                    update["mapping"]["dest_abspath"] = str(dest_file.resolve())

                                if update.get("is_new"):
                                    if "artifact_mappings" not in integration:
                                        integration["artifact_mappings"] = []
                                    integration["artifact_mappings"].append(update["mapping"])

                        txn.commit()

                        # Save registry only after commit
                        integration["last_import_commit"] = update_info["to_commit"]
                        integration["last_checked_commit"] = update_info["to_commit"]
                        self.discovery._save_registry()

                        print(f"\n✓ Update completed successfully for {int_id}")

                except TransactionError as e:
                    print(f"\n❌ Transaction Failed: {e}")
                    print("↺ Rolled back all changes.")
                except Exception as e:
                    print(f"\n❌ Unexpected Error: {e}")
                    print("↺ Rolled back all changes.")
                    import traceback

                    if self.verbose:
                        traceback.print_exc()
            else:
                print("\nTo apply, run with --dry-run=false")

    def _analyze_changes(self, cache_path: Path, update_info: Dict[str, Any]) -> Dict[str, str]:
        """Analyze changes to understand WHY they were made."""
        analysis = {"type": "unknown", "summary": None}

        # Check for changelog/release notes changes
        changelog_files = ["CHANGELOG.md", "CHANGELOG", "HISTORY.md", "RELEASES.md", "NEWS.md"]

        for changelog in changelog_files:
            diff = get_file_diff(cache_path, update_info["from_commit"], update_info["to_commit"], changelog)
            if diff:
                # Extract added lines (start with +)
                added_lines = [
                    line[1:].strip() for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++")
                ]

                if added_lines:
                    # Try to extract version/summary from first few lines
                    summary = " ".join(added_lines[:3])[:200]
                    analysis["summary"] = summary

                    # Classify change type from commit messages
                    commit_text = " ".join(c["message"].lower() for c in update_info["commits"])

                    if "break" in commit_text or "breaking" in commit_text:
                        analysis["type"] = "breaking change"
                    elif "feat" in commit_text or "feature" in commit_text or "add" in commit_text:
                        analysis["type"] = "feature"
                    elif "fix" in commit_text or "bug" in commit_text:
                        analysis["type"] = "bugfix"
                    elif "doc" in commit_text:
                        analysis["type"] = "documentation"
                    elif "refactor" in commit_text:
                        analysis["type"] = "refactor"
                    else:
                        analysis["type"] = "update"

                    return analysis

        # No changelog, classify from commit messages
        if update_info["commits"]:
            commit_text = " ".join(c["message"].lower() for c in update_info["commits"])

            if "break" in commit_text:
                analysis["type"] = "breaking change"
            elif "feat" in commit_text or "add" in commit_text:
                analysis["type"] = "feature"
            elif "fix" in commit_text:
                analysis["type"] = "bugfix"
            elif "doc" in commit_text:
                analysis["type"] = "documentation"
            else:
                analysis["type"] = "maintenance"

        return analysis


def main():
    parser = argparse.ArgumentParser(description="Update integrated Claude Code repositories")

    parser.add_argument("--check", action="store_true", help="Check for updates")
    parser.add_argument("--apply", action="store_true", help="Apply updates")
    parser.add_argument("--all", action="store_true", help="Process all integrations")
    parser.add_argument("--id", help="Integration ID to process")
    # Add standardized dry-run argument (--apply action also implies dry_run=False)
    add_dry_run_argument(parser)
    parser.add_argument("--overwrite-with-backup", action="store_true")
    parser.add_argument("--registry", default="~/.claude/mine/registry.json")

    add_logging_arguments(parser)

    parser.add_argument("--auto-import-new", action="store_true", help="Automatically import new artifacts")
    parser.add_argument(
        "--delete-policy",
        choices=["soft", "hard", "ask", "skip"],
        default="ask",
        help="Policy for handling deleted upstream artifacts (default: ask)",
    )

    args = parser.parse_args()

    # Resolve dry-run state: --apply action also implies dry_run=False
    effective_dry_run = resolve_dry_run(args) and not args.apply

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    registry_path = Path(args.registry).expanduser()
    updater = IntegrationUpdater(
        registry_path,
        effective_dry_run,
        auto_import_new=args.auto_import_new,
        delete_policy=args.delete_policy,
    )

    if args.check:
        int_id = args.id if not args.all else None
        updates = updater.check_updates(int_id)

        if not updates:
            logger.info("All integrations are up to date.")
        else:
            logger.info(f"Updates available for {len(updates)} integration(s):")
            for update in updates:
                logger.info(f"  - {update['integration_id']}: {update['num_commits']} commits")

    elif args.apply:
        int_id = args.id if not args.all else None
        updates = updater.check_updates(int_id)

        for update in updates:
            updater.apply_update(update, args.overwrite_with_backup)

    else:
        parser.print_help()

    # Enforce cache limits after operations
    enforce_limits(updater.cache_dir, verbose=logger.isEnabledFor(logging.DEBUG))

    return 0


if __name__ == "__main__":
    sys.exit(main())
