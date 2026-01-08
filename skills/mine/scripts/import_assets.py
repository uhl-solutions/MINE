#!/usr/bin/env python3
"""
import_assets.py - Import or generate Claude Code artifacts from repositories

Imports existing Claude artifacts or generates new skill packs based on
repository workflows and conventions.
"""

import argparse
import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import shared modules
from scan_repo import RepoScanner

import platform_utils
from hash_helpers import hash_file
from path_safety import PathSafetyError, validate_path

import _init_shared
from safe_io import safe_write_json
from cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run
from logging_utils import setup_logging, get_logger, add_logging_arguments
from skill_creator_bridge import (
    is_skill_creator_available,
    should_handoff,
    generate_handoff_context,
    format_handoff_message,
    get_skill_creator_instructions,
    DEFAULT_HANDOFF_THRESHOLD,
)

# Add update skill script dir for Registry access
UPDATE_SKILLS_DIR = Path(__file__).parent.parent.parent / "mine-mine" / "scripts"
if UPDATE_SKILLS_DIR.exists():
    sys.path.insert(0, str(UPDATE_SKILLS_DIR))
    try:
        from discover_integrations import IntegrationDiscovery
    except ImportError:
        IntegrationDiscovery = None
else:
    IntegrationDiscovery = None

# Import P5 Agentic Modules
try:
    from agentic_classifier import classify_candidates
    from agentic_converter import AgenticConverter
    from agentic_discovery import AgenticDiscoverer
    from agentic_provenance import write_agentic_provenance
except ImportError:
    AgenticDiscoverer = None
    classify_candidates = None
    AgenticConverter = None
    write_agentic_provenance = None


