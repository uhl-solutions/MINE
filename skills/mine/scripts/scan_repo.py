#!/usr/bin/env python3
"""
scan_repo.py - Scan repositories for Claude Code artifacts

Detects skills, commands, agents, hooks, MCP configs, and documentation
in GitHub repositories or local paths, and outputs a structured JSON report.
"""

import argparse
import hashlib
import json
from datetime import datetime
import os
import re
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import _init_shared
from safe_io import safe_write_json
from logging_utils import setup_logging, get_logger, add_logging_arguments

# Constants
MAX_ARTIFACTS = 1000
MAX_SCAN_TIME = 300  # 5 minutes


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
            # Check for high percentage of non-text characters
            text_chars = set(bytes(range(32, 127)) + b"\n\r\t")
            non_text = sum(1 for b in chunk if b not in text_chars)
            return non_text / len(chunk) > 0.3 if chunk else False
    except (IOError, OSError):
        return False


class RepoScanner:
    """Scans repositories for Claude Code artifacts."""

    def __init__(
        self, source: str, ref: Optional[str] = None, max_artifacts: int = MAX_ARTIFACTS, verbose: bool = False
    ):
        self.source = str(source)
        self.ref = ref
        # verbose is deprecated, handled via logging
        self.max_artifacts = max_artifacts
        self.artifact_count = 0
        self.start_time = None
        self.repo_path: Optional[Path] = None
        self.temp_dir: Optional[str] = None
        self.repo_id = self._extract_repo_id(self.source)
        self.logger = get_logger(__name__)

    def _extract_repo_id(self, source: str) -> str:
        """Extract repository ID from URL or path."""
        source_str = str(source)
        if source_str.startswith("http"):
            # GitHub URL: https://github.com/user/repo
            match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(\.git)?$", source_str)
            if match:
                return match.group(1)
            return "unknown-repo"
        else:
            # Local path: use directory name
            return Path(source).name

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        self.logger.debug(message)

    def _safe_path_str(self, path: Path) -> str:
        """Safely convert path to string, handling encoding issues."""
        try:
            return str(path)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback to a lossy but safe representation
            try:
                return os.fsdecode(os.fsencode(path))
            except Exception:
                return repr(path)

    def _check_limits(self, report: Dict[str, Any]) -> bool:
        """Check if we've hit any limits."""
        if self.start_time and time.monotonic() - self.start_time > MAX_SCAN_TIME:
            report["truncated"] = True
            report["truncation_reason"] = "scan_timeout"
            return False

        if self.artifact_count >= self.max_artifacts:
            report["truncated"] = True
            report["truncation_reason"] = "max_artifacts"
            return False

        return True

    def _track_artifact(self, report: Dict[str, Any], artifact: Dict[str, Any]):
        """Add artifact to report and increment count."""
        if self._check_limits(report):
            report["detected_artifacts"].append(artifact)
            self.artifact_count += 1

    def _clone_repo(self) -> Path:
        """Clone repository to temporary directory if source is a URL.

        Uses centralized clone helper with secure GIT_ASKPASS authentication.
        """
        if not self.source.startswith("http"):
            # Local path
            self._log(f"Using local path: {self.source}")
            return Path(self.source).resolve()

        # Import secure helpers
        try:
            from url_utils import clone_with_auth_fallback, redact_url_credentials
        except ImportError:
            redact_url_credentials = lambda x: x
            clone_with_auth_fallback = None

        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="claude-repo-scan-")
        dest = Path(self.temp_dir) / "repo"

        ref_msg = f" (ref: {self.ref})" if self.ref else ""
        self._log(f"Cloning {redact_url_credentials(self.source)}{ref_msg} to {dest}")

        # Prepare extra arguments
        extra_args = ["--branch", self.ref] if self.ref else None

        # Use centralized clone helper (handles gh CLI, askpass, and plain git fallback)
        if clone_with_auth_fallback is not None:
            if clone_with_auth_fallback(
                self.source, dest, depth=1, extra_args=extra_args, verbose=self.logger.isEnabledFor(logging.DEBUG)
            ):
                return dest

        # Ultimate fallback: plain git clone (no auth)
        self._log("Using unauthenticated git clone")
        cmd = ["git", "clone", "--depth", "1"]
        if self.ref:
            cmd.extend(["--branch", self.ref])
        cmd.extend([self.source, str(dest)])

        subprocess.run(cmd, check=True, capture_output=True)
        return dest

    def _get_file_mode(self, path: Path) -> Optional[int]:
        """Get file mode bits."""
        try:
            return path.stat().st_mode
        except OSError:
            return None

    def _create_artifact_mapping(
        self, artifact_type: str, source_relpath: str, dest_relpath: str, is_directory: bool = False
    ) -> Dict[str, Any]:
        """Create mapping dictionary for an artifact."""
        source_path = self.repo_path / source_relpath

        if is_directory:
            # Assuming _hash_directory is defined elsewhere or will be added
            # For now, a placeholder
            last_hash = ""  # self._hash_directory(source_path)
            file_mode = None
        else:
            # Store content hash for file
            try:
                content = source_path.read_bytes()
                last_hash = hashlib.sha256(content).hexdigest()
                file_mode = self._get_file_mode(source_path)
            except (OSError, IOError):
                last_hash = ""
                file_mode = None

        return {
            "type": artifact_type,
            "source_relpath": str(source_relpath),
            "dest_relpath": str(dest_relpath),  # Keep relative for portability
            "is_directory": is_directory,
            "last_import_hash": last_hash,
            "last_import_time": datetime.now().isoformat(),
            "file_mode": file_mode,
        }

    def scan(self) -> Dict[str, Any]:
        """Scan repository and return structured report."""
        try:
            self.repo_path = self._clone_repo()
            self.start_time = time.monotonic()

            report = {
                "repo_id": self.repo_id,
                "source": self.source,
                "detected_artifacts": [],
                "suggested_actions": [],
                "risks": [],
                "framework_type": None,
                "truncated": False,
                "truncation_reason": None,
            }

            # First detect if this is a known framework
            self._detect_framework(report)

            # Scan for different artifact types
            self._scan_skills(report)
            self._scan_commands(report)
            self._scan_agents(report)
            self._scan_hooks(report)
            self._scan_mcp_configs(report)
            self._scan_plugins(report)
            self._scan_documentation(report)
            self._scan_build_files(report)

            # If framework detected, scan framework-specific artifacts
            if report["framework_type"]:
                self._scan_framework_artifacts(report)

            # Determine suggested actions
            has_claude_artifacts = any(
                a["type"] in ["skill", "command", "agent", "hook", "mcp_config"] for a in report["detected_artifacts"]
            )

            if has_claude_artifacts:
                report["suggested_actions"].append("import")
            elif report["framework_type"]:
                report["suggested_actions"].append("convert")
            else:
                report["suggested_actions"].append("generate")

            return report

        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _scan_skills(self, report: Dict[str, Any]):
        """Scan for skill artifacts."""
        skill_patterns = [".claude/skills/**/SKILL.md", "skills/**/SKILL.md"]

        for pattern in skill_patterns:
            for skill_file in self.repo_path.glob(pattern):
                if skill_file.is_symlink():
                    self._log(f"Skipping symlink: {skill_file.relative_to(self.repo_path)}")
                    continue

                skill_dir = skill_file.parent
                self._log(f"Found skill: {skill_file.relative_to(self.repo_path)}")

                # Validate YAML frontmatter
                notes = "Complete skill"
                try:
                    with open(skill_file, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        if not content.startswith("---"):
                            notes = "Warning: Missing YAML frontmatter"
                        elif "name:" not in content[:500]:
                            notes = "Warning: Missing 'name' field"
                        elif "description:" not in content[:500]:
                            notes = "Warning: Missing 'description' field"

                        # Check for bundled resources
                        has_scripts = (skill_dir / "scripts").exists()
                        has_refs = (skill_dir / "references").exists()
                        has_assets = (skill_dir / "assets").exists()

                        if has_scripts or has_refs or has_assets:
                            resources = []
                            if has_scripts:
                                resources.append("scripts")
                            if has_refs:
                                resources.append("references")
                            if has_assets:
                                resources.append("assets")
                            notes = f"Complete skill with {', '.join(resources)}"

                except Exception as e:
                    notes = f"Error reading skill: {e}"

                skill_name = skill_dir.name
                self._track_artifact(
                    report,
                    {
                        "type": "skill",
                        "source_path": self._safe_path_str(skill_file.relative_to(self.repo_path)),
                        "destination_suggestions": {
                            "user": f"~/.claude/skills/{skill_name}/",
                            "project": f".claude/skills/{skill_name}/",
                        },
                        "notes": notes,
                    },
                )

                if report.get("truncated"):
                    return

    def _scan_commands(self, report: Dict[str, Any]):
        """Scan for command artifacts."""
        command_patterns = [".claude/commands/*.md", "commands/*.md"]

        for pattern in command_patterns:
            for cmd_file in self.repo_path.glob(pattern):
                if cmd_file.is_symlink():
                    self._log(f"Skipping symlink: {cmd_file.relative_to(self.repo_path)}")
                    continue

                self._log(f"Found command: {cmd_file.relative_to(self.repo_path)}")

                cmd_name = cmd_file.name
                self._track_artifact(
                    report,
                    {
                        "type": "command",
                        "source_path": self._safe_path_str(cmd_file.relative_to(self.repo_path)),
                        "destination_suggestions": {
                            "user": f"~/.claude/commands/{cmd_name}",
                            "project": f".claude/commands/{cmd_name}",
                        },
                        "notes": "Command file",
                    },
                )

                if report.get("truncated"):
                    return

    def _scan_agents(self, report: Dict[str, Any]):
        """Scan for agent artifacts."""
        agent_patterns = [".claude/agents/*.md", "agents/*.md"]

        for pattern in agent_patterns:
            for agent_file in self.repo_path.glob(pattern):
                if agent_file.is_symlink():
                    self._log(f"Skipping symlink: {agent_file.relative_to(self.repo_path)}")
                    continue

                self._log(f"Found agent: {agent_file.relative_to(self.repo_path)}")

                agent_name = agent_file.name
                self._track_artifact(
                    report,
                    {
                        "type": "agent",
                        "source_path": self._safe_path_str(agent_file.relative_to(self.repo_path)),
                        "destination_suggestions": {
                            "user": f"~/.claude/agents/{agent_name}",
                            "project": f".claude/agents/{agent_name}",
                        },
                        "notes": "Agent definition",
                    },
                )

                if report.get("truncated"):
                    return

    def _scan_hooks(self, report: Dict[str, Any]):
        """Scan for hook artifacts and assess risks."""
        hook_patterns = [".claude/hooks/*", ".claude/hooks/**/*"]

        for pattern in hook_patterns:
            for hook_file in self.repo_path.glob(pattern):
                if hook_file.is_file():
                    if hook_file.is_symlink():
                        self._log(f"Skipping symlink: {hook_file.relative_to(self.repo_path)}")
                        continue

                    self._log(f"Found hook: {hook_file.relative_to(self.repo_path)}")

                    # Assess risk
                    severity = self._assess_hook_risk(hook_file)
                    reason = self._get_risk_reason(hook_file)

                    hook_name = hook_file.name
                    self._track_artifact(
                        report,
                        {
                            "type": "hook",
                            "source_path": self._safe_path_str(hook_file.relative_to(self.repo_path)),
                            "destination_suggestions": {
                                "project": f".claude/hooks.imported.{self.repo_id.replace('/', '-')}/{hook_name}"
                            },
                            "notes": "Hook (requires manual review and enablement)",
                        },
                    )

                    report["risks"].append(
                        {
                            "type": "hook",
                            "path": self._safe_path_str(hook_file.relative_to(self.repo_path)),
                            "severity": severity,
                            "reason": reason,
                        }
                    )

                    if report.get("truncated"):
                        return

        # Also check settings.json for hook configurations
        settings_files = [".claude/settings.json", ".claude/settings.local.json"]

        for settings_file in settings_files:
            settings_path = self.repo_path / settings_file
            if settings_path.exists():
                try:
                    with open(settings_path, "r", encoding="utf-8", errors="replace") as f:
                        settings = json.load(f)
                        if "hooks" in settings:
                            self._log(f"Found hook configuration in {settings_file}")
                            report["detected_artifacts"].append(
                                {
                                    "type": "hook_config",
                                    "source_path": settings_file,
                                    "destination_suggestions": {
                                        "project": f".claude/settings.imported.{self.repo_id.replace('/', '-')}.json"
                                    },
                                    "notes": "Settings with hook configuration (requires manual merge)",
                                }
                            )

                            report["risks"].append(
                                {
                                    "type": "hook_config",
                                    "path": settings_file,
                                    "severity": "medium",
                                    "reason": "Contains hook configurations that execute automatically",
                                }
                            )
                except Exception as e:
                    self._log(f"Error reading {settings_file}: {e}")

    def _assess_hook_risk(self, hook_file: Path) -> str:
        """Assess risk level of a hook file."""
        if is_binary_file(hook_file):
            return "high"

        # Check file extension and permissions
        if hook_file.suffix in [".sh", ".bash", ".zsh"]:
            return "medium"

        if os.access(hook_file, os.X_OK):
            return "medium"

        return "low"

    def _get_risk_reason(self, hook_file: Path) -> str:
        """Get human-readable reason for hook risk."""
        if is_binary_file(hook_file):
            return "Binary executable"

        reasons = []

        if hook_file.suffix in [".sh", ".bash", ".zsh"]:
            reasons.append("shell script")

        if os.access(hook_file, os.X_OK):
            reasons.append("executable permissions")

        if not reasons:
            reasons.append("hook file")

        return ", ".join(reasons).capitalize()

    def _scan_mcp_configs(self, report: Dict[str, Any]):
        """Scan for MCP configuration files."""
        mcp_patterns = [".mcp.json", ".claude-plugin/mcp.json", "mcp.json"]

        for pattern in mcp_patterns:
            mcp_file = self.repo_path / pattern
            if mcp_file.exists():
                if mcp_file.is_symlink():
                    self._log(f"Skipping symlink: {pattern}")
                    continue

                self._log(f"Found MCP config: {pattern}")

                self._track_artifact(
                    report,
                    {
                        "type": "mcp_config",
                        "source_path": self._safe_path_str(Path(pattern)),
                        "destination_suggestions": {
                            "user": f"~/.mcp.imported.{self.repo_id.replace('/', '-')}.json",
                            "project": f".mcp.imported.{self.repo_id.replace('/', '-')}.json",
                        },
                        "notes": "MCP configuration (requires manual merge with .mcp.json)",
                    },
                )

    def _scan_plugins(self, report: Dict[str, Any]):
        """Scan for plugin manifests."""
        plugin_patterns = [".claude-plugin/marketplace.json", ".claude-plugin/plugin.json", "plugin.json"]

        for pattern in plugin_patterns:
            plugin_file = self.repo_path / pattern
            if plugin_file.exists():
                if plugin_file.is_symlink():
                    self._log(f"Skipping symlink: {pattern}")
                    continue

                self._log(f"Found plugin manifest: {pattern}")

                report["detected_artifacts"].append(
                    {
                        "type": "plugin",
                        "source_path": pattern,
                        "destination_suggestions": {},
                        "notes": "Plugin manifest (informational, not auto-imported)",
                    }
                )

    def _scan_documentation(self, report: Dict[str, Any]):
        """Scan for documentation files."""
        doc_patterns = ["CLAUDE.md", "README.md", "README.rst", "README.txt", "CONTRIBUTING.md"]

        for pattern in doc_patterns:
            doc_file = self.repo_path / pattern
            if doc_file.exists():
                if doc_file.is_symlink():
                    self._log(f"Skipping symlink: {pattern}")
                    continue

                self._log(f"Found documentation: {pattern}")

                if pattern == "CLAUDE.md":
                    report["detected_artifacts"].append(
                        {
                            "type": "claude_md",
                            "source_path": pattern,
                            "destination_suggestions": {
                                "user": f"~/.claude/CLAUDE.imported.{self.repo_id.replace('/', '-')}.md",
                                "project": f".claude/CLAUDE.imported.{self.repo_id.replace('/', '-')}.md",
                            },
                            "notes": "Claude instructions (requires manual merge with CLAUDE.md)",
                        }
                    )
                else:
                    report["detected_artifacts"].append(
                        {
                            "type": "documentation",
                            "source_path": pattern,
                            "destination_suggestions": {},
                            "notes": "Documentation (used for skill generation)",
                        }
                    )

    def _scan_build_files(self, report: Dict[str, Any]):
        """Scan for build/workflow files."""
        build_patterns = [
            "Makefile",
            "package.json",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Cargo.toml",
            "go.mod",
        ]

        for pattern in build_patterns:
            build_file = self.repo_path / pattern
            if build_file.exists():
                if build_file.is_symlink():
                    self._log(f"Skipping symlink: {pattern}")
                    continue

                self._log(f"Found build file: {pattern}")

                report["detected_artifacts"].append(
                    {
                        "type": "build_file",
                        "source_path": pattern,
                        "destination_suggestions": {},
                        "notes": "Build configuration (used for skill generation)",
                    }
                )

    def _detect_framework(self, report: Dict[str, Any]):
        """Detect if this is a known AI framework repository."""
        # Check for Fabric
        if self._is_fabric_repo():
            report["framework_type"] = "fabric"
            self._log("Detected Fabric framework")
            return

        # Check for other frameworks
        if self._is_langchain_repo():
            report["framework_type"] = "langchain"
            self._log("Detected LangChain framework")
            return

        if self._is_autogen_repo():
            report["framework_type"] = "autogen"
            self._log("Detected AutoGen framework")
            return

        # Add more framework detections as needed

    def _is_fabric_repo(self) -> bool:
        """
        Check if this is a Fabric repository.

        Detection strategy:
        1. Strong indicators (cmd/fabric, patterns with system.md) → immediate True
        2. README mentions are tie-breakers, only with structural evidence
        3. Avoid false positives from README-only mentions of "fabric"
        """
        # Strong structural indicators
        has_patterns_dir = (self.repo_path / "patterns").is_dir()
        has_fabric_cmd = (self.repo_path / "cmd" / "fabric").exists()
        has_client = (self.repo_path / "client").exists()

        # cmd/fabric is a very strong indicator (official Fabric layout)
        if has_fabric_cmd:
            return True

        # If we have the patterns directory, verify it contains Fabric-style patterns
        if has_patterns_dir:
            patterns_path = self.repo_path / "patterns"
            try:
                # Check for at least one pattern with system.md (Fabric pattern structure)
                for d in patterns_path.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        if (d / "system.md").exists():
                            # Found a Fabric-style pattern
                            return True
            except (OSError, PermissionError):
                pass

        # README hints + weak structural indicators = possible Fabric
        # Only use as tie-breaker when we have SOME structure
        if has_client and has_patterns_dir:
            readme_path = self.repo_path / "README.md"
            if readme_path.exists():
                try:
                    with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(2000).lower()
                        # More specific check: look for Fabric-specific mentions
                        # Must have "fabric" AND ("danielmiessler" OR "pattern" with "prompt")
                        if "fabric" in content:
                            if "danielmiessler" in content:
                                return True
                            if "pattern" in content and "prompt" in content:
                                return True
                except (OSError, UnicodeError):
                    pass

        return False

    def _is_langchain_repo(self) -> bool:
        """Check if this is a LangChain repository."""
        indicators = [
            (self.repo_path / "langchain").is_dir(),
            (self.repo_path / "libs" / "langchain").is_dir(),
        ]
        return any(indicators)

    def _is_autogen_repo(self) -> bool:
        """Check if this is an AutoGen repository."""
        indicators = [
            (self.repo_path / "autogen").is_dir(),
            (self.repo_path / "notebook").is_dir() and (self.repo_path / "autogen").exists(),
        ]
        return any(indicators)

    def _scan_framework_artifacts(self, report: Dict[str, Any]):
        """Scan framework-specific artifacts for conversion."""
        framework = report["framework_type"]

        if framework == "fabric":
            self._scan_fabric_patterns(report)
        elif framework == "langchain":
            self._scan_langchain_chains(report)
        elif framework == "autogen":
            self._scan_autogen_agents(report)

    def _scan_fabric_patterns(self, report: Dict[str, Any]):
        """Scan Fabric patterns directory for convertible patterns."""
        patterns_dir = self.repo_path / "patterns"

        if not patterns_dir.exists():
            return

        self._log("Scanning Fabric patterns...")

        # Each subdirectory in patterns/ is a pattern
        for pattern_dir in patterns_dir.iterdir():
            if not pattern_dir.is_dir() or pattern_dir.is_symlink():
                continue

            # Look for system.md, user.md, or pattern files
            system_md = pattern_dir / "system.md"
            user_md = pattern_dir / "user.md"

            if system_md.exists() or user_md.exists():
                self._log(f"Found Fabric pattern: {pattern_dir.name}")

                # Determine what type of Claude artifact this would become
                pattern_type = self._classify_fabric_pattern(pattern_dir)

                report["detected_artifacts"].append(
                    {
                        "type": "fabric_pattern",
                        "source_path": str(pattern_dir.relative_to(self.repo_path)),
                        "destination_suggestions": {
                            "user": f"~/.claude/{pattern_type}/{pattern_dir.name}.md",
                            "project": f".claude/{pattern_type}/{pattern_dir.name}.md",
                        },
                        "notes": f"Fabric pattern (convertible to Claude {pattern_type})",
                        "conversion_type": pattern_type,
                        "pattern_name": pattern_dir.name,
                    }
                )

    def _classify_fabric_pattern(self, pattern_dir: Path) -> str:
        """Classify a Fabric pattern into Claude artifact type."""
        pattern_name = pattern_dir.name.lower()

        # Read system.md to understand the pattern
        system_md = pattern_dir / "system.md"
        content = ""

        if system_md.exists():
            try:
                with open(system_md, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(1000).lower()
            except (OSError, UnicodeError):
                pass

        # Classification logic based on pattern characteristics
        # Agents: complex reasoning, multi-step processes
        agent_indicators = ["agent", "analyze", "review", "evaluate", "assess", "expert"]
        if any(ind in pattern_name for ind in agent_indicators):
            return "agents"

        if any(ind in content for ind in ["step by step", "first,", "then,", "analyze"]):
            return "agents"

        # Commands: simple, action-oriented
        command_indicators = ["extract", "summarize", "create", "generate", "improve"]
        if any(ind in pattern_name for ind in command_indicators):
            return "commands"

        # Default to commands for simpler patterns
        return "commands"

    def _scan_langchain_chains(self, report: Dict[str, Any]):
        """Scan LangChain chains for conversion."""
        # Look for chain definitions
        for chain_file in self.repo_path.rglob("*chain*.py"):
            if "test" not in str(chain_file).lower():
                report["detected_artifacts"].append(
                    {
                        "type": "langchain_chain",
                        "source_path": str(chain_file.relative_to(self.repo_path)),
                        "destination_suggestions": {"user": f"~/.claude/agents/{chain_file.stem}.md"},
                        "notes": "LangChain chain (convertible to Claude agent)",
                    }
                )

    def _scan_autogen_agents(self, report: Dict[str, Any]):
        """Scan AutoGen agents for conversion."""
        # Look for agent definitions
        for agent_file in self.repo_path.rglob("*agent*.py"):
            if "test" not in str(agent_file).lower():
                report["detected_artifacts"].append(
                    {
                        "type": "autogen_agent",
                        "source_path": str(agent_file.relative_to(self.repo_path)),
                        "destination_suggestions": {"user": f"~/.claude/agents/{agent_file.stem}.md"},
                        "notes": "AutoGen agent (convertible to Claude agent)",
                    }
                )


def main():
    parser = argparse.ArgumentParser(
        description="Scan repository for Claude Code artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan a GitHub repository
  %(prog)s --source https://github.com/user/repo

  # Scan a local directory
  %(prog)s --source ~/code/my-project

  # Save report to file
  %(prog)s --source https://github.com/user/repo --output report.json
        """,
    )

    parser.add_argument("--source", required=True, help="GitHub URL or local path to repository")

    parser.add_argument("--output", help="Output file for JSON report (default: stdout)")

    parser.add_argument("--ref", help="Git reference to scan (branch, tag)")

    add_logging_arguments(parser)

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = get_logger(__name__)

    try:
        scanner = RepoScanner(args.source, ref=args.ref)
        report = scanner.scan()

        # Output report
        json_output = json.dumps(report, indent=2)

        if args.output:
            if not safe_write_json(Path(args.output), report):
                logger.error(f"Error: Failed to write scan report to {args.output}")
                return 1
            logger.info(f"✓ Scan report written to {args.output}")
        else:
            # Output to stdout if no file specified
            # We use json.dumps here because safe_write_json writes to a file
            print(json.dumps(report, indent=2))

        return 0

    except subprocess.CalledProcessError as e:
        logger.error(f"Error: Failed to clone repository: {e}")
        return 3
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback

            logger.debug(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
