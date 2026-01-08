#!/usr/bin/env python3
"""
agentic_converter.py

Converts classified agentic content into Claude Code artifacts.
Supports: commands, agents, skills (doc-only), and MCP fragments.

Part of Agentic Discovery & Conversion
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import _init_shared

# Import redaction module
try:
    from redaction import redact_secrets
    from safe_io import safe_write_text
    from cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run
except ImportError:
    from .redaction import redact_secrets
    from .safe_io import safe_write_text
    from .cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run


class AgenticConverter:
    """Converts agentic content to Claude Code format."""

    def __init__(
        self,
        output_dir: Path,
        repo_name: str,
        verbose: bool = False,
        dry_run: bool = True,
        repo_path: Optional[Path] = None,
    ):
        self.output_dir = Path(output_dir)
        self.repo_name = self._sanitize_name(repo_name)
        self.verbose = verbose
        self.dry_run = dry_run
        self.repo_path = repo_path
        self.conversions: List[Dict[str, Any]] = []
        # Detect Context7 integration
        self.context7_enabled = self._detect_context7() if repo_path else False

    def _log(self, message: str):
        if self.verbose:
            print(f"[AGENTIC-CONVERT] {message}", file=sys.stderr)

    def convert(self, classification: Dict[str, Any], threshold: float = 0.65) -> Optional[Dict[str, Any]]:
        """
        Convert a classified file to Claude Code format.

        Args:
            classification: Classification dict from AgenticClassifier
            threshold: Minimum confidence threshold for conversion (default: 0.65)

        Returns:
            Conversion result dict or None if below threshold/failed
        """
        confidence = classification.get("confidence", 0.0)
        source_path = classification.get("source_path", "")

        if confidence < threshold:
            self._log(f"Skipping {source_path}: confidence {confidence} < {threshold}")
            return None

        output_type = classification.get("suggested_output", {}).get("type", "doc_only")

        if output_type == "command":
            return self._convert_to_command(classification)
        elif output_type == "agent":
            return self._convert_to_agent(classification)
        elif output_type == "skill":
            return self._convert_to_skill(classification)
        elif output_type == "mcp_fragment":
            return self._convert_to_mcp_fragment(classification)
        elif output_type == "doc_only":
            self._log(f"Skipping {source_path}: marked as doc_only")
            return None
        else:
            self._log(f"Unknown output type: {output_type}")
            return None

    def convert_all(self, classifications: List[Dict[str, Any]], threshold: float = 0.65) -> List[Dict[str, Any]]:
        """
        Convert all classifications that meet the threshold.

        Args:
            classifications: List of classification dicts
            threshold: Minimum confidence threshold

        Returns:
            List of successful conversion results
        """
        results = []
        for classification in classifications:
            result = self.convert(classification, threshold)
            if result:
                results.append(result)
                self.conversions.append(result)
        return results

    def _convert_to_command(self, classification: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert to Claude Code command."""
        source_path = Path(classification["source_path"])
        name = self._sanitize_name(classification.get("title", source_path.stem))
        output_path = self.output_dir / "commands" / f"{name}.md"

        # Read source content
        content = self._read_source(source_path)
        if content is None:
            return None

        # Generate command format
        command_content = self._generate_command_content(classification, content)

        # Redact secrets
        command_content = redact_secrets(command_content)

        # Write output
        if not self.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if not safe_write_text(output_path, command_content):
                self._log(f"Failed to write command: {output_path}")
                return None
            self._log(f"Wrote command: {output_path}")
        else:
            self._log(f"[DRY-RUN] Would write command: {output_path}")

        return {
            "source_path": str(source_path),
            "output_path": str(output_path),
            "type": "command",
            "classification": classification,
            "dry_run": self.dry_run,
        }

    def _convert_to_agent(self, classification: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert to Claude Code agent."""
        source_path = Path(classification["source_path"])
        name = self._sanitize_name(classification.get("title", source_path.stem))
        output_path = self.output_dir / "agents" / f"{name}.md"

        content = self._read_source(source_path)
        if content is None:
            return None

        agent_content = self._generate_agent_content(classification, content)
        agent_content = redact_secrets(agent_content)

        if not self.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if not safe_write_text(output_path, agent_content):
                self._log(f"Failed to write agent: {output_path}")
                return None
            self._log(f"Wrote agent: {output_path}")
        else:
            self._log(f"[DRY-RUN] Would write agent: {output_path}")

        return {
            "source_path": str(source_path),
            "output_path": str(output_path),
            "type": "agent",
            "classification": classification,
            "dry_run": self.dry_run,
        }

    def _convert_to_skill(self, classification: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert to Claude Code skill (doc-only, no executable scripts)."""
        source_path = Path(classification["source_path"])
        name = self._sanitize_name(classification.get("title", source_path.stem))
        skill_dir = self.output_dir / "skills" / f"{self.repo_name}--{name}"
        skill_md = skill_dir / "SKILL.md"

        content = self._read_source(source_path)
        if content is None:
            return None

        skill_content = self._generate_skill_content(classification, content)
        skill_content = redact_secrets(skill_content)

        if not self.dry_run:
            skill_dir.mkdir(parents=True, exist_ok=True)
            if not safe_write_text(skill_md, skill_content):
                self._log(f"Failed to write skill: {skill_md}")
                return None
            self._log(f"Wrote skill: {skill_dir}/SKILL.md")
        else:
            self._log(f"[DRY-RUN] Would write skill: {skill_dir}/SKILL.md")

        return {
            "source_path": str(source_path),
            "output_path": str(skill_dir),
            "type": "skill",
            "classification": classification,
            "dry_run": self.dry_run,
        }

    def _convert_to_mcp_fragment(self, classification: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert to MCP config fragment."""
        source_path = Path(classification["source_path"])
        output_path = self.output_dir / f".mcp.imported.{self.repo_name}.json"

        # Read and validate JSON
        content = self._read_source(source_path)
        if content is None:
            return None

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON in {source_path}: {e}")
            return None

        # Redact secrets in JSON values
        redacted_json = redact_secrets(json.dumps(data, indent=2))

        if not self.dry_run:
            if not safe_write_text(output_path, redacted_json):
                self._log(f"Failed to write MCP fragment: {output_path}")
                return None
            self._log(f"Wrote MCP fragment: {output_path}")
        else:
            self._log(f"[DRY-RUN] Would write MCP fragment: {output_path}")

        return {
            "source_path": str(source_path),
            "output_path": str(output_path),
            "type": "mcp_fragment",
            "classification": classification,
            "dry_run": self.dry_run,
        }

    def _read_source(self, source_path: Path) -> Optional[str]:
        """Safely read source file content."""
        try:
            if not source_path.exists():
                self._log(f"Source file not found: {source_path}")
                return None
            return source_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError) as e:
            self._log(f"Cannot read {source_path}: {e}")
            return None

    def _detect_context7(self) -> bool:
        """
        Detect if Context7 MCP is configured in the repository or user config.

        Looks for 'context7' key in any .mcp*.json file.
        """
        if not self.repo_path:
            return False

        try:
            # Check .mcp.json and .mcp*.json files
            mcp_patterns = [
                self.repo_path / ".mcp.json",
                *self.repo_path.glob(".mcp*.json"),
            ]

            # Also check user-level config
            user_mcp = Path.home() / ".mcp.json"
            if user_mcp.exists():
                mcp_patterns.append(user_mcp)

            for mcp_path in mcp_patterns:
                if mcp_path.exists():
                    try:
                        with open(mcp_path, "r", encoding="utf-8", errors="replace") as f:
                            data = json.load(f)
                        servers = data.get("mcpServers", {})
                        if "context7" in servers:
                            self._log(f"Context7 detected in {mcp_path}")
                            return True
                    except (json.JSONDecodeError, OSError):
                        continue
        except Exception as e:
            self._log(f"Error detecting Context7: {e}")

        return False

    def _get_context7_hint(self, artifact_type: str = "command") -> str:
        """
        Generate Context7 usage hint for inclusion in converted artifacts.

        Args:
            artifact_type: 'command' or 'agent'

        Returns:
            Markdown hint text or empty string if Context7 not available
        """
        if not self.context7_enabled:
            return ""

        if artifact_type == "command":
            return """\n## Documentation

> **💡 Context7 Tip**: This project is configured with Context7 MCP.
> Use `context7` to fetch current API documentation when working with
> external libraries or frameworks referenced in this command.
"""
        elif artifact_type == "agent":
            return """\n## Docs Policy

> **💡 Context7 Integration**: Context7 MCP is available for this project.
> When this agent needs API documentation or library references, prefer
> using the `resolve-library-id` and `get-library-docs` tools from Context7
> to ensure up-to-date information.
"""
        return ""

    def _generate_command_content(self, classification: Dict[str, Any], source_content: str) -> str:
        """Generate Claude Code command from source content."""
        title = classification.get("title", "Converted Command")
        kind = classification.get("kind", "unknown")
        signals = classification.get("signals", [])
        confidence = classification.get("confidence", 0.0)
        rel_path = classification.get("rel_path", classification.get("source_path", ""))
        context7_hint = self._get_context7_hint("command")

        return f"""# {title}

> **Auto-generated command from `{rel_path}`**
> 
> - **Kind:** {kind}
> - **Confidence:** {confidence:.0%}
> - **Signals:** {", ".join(signals) if signals else "none"}
> - **Converted:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

## How to Use

This command was automatically converted from an agentic document.
Review and customize as needed before using.
{context7_hint}
---

## Original Content

{source_content}

---

*Converted by mine (Agentic Conversion)*
"""

    def _generate_agent_content(self, classification: Dict[str, Any], source_content: str) -> str:
        """Generate Claude Code agent from source content."""
        title = classification.get("title", "Converted Agent")
        signals = classification.get("signals", [])
        confidence = classification.get("confidence", 0.0)
        rel_path = classification.get("rel_path", classification.get("source_path", ""))
        context7_hint = self._get_context7_hint("agent")

        return f"""# {title}

> **Auto-generated agent from `{rel_path}`**
> 
> - **Confidence:** {confidence:.0%}
> - **Signals:** {", ".join(signals) if signals else "none"}
> - **Converted:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Role

This agent was automatically converted from an agentic document.
Define the agent's role, goals, and capabilities based on the original content below.
{context7_hint}
---

## Original Content

{source_content}

---

## Usage Examples

Add usage examples after reviewing and customizing this agent.

---

*Converted by mine (Agentic Conversion)*
"""

    def _generate_skill_content(self, classification: Dict[str, Any], source_content: str) -> str:
        """Generate Claude Code skill documentation."""
        title = classification.get("title", "Converted Skill")
        name = self._sanitize_name(title)
        signals = classification.get("signals", [])
        confidence = classification.get("confidence", 0.0)
        rel_path = classification.get("rel_path", classification.get("source_path", ""))

        return f"""---
name: {name}
description: Auto-generated skill from {rel_path}
---

# {title}

> **Auto-generated from `{rel_path}`**
> 
> - **Confidence:** {confidence:.0%}
> - **Signals:** {", ".join(signals) if signals else "none"}
> - **Converted:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Overview

This skill was automatically converted from a repository tool/API specification.
Review and add executable scripts under `scripts/` if needed.

> **Note:** This is a documentation-only skill. No executable scripts were generated
> for safety. Add your own scripts after review.

---

## Original Content

{source_content}

---

*Converted by mine (Agentic Conversion)*
"""

    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for filesystem use."""
        # Remove non-alphanumeric except hyphens/underscores, lowercase
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
        sanitized = re.sub(r"-+", "-", sanitized).strip("-").lower()
        # Limit length
        return sanitized[:100] if sanitized else "converted"


def convert_agentic_content(
    classifications: List[Dict[str, Any]],
    output_dir: str,
    repo_name: str,
    threshold: float = 0.65,
    dry_run: bool = True,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Convenience function to convert classified agentic content.

    Args:
        classifications: List of classification dicts from AgenticClassifier
        output_dir: Output directory for converted artifacts
        repo_name: Repository name for namespacing
        threshold: Minimum confidence threshold (default: 0.65)
        dry_run: If True, don't write files
        verbose: Enable verbose logging

    Returns:
        List of conversion result dicts
    """
    converter = AgenticConverter(
        output_dir=Path(output_dir),
        repo_name=repo_name,
        verbose=verbose,
        dry_run=dry_run,
    )
    return converter.convert_all(classifications, threshold)


def main():
    """CLI entry point for standalone conversion."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert agentic content to Claude Code format")

    parser.add_argument("--source", required=True, help="Source file to convert")

    parser.add_argument("--output", required=True, help="Output directory")

    parser.add_argument("--repo-name", default="converted", help="Repository name for namespacing")

    parser.add_argument(
        "--type", choices=["command", "agent", "skill", "mcp_fragment"], required=True, help="Output type"
    )

    parser.add_argument("--threshold", type=float, default=0.65, help="Confidence threshold (default: 0.65)")

    # Add standardized dry-run and apply arguments
    add_dry_run_argument(parser, help_text="Preview without writing (default: true)")
    add_apply_argument(parser)

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Resolve effective dry-run state
    effective_dry_run = resolve_dry_run(args)

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"Error: Source not found: {source_path}", file=sys.stderr)
        return 1

    # Create mock classification for manual conversion
    classification = {
        "source_path": str(source_path),
        "rel_path": str(source_path),
        "kind": "unknown",
        "signals": ["manual_conversion"],
        "confidence": 1.0,  # Manual = full confidence
        "title": source_path.stem,
        "suggested_output": {"type": args.type, "name": "manual"},
    }

    converter = AgenticConverter(
        output_dir=Path(args.output),
        repo_name=args.repo_name,
        verbose=args.verbose,
        dry_run=effective_dry_run,
    )

    result = converter.convert(classification, threshold=args.threshold)

    if result:
        print(json.dumps(result, indent=2, default=str))
        return 0
    else:
        print("Conversion failed or skipped", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