class AssetImporter:
    """Imports Claude artifacts from scanned repositories."""

    def __init__(
        self,
        source: str,
        scope: str,
        mode: str = "import",
        dry_run: bool = True,
        target_repo: Optional[str] = None,
        overwrite_with_backup: bool = False,
        ref: Optional[str] = None,
        discover_agentic: bool = False,
        min_confidence: float = 0.65,
        verbose: bool = False,
        use_skill_creator: bool = False,
        no_skill_creator: bool = False,
    ):
        self.source = source
        self.scope = scope
        self.mode = mode
        self.dry_run = dry_run
        self.target_repo = target_repo
        self.overwrite_with_backup = overwrite_with_backup
        self.ref = ref
        self.discover_agentic = discover_agentic
        self.min_confidence = min_confidence
        # verbose is deprecated, handled via logging, but kept for compatibility
        self.verbose = verbose
        self.logger = get_logger(__name__)
        # Skill-creator integration (Option B + Option C)
        self.use_skill_creator = use_skill_creator
        self.no_skill_creator = no_skill_creator

        # Determine base directories
        if scope == "user":
            self.base_dir = Path.home() / ".claude"
        elif scope == "project":
            if not target_repo:
                target_repo = os.getcwd()
            self.base_dir = Path(target_repo) / ".claude"
        else:
            raise ValueError(f"Invalid scope: {scope}")

        self.operations: List[Dict[str, Any]] = []
        self.conflicts: List[str] = []
        self.dest_tracker: Dict[str, str] = {}  # Track destination -> source mapping for collision detection
        self.repo_id = None
        self.artifact_mappings: List[Dict[str, Any]] = []  # Track imported artifacts
        self.source_commit: Optional[str] = None  # Track source commit SHA

        # Initialize discovery for registry checks
        self.discovery = None
        if IntegrationDiscovery:
            registry_path = Path.home() / ".claude" / "mine" / "registry.json"
            self.discovery = IntegrationDiscovery(
                registry_path=registry_path, verbose=self.logger.isEnabledFor(logging.DEBUG)
            )

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        self.logger.debug(message)

    def _print_operation(self, op_type: str, path: str, note: str = ""):
        """Print an operation in a formatted way."""
        note_str = f" ({note})" if note else ""
        self.logger.info(f"[{op_type}] {path}{note_str}")

    def import_assets(self) -> int:
        """Main import workflow."""
        self.logger.info("=" * 70)
        if self.dry_run:
            self.logger.info("=== DRY-RUN MODE ===")
            self.logger.info("No files will be modified. Use --dry-run=false to execute.")
        else:
            self.logger.info("=== IMPORT MODE ===")
            self.logger.info("Files will be written to disk.")
        self.logger.info("=" * 70)
        self.logger.info("")

        # Scan repository
        self.logger.info("Scanning repository...")
        scanner = RepoScanner(self.source, ref=self.ref)
        report = scanner.scan()
        self.repo_id = report["repo_id"]

        # Check if already integrated (Re-import detection)
        if self.discovery and self.mode == "import":
            registrations = self.discovery._load_registry().get("integrations", {})
            # Look for matching repo_id or source URL
            existing_id = None
            for int_id, data in registrations.items():
                if data.get("repo_id") == self.repo_id or data.get("source_url") == self.source:
                    existing_id = int_id
                    break

            if existing_id:
                self.logger.info(f"ℹ Repository already integrated as: {existing_id}")
                self.logger.info("  Suggestion: Use 'mine-mine --check' to see updates.")
                self.logger.info("  Continuing with re-import as requested (artifacts will be refreshed).")
                self.logger.info("")

        self.logger.info(f"Repository: {self.repo_id}")
        if self.ref:
            self.logger.info(f"Reference: {self.ref}")
        self.logger.info(f"Source: {report['source']}")
        self.logger.info(f"Artifacts found: {len(report['detected_artifacts'])}")
        if report.get("framework_type"):
            self.logger.info(f"Framework detected: {report['framework_type']}")
        self.logger.info("")

        # Check for auto mode selection
        if self.mode == "auto":
            if "convert" in report["suggested_actions"]:
                self.mode = "convert"
            elif "import" in report["suggested_actions"]:
                self.mode = "import"
            else:
                self.mode = "generate"
            self.logger.info(f"Auto-selected mode: {self.mode}")
            self.logger.info("")

        # Check mode
        if self.mode == "import":
            if not report["detected_artifacts"] or all(
                a["type"] in ["documentation", "build_file", "plugin"] for a in report["detected_artifacts"]
            ):
                self.logger.warning("⚠ No importable Claude artifacts found.")
                if report.get("framework_type"):
                    self.logger.info(
                        f"Suggested action: Use --mode convert to convert {report['framework_type']} patterns"
                    )
                else:
                    self.logger.info("Suggested action: Use --mode generate to create a skill pack")
                return 1

            return self._import_mode(report)

        elif self.mode == "convert":
            if not report.get("framework_type"):
                self.logger.error("Error: No framework detected for conversion")
                self.logger.error("This repository does not appear to be a known AI framework")
                return 1

            return self._convert_mode(report)

        elif self.mode == "generate":
            return self._generate_mode(report)

        else:
            self.logger.error(f"Error: Invalid mode: {self.mode}")
            return 2

    def _import_mode(self, report: Dict[str, Any]) -> int:
        """Import existing Claude artifacts."""
        # Check for overlapping integrations (Overlap Protection)
        if self.discovery:
            overlap_conflicts = self._validate_no_overlap(report)
            if overlap_conflicts:
                self.logger.error("❌ Overlap Conflict Detected:")
                for conflict in overlap_conflicts:
                    self.logger.error(f"  - {conflict}")
                self.logger.error("\nError: Destination paths are already owned by other integrations.")
                self.logger.error("Use a different --target-repo or uninstall conflicting integrations.")
                return 4

        self.logger.info("PLANNED OPERATIONS:")
        self.logger.info("")

        # Get source repository path
        scanner = RepoScanner(self.source, ref=self.ref)
        try:
            repo_path = scanner._clone_repo()
        except Exception as e:
            self.logger.error(f"Error: Failed to access repository: {e}")
            return 3

        try:
            # Process each artifact
            for artifact in report["detected_artifacts"]:
                self._process_artifact(artifact, repo_path)

            # Print summary
            self.logger.info("")
            if self.conflicts:
                self.logger.warning("CONFLICTS:")
                for conflict in self.conflicts:
                    self.logger.warning(f"- {conflict}")
                self.logger.info("")

            if report["risks"]:
                self.logger.warning("RISKS:")
                for risk in report["risks"]:
                    self.logger.warning(f"- {risk['path']} ({risk['severity']}: {risk['reason']})")
                self.logger.info("")

            # Execute operations if not dry-run
            if not self.dry_run:
                self.logger.info("Executing operations...")
                for op in self.operations:
                    self._execute_operation(op)
                self.logger.info("")
                self.logger.info("✓ Import complete")

                # Write provenance file for future updates
                self._write_provenance(repo_path)

                # Print post-import instructions
                self._print_merge_instructions(report)
            else:
                self.logger.info("To execute, run with: --dry-run=false")

            # Run Agentic Pipeline if requested (P5)
            if self.discover_agentic and AgenticDiscoverer:
                self._run_agentic_pipeline(repo_path)
            elif self.discover_agentic:
                self.logger.warning("Warning: Agentic modules not found, skipping agentic discovery.")

            return 0

        finally:
            # Cleanup
            if scanner.temp_dir and os.path.exists(scanner.temp_dir):
                shutil.rmtree(scanner.temp_dir)

    def _process_artifact(self, artifact: Dict[str, Any], repo_path: Path):
        """Process a single artifact for import."""
        artifact_type = artifact["type"]
        source_path = repo_path / artifact["source_path"]

        # Skip artifacts that aren't actually imported
        if artifact_type in ["documentation", "build_file", "plugin"]:
            return

        # Determine destination
        dest_suggestions = artifact["destination_suggestions"]
        if self.scope not in dest_suggestions:
            self._log(f"Skipping {artifact['source_path']}: not available for {self.scope} scope")
            return

        dest_rel = dest_suggestions[self.scope]

        # Expand user home if needed
        if dest_rel.startswith("~/"):
            dest_path = Path.home() / dest_rel[2:]
        else:
            dest_path = self.base_dir.parent / dest_rel if dest_rel.startswith(".") else Path(dest_rel)

        # Validate path safety
        try:
            # For user scope, ensure within .claude
            # For project scope, ensure within project root (base_dir.parent)
            root = Path.home() / ".claude" if self.scope == "user" else self.base_dir.parent
            dest_path = validate_path(
                dest_path, root, error_msg=f"Destination path '{dest_path}' is outside allowed scope root"
            )
        except PathSafetyError as e:
            self._log(f"Skipping {artifact['source_path']}: {e}")
            return

        # Check for skills (copy entire directory)
        if artifact_type == "skill":
            source_dir = source_path.parent
            # Pass the artifact source_path (includes .claude/) for proper tracking
            self._plan_directory_copy(source_dir, dest_path, artifact_type, artifact["source_path"])
        else:
            # Copy single file - pass artifact source_path
            self._plan_file_copy(source_path, dest_path, artifact_type, artifact["source_path"])

    def _plan_file_copy(self, source: Path, dest: Path, artifact_type: str, source_relpath: str):
        """Plan a file copy operation."""
        # Check for collision with other artifacts in this batch
        dest_str = str(dest.resolve())
        if dest_str in self.dest_tracker:
            prev_source = self.dest_tracker[dest_str]
            self._log(f"Collision detected: {source_relpath} and {prev_source} both map to {dest}")
            self.conflicts.append(f"{source_relpath} -> {dest} (COLLISION with {prev_source})")
            return

        self.dest_tracker[dest_str] = source_relpath
        will_import = False  # Track whether this artifact will actually be imported

        if dest.exists():
            if self.overwrite_with_backup:
                backup_path = self._get_backup_path(dest)
                self.operations.append({"type": "backup", "source": dest, "dest": backup_path})
                self.operations.append({"type": "copy", "source": source, "dest": dest, "artifact_type": artifact_type})
                self._print_operation("BACKUP", f"{dest} → {backup_path}")
                self._print_operation("CREATE", str(dest))
                will_import = True  # Will be imported (with backup)
            else:
                self.conflicts.append(str(dest))
                self._print_operation("SKIP", str(dest), "exists")
                will_import = False  # Skipped - don't track
        else:
            self.operations.append({"type": "copy", "source": source, "dest": dest, "artifact_type": artifact_type})
            self._print_operation("CREATE", str(dest))
            will_import = True  # Will be imported (new file)

        # Track artifact mapping ONLY if actually imported
        if will_import:
            self.artifact_mappings.append(
                {"type": artifact_type, "source_relpath": source_relpath, "dest_abspath": str(dest.resolve())}
            )

    def _plan_directory_copy(self, source: Path, dest: Path, artifact_type: str, source_relpath: str):
        """Plan a directory copy operation."""
        will_import = False  # Track whether this artifact will actually be imported

        if dest.exists():
            if self.overwrite_with_backup:
                backup_path = self._get_backup_path(dest)
                self.operations.append({"type": "backup_dir", "source": dest, "dest": backup_path})
                self.operations.append(
                    {"type": "copy_dir", "source": source, "dest": dest, "artifact_type": artifact_type}
                )
                self._print_operation("BACKUP", f"{dest}/ → {backup_path}/")
                self._print_operation("CREATE", f"{dest}/")
                will_import = True  # Will be imported (with backup)
            else:
                self.conflicts.append(str(dest))
                self._print_operation("SKIP", f"{dest}/", "exists")
                will_import = False  # Skipped - don't track
        else:
            self.operations.append({"type": "copy_dir", "source": source, "dest": dest, "artifact_type": artifact_type})
            self._print_operation("CREATE", f"{dest}/")
            will_import = True  # Will be imported (new directory)

        # Track artifact mappings ONLY if actually imported
        if will_import:
            # Track artifact mappings for ALL directories at file level
            # This enables granular update tracking for each file
            if source.exists():
                # Get the skill directory path from source_relpath
                # e.g., ".claude/skills/my-skill/SKILL.md" -> ".claude/skills/my-skill"
                # For basic directories, source_relpath covers the dir

                # If source_relpath ends with the directory name, use it directly
                # If it points to a file inside (like SKILL.md), get parent
                src_rel_path = Path(source_relpath)
                if src_rel_path.name == source.name:
                    base_relpath = str(src_rel_path)
                else:
                    base_relpath = str(src_rel_path.parent)

                # Create mappings for all files in the directory
                for file_path in source.rglob("*"):
                    if file_path.is_file():
                        # Calculate relative path within repo
                        try:
                            file_relpath_in_dir = file_path.relative_to(source)
                            full_source_relpath = str(Path(base_relpath) / file_relpath_in_dir)
                        except ValueError:
                            continue

                        # Calculate destination
                        dest_file = dest / file_relpath_in_dir

                        self.artifact_mappings.append(
                            {
                                "type": artifact_type,
                                "source_relpath": full_source_relpath,
                                "dest_abspath": str(dest_file.resolve()),
                                "is_directory": False,
                            }
                        )
            else:
                # Should not happen if source exists check passed
                pass

    def _get_backup_path(self, path: Path) -> Path:
        """Generate backup path with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return path.parent / f"{path.name}.bak.{timestamp}"

    def _execute_operation(self, op: Dict[str, Any]):
        """Execute a planned operation."""
        op_type = op["type"]

        if op_type == "copy":
            dest = op["dest"]
            # Check for symlink at source
            if os.path.islink(op["source"]):
                print(f"⚠ Skipping symlink: {op['source']}")
                return

            os.makedirs(platform_utils.get_long_path(dest.parent), exist_ok=True)

            # Check for case mismatch on case-insensitive filesystems
            if dest.exists() and not platform_utils.is_path_case_sensitive(dest):
                try:
                    real_path = dest.resolve()
                    if real_path.name != dest.name and real_path.name.lower() == dest.name.lower():
                        # Case mismatch detected (e.g. disk has 'Foo', we want 'foo')
                        # Rename to temp then to target to fix case
                        print(f"  Fixing case: {real_path.name} -> {dest.name}")
                        temp_dest = dest.with_name(f".tmp_{dest.name}_{os.getpid()}")
                        # Rename existing to temp
                        real_path.rename(platform_utils.get_long_path(temp_dest))
                        # Copy new file to dest (creating it with correct case)
                        shutil.copy2(platform_utils.get_long_path(op["source"]), platform_utils.get_long_path(dest))
                        # Remove temp (which was the old file)
                        # Actually we are overwriting, so we don't need the old file unless backup
                        # If we are here, backup was already handled if requested (via separate op)
                        if temp_dest.exists():
                            if temp_dest.is_dir():
                                shutil.rmtree(platform_utils.get_long_path(temp_dest))
                            else:
                                temp_dest.unlink()
                        print(f"✓ Wrote: {dest}")
                        return
                except OSError:
                    pass

            shutil.copy2(platform_utils.get_long_path(op["source"]), platform_utils.get_long_path(dest))
            print(f"✓ Wrote: {dest}")

        elif op_type == "copy_dir":
            dest = op["dest"]
            if dest.exists():
                shutil.rmtree(dest)

            # Helper to ignore symlinks during copytree
            def ignore_symlinks(dir, files):
                return [f for f in files if os.path.islink(os.path.join(dir, f))]

            shutil.copytree(
                platform_utils.get_long_path(op["source"]), platform_utils.get_long_path(dest), ignore=ignore_symlinks
            )
            print(f"✓ Wrote: {dest}/")

        elif op_type == "backup":
            shutil.copy2(platform_utils.get_long_path(op["source"]), platform_utils.get_long_path(op["dest"]))
            print(f"✓ Backup: {op['dest']}")

        elif op_type == "backup_dir":
            shutil.copytree(platform_utils.get_long_path(op["source"]), platform_utils.get_long_path(op["dest"]))
            print(f"✓ Backup: {op['dest']}/")

    def _print_merge_instructions(self, report: Dict[str, Any]):
        """Print instructions for manual merge operations."""
        has_hooks = any(a["type"] in ["hook", "hook_config"] for a in report["detected_artifacts"])
        has_mcp = any(a["type"] == "mcp_config" for a in report["detected_artifacts"])
        has_claude_md = any(a["type"] == "claude_md" for a in report["detected_artifacts"])

        if not (has_hooks or has_mcp or has_claude_md):
            return

        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("MANUAL MERGE REQUIRED")
        self.logger.info("=" * 70)

        if has_hooks:
            repo_safe = self.repo_id.replace("/", "-")
            self.logger.info("")
            self.logger.info("Hooks imported to review location:")
            self.logger.info(f"  .claude/hooks.imported.{repo_safe}/")
            self.logger.info("")
            self.logger.info("To enable hooks (after review):")
            self.logger.info(f"  1. Review: ls -la .claude/hooks.imported.{repo_safe}/")
            self.logger.info(f"  2. Enable: cp .claude/hooks.imported.{repo_safe}/* .claude/hooks/")
            self.logger.info("  3. Make executable: chmod +x .claude/hooks/*")

        if has_mcp:
            repo_safe = self.repo_id.replace("/", "-")
            self.logger.info("")
            self.logger.info("MCP configuration imported to:")
            self.logger.info(f"  .mcp.imported.{repo_safe}.json")
            self.logger.info("")
            self.logger.info("To merge with existing MCP config:")
            self.logger.info(f"  1. Review: cat .mcp.imported.{repo_safe}.json")
            self.logger.info("  2. Manually merge server configs into .mcp.json")
            self.logger.info(f"  3. Delete: rm .mcp.imported.{repo_safe}.json")

        if has_claude_md:
            repo_safe = self.repo_id.replace("/", "-")
            self.logger.info("")
            self.logger.info("CLAUDE.md imported to:")
            self.logger.info(f"  .claude/CLAUDE.imported.{repo_safe}.md")
            self.logger.info("")
            self.logger.info("To merge with existing CLAUDE.md:")
            self.logger.info(f"  1. Review: cat .claude/CLAUDE.imported.{repo_safe}.md")
            self.logger.info("  2. Append relevant sections to CLAUDE.md")
            self.logger.info(f"  3. Delete: rm .claude/CLAUDE.imported.{repo_safe}.md")

        self.logger.info("")

    def _write_provenance(self, repo_path: Path):
        """Write provenance file to track this import for future updates.

        Note: URLs are sanitized before storage to prevent credential persistence.
        """
        # Import URL sanitization utility
        # Import URL sanitization utility
        try:
            from url_utils import sanitize_json_urls
        except ImportError:
            # Should be provided by _init_shared
            sanitize_json_urls = lambda x: x

        # Get commit SHA from source repo
        try:
            if repo_path.exists() and (repo_path / ".git").exists():
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
                )
                self.source_commit = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.source_commit = None

        # Compute hashes for all imported files
        for mapping in self.artifact_mappings:
            dest_path = Path(mapping["dest_abspath"])

            if mapping.get("is_directory"):
                # For directories, hash the main files
                if dest_path.exists():
                    # Hash SKILL.md or main file
                    skill_file = dest_path / "SKILL.md"
                    if skill_file.exists():
                        mapping["last_import_hash"] = hash_file(skill_file)
            else:
                # For files, hash the file
                if dest_path.exists():
                    mapping["last_import_hash"] = hash_file(dest_path)

            mapping["last_import_time"] = datetime.now().isoformat()

        # Create provenance data
        provenance = {
            "version": "1.0",
            "repo_id": self.repo_id,
            "source_url": self.source if self.source.startswith("http") else None,
            "source_path": self.source if not self.source.startswith("http") else None,
            "import_commit": self.source_commit,
            "import_ref": self.ref,
            "import_time": datetime.now().isoformat(),
            "import_scope": self.scope,
            "artifact_mappings": self.artifact_mappings,
        }

        # Sanitize URL credentials before writing to disk
        provenance = sanitize_json_urls(provenance)

        # Determine provenance file location
        if self.scope == "user":
            provenance_dir = Path.home() / ".claude" / "mine" / ".provenance"
        else:
            provenance_dir = self.base_dir / ".provenance"

        provenance_dir.mkdir(parents=True, exist_ok=True)

        # Safe filename from repo_id
        safe_repo_id = self.repo_id.replace("/", "-").replace("\\", "-")
        provenance_file = provenance_dir / f"{safe_repo_id}.json"

        # Write provenance file atomically (crash-safe)
        if not safe_write_json(provenance_file, provenance):
            self._log(f"Warning: Failed to write provenance file atomically: {provenance_file}")

        self._log(f"Wrote provenance file: {provenance_file}")

        # Auto-register with mine-mine if available
        self._auto_register_integration(provenance_file)

    def _validate_no_overlap(self, report: Dict[str, Any]) -> List[str]:
        """Check if destination paths overlap with existing integrations."""
        if not self.discovery:
            return []

        registrations = self.discovery._load_registry().get("integrations", {})
        conflicts = []

        # Collect all destination paths already in registry (excluding the one being re-imported)
        existing_destinations = {}  # dest_abspath -> integration_id
        for int_id, data in registrations.items():
            # If re-importing same repo, don't conflict with itself
            if data.get("repo_id") == self.repo_id or data.get("source_url") == self.source:
                continue

            for mapping in data.get("artifact_mappings", []):
                dest = mapping.get("dest_abspath")
                if dest:
                    existing_destinations[str(Path(dest).resolve())] = int_id

        # Check planned destinations
        for artifact in report["detected_artifacts"]:
            if artifact["type"] in ["documentation", "build_file", "plugin"]:
                continue

            dest_suggestions = artifact.get("destination_suggestions", {})
            if self.scope not in dest_suggestions:
                continue

            dest_rel = dest_suggestions[self.scope]
            if dest_rel.startswith("~/"):
                dest_path = Path.home() / dest_rel[2:]
            else:
                dest_path = self.base_dir.parent / dest_rel if dest_rel.startswith(".") else Path(dest_rel)

            dest_abs = str(dest_path.resolve())

            # Direct match
            if dest_abs in existing_destinations:
                conflicts.append(f"{dest_abs} is already owned by {existing_destinations[dest_abs]}")

            # Parent/Child check (one integration owning a directory where another wants a file)
            for existing_dest, owner in existing_destinations.items():
                if dest_abs.startswith(existing_dest + os.sep) or existing_dest.startswith(dest_abs + os.sep):
                    conflicts.append(f"{dest_abs} overlaps with {existing_dest} (owned by {owner})")

        return list(set(conflicts))

    def _auto_register_integration(self, provenance_file: Path):
        """Attempt to auto-register this integration with mine-mine."""
        # Check if mine-mine is installed
        update_skill_path = Path.home() / ".claude" / "skills" / "mine-mine"
        discover_script = update_skill_path / "scripts" / "discover_integrations.py"

        if not discover_script.exists():
            self._log("mine-mine not found, skipping auto-registration")
            return

        # Call discover to auto-add this integration
        try:
            subprocess.run(
                [sys.executable, str(discover_script), "--discover", "--no-confirm"], capture_output=True, timeout=10
            )
            self._log("Auto-registered integration with mine-mine")
        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            self._log("Auto-registration failed (non-critical)")

    def _convert_mode(self, report: Dict[str, Any]) -> int:
        """Convert framework artifacts to Claude Code format."""
        framework = report["framework_type"]
        print(f"CONVERT MODE: Converting {framework} framework to Claude Code")
        print()

        # Import converter module
        try:
            from convert_framework import FrameworkConverter
        except ImportError:
            print("Error: convert_framework.py not found", file=sys.stderr)
            return 1

        # Get source repository path
        scanner = RepoScanner(self.source, verbose=False)
        try:
            repo_path = scanner._clone_repo()
        except Exception as e:
            print(f"Error: Failed to access repository: {e}", file=sys.stderr)
            return 3

        try:
            # Determine output directory
            if self.scope == "user":
                output_dir = Path.home() / ".claude"
            else:
                output_dir = self.base_dir

            # Validate output dir
            root = Path.home() / ".claude" if self.scope == "user" else self.base_dir.parent
            output_dir = validate_path(output_dir, root)

            # Convert framework artifacts
            converter = FrameworkConverter(
                framework_type=framework,
                source_path=repo_path,
                output_dir=output_dir,
                dry_run=self.dry_run,
                verbose=self.verbose,
            )

            result = converter.convert()

            if result == 0 and not self.dry_run:
                print()
                print("=" * 70)
                print("CONVERSION COMPLETE")
                print("=" * 70)
                print()
                print(f"Converted {framework} patterns to Claude Code artifacts:")
                print(f"  Agents: {output_dir}/agents/")
                print(f"  Commands: {output_dir}/commands/")
                print(f"  Skills: {output_dir}/skills/")
                print()
                print("Restart Claude Code to load the converted artifacts.")

            return result

        finally:
            # Cleanup
            if scanner.temp_dir and os.path.exists(scanner.temp_dir):
                shutil.rmtree(scanner.temp_dir)

    def _generate_mode(self, report: Dict[str, Any]) -> int:
        """Generate new skill pack from repository."""
        print("GENERATE MODE: Creating skill pack from repository workflows")
        print()

        # Import generate_skillpack module
        try:
            from generate_skillpack import SkillpackGenerator
        except ImportError:
            print("Error: generate_skillpack.py not found", file=sys.stderr)
            return 1

        # Determine target directory
        skill_name = f"{self.repo_id.split('/')[-1]}-workflow"
        if self.scope == "user":
            target_dir = Path.home() / ".claude" / "skills" / skill_name
        else:
            target_dir = self.base_dir / "skills" / skill_name

        # Validate target dir
        root = Path.home() / ".claude" if self.scope == "user" else self.base_dir.parent
        validate_path(target_dir, root)

        # Check if skill-creator handoff is appropriate (Option B + Option C)
        # Calculate a confidence score based on what we detected
        confidence_score = self._calculate_generation_confidence(report)

        do_handoff, handoff_reason = should_handoff(
            confidence_score=confidence_score,
            force_handoff=self.use_skill_creator,
            disable_handoff=self.no_skill_creator,
            threshold=DEFAULT_HANDOFF_THRESHOLD,
        )

        if do_handoff:
            return self._handoff_to_skill_creator(report, target_dir, confidence_score, handoff_reason)

        # Standard template-based generation (fallback or user disabled skill-creator)
        if not self.no_skill_creator and confidence_score < DEFAULT_HANDOFF_THRESHOLD:
            print(f"ℹ Low confidence ({confidence_score:.1%}) but skill-creator not available.")
            print("  Tip: Install skill-creator for higher-quality skill generation.")
            print()

        # Generate skill pack
        generator = SkillpackGenerator(
            self.source,
            str(target_dir),
            repo_name=self.repo_id.split("/")[-1],
            dry_run=self.dry_run,
            verbose=self.verbose,
        )

        return generator.generate()

    def _calculate_generation_confidence(self, report: Dict[str, Any]) -> float:
        """Calculate confidence score for template-based generation.

        Higher scores indicate better fit for templates; lower scores suggest
        that skill-creator would produce better results.
        """
        score = 0.5  # Base score

        # Boost for known patterns
        if report.get("framework_type"):
            score += 0.3  # Known framework = high confidence

        artifacts = report.get("detected_artifacts", [])

        # Boost for existing Claude artifacts
        claude_artifacts = [a for a in artifacts if a.get("type") in ["skill", "command", "agent"]]
        if claude_artifacts:
            score += 0.2

        # Boost for build files (structured project)
        build_files = [a for a in artifacts if a.get("type") == "build_file"]
        if build_files:
            score += 0.1

        # Reduce for complex/unknown structures
        if not artifacts:
            score -= 0.2  # No artifacts = harder to template

        return max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]

    def _handoff_to_skill_creator(
        self, report: Dict[str, Any], target_dir: Path, confidence_score: float, reason: str
    ) -> int:
        """Hand off skill creation to Anthropic's skill-creator skill."""
        # Build analysis context
        analysis = {
            "detected_patterns": [a.get("type") for a in report.get("detected_artifacts", [])],
            "language": report.get("language", "unknown"),
            "frameworks": [report.get("framework_type")] if report.get("framework_type") else [],
            "confidence_score": confidence_score,
            "reason_for_handoff": reason,
            "artifact_types": list(set(a.get("type") for a in report.get("detected_artifacts", []))),
        }

        # Generate handoff context
        context = generate_handoff_context(
            source=self.source,
            source_type="workflow_generation",
            scope=self.scope,
            target_dir=str(target_dir),
            analysis=analysis,
            dry_run=self.dry_run,
        )

        # Display handoff message
        message = format_handoff_message(context, verbose=self.verbose)
        print(message)

        # Generate instructions for the user
        description = report.get("description", f"workflow automation for {self.repo_id}")
        instructions = get_skill_creator_instructions(
            source=self.source,
            description=description,
            target_scope=self.scope,
        )
        print(instructions)

        # Return success - handoff complete (user will use skill-creator)
        return 0

    def _run_agentic_pipeline(self, repo_path: Path):
        """Run the Agentic Discovery & Conversion pipeline."""
        print()
        print("=" * 70)
        print("AGENTIC DISCOVERY & CONVERSION")
        print("=" * 70)
        print()

        try:
            # 1. Discovery
            print("Discovering agentic candidates...")
            discoverer = AgenticDiscoverer(repo_path, verbose=self.verbose)
            candidates = discoverer.discover()
            print(f"Found {len(candidates)} candidates.")

            if not candidates:
                return

            # 2. Classification
            print("Classifying candidates...")
            classified = classify_candidates(candidates, verbose=self.verbose)

            # Filter by confidence
            high_confidence = [c for c in classified if c["confidence"] >= self.min_confidence]
            print(
                f"Classified {len(classified)} items. {len(high_confidence)} met confidence threshold ({self.min_confidence})."
            )

            if not high_confidence:
                return

            # 3. Conversion
            print(f"Converting {len(high_confidence)} items...")

            # Determine output directory
            if self.scope == "user":
                output_dir = Path.home() / ".claude"
            else:
                output_dir = self.base_dir

            converter = AgenticConverter(
                output_dir=output_dir, repo_name=self.repo_id.split("/")[-1], verbose=self.verbose, dry_run=self.dry_run
            )

            # Convert all high-confidence items
            conversions = []
            for item in high_confidence:
                result = converter.convert(item, threshold=self.min_confidence)
                if result:
                    conversions.append(result)

            # 4. Provenance
            if conversions and not self.dry_run and write_agentic_provenance:
                # Determine provenance directory
                if self.scope == "user":
                    provenance_dir = Path.home() / ".claude" / "mine" / ".provenance"
                else:
                    provenance_dir = output_dir / ".provenance"

                provenance_path = write_agentic_provenance(
                    conversions=conversions,
                    repo_id=self.repo_id,
                    source_url=self.source,
                    provenance_dir=str(provenance_dir),
                )
                print(f"Agentic provenance written to: {provenance_path}")

        except Exception as e:
            print(f"Error in agentic pipeline: {e}", file=sys.stderr)
            if self.verbose:
                import traceback

                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="Import, convert, or generate Claude Code artifacts from repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect mode (dry-run preview)
  %(prog)s --source https://github.com/user/repo --scope user
  
  # Import Claude artifacts
  %(prog)s --source https://github.com/user/repo --scope user --mode import --dry-run=false

  # Convert Fabric patterns to Claude Code
  %(prog)s --source https://github.com/danielmiessler/fabric --scope user --mode convert --dry-run=false

  # Generate skill pack from repository
  %(prog)s --source https://github.com/user/repo --scope project --mode generate --dry-run=false
  
  # Import to specific project
  %(prog)s --source ~/code/skills --scope project --target-repo ~/code/myapp --dry-run=false
        """,
    )

    parser.add_argument("--source", required=True, help="GitHub URL or local path to repository")

    parser.add_argument(
        "--scope",
        required=True,
        choices=["user", "project"],
        help="Installation scope (user: ~/.claude/, project: .claude/)",
    )

    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "import", "convert", "generate"],
        help="Operation mode: auto (detect), import (Claude artifacts), convert (frameworks), generate (from docs) (default: auto)",
    )

    # Add standardized dry-run and apply arguments
    add_dry_run_argument(parser, help_text="Preview changes without writing (default: true)")
    add_apply_argument(parser)

    parser.add_argument(
        "--target-repo", help="Target repository path (required for project scope if not in target repo)"
    )

    parser.add_argument(
        "--overwrite-with-backup",
        action="store_true",
        help="Create timestamped backups before overwriting existing files",
    )

    add_logging_arguments(parser)

    parser.add_argument("--ref", help="Git reference to import (branch, tag)")

    parser.add_argument(
        "--discover-agentic", action="store_true", help="Enable experimental agentic discovery and conversion"
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.65,
        help="Minimum confidence threshold for agentic conversion (default: 0.65)",
    )

    # Skill-creator integration (Option B + Option C)
    skill_creator_group = parser.add_mutually_exclusive_group()
    skill_creator_group.add_argument(
        "--use-skill-creator",
        action="store_true",
        help="Force handoff to skill-creator for skill generation (requires skill-creator installed)",
    )
    skill_creator_group.add_argument(
        "--no-skill-creator",
        action="store_true",
        help="Disable skill-creator handoff (use template-based generation only)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.scope == "project" and not args.target_repo:
        # Use current directory as target
        args.target_repo = os.getcwd()

    # Resolve effective dry-run state (--apply overrides --dry-run)
    effective_dry_run = resolve_dry_run(args)

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    try:
        importer = AssetImporter(
            source=args.source,
            scope=args.scope,
            mode=args.mode,
            dry_run=effective_dry_run,
            target_repo=args.target_repo,
            overwrite_with_backup=args.overwrite_with_backup,
            ref=args.ref,
            discover_agentic=args.discover_agentic,
            min_confidence=args.min_confidence,
            use_skill_creator=args.use_skill_creator,
            no_skill_creator=args.no_skill_creator,
        )

        return importer.import_assets()

    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback

            logger.debug(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
