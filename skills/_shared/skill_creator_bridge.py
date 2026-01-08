#!/usr/bin/env python3
"""
skill_creator_bridge.py - Bridge module for Anthropic's skill-creator integration

Provides detection, handoff context generation, and inter-skill communication
for delegating complex skill creation to Anthropic's skill-creator skill.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Default confidence threshold below which handoff is recommended
DEFAULT_HANDOFF_THRESHOLD = 0.5

# Standard skill-creator installation paths
SKILL_CREATOR_PATHS = [
    Path.home() / ".claude" / "skills" / "skill-creator",
    Path.home() / ".claude" / "skills" / "skill_creator",
]


def is_skill_creator_available() -> bool:
    """
    Check if Anthropic's skill-creator skill is installed.

    Returns:
        True if skill-creator is found in standard locations, False otherwise.
    """
    for path in SKILL_CREATOR_PATHS:
        skill_md = path / "SKILL.md"
        if skill_md.exists() and skill_md.is_file():
            return True
    return False


def get_skill_creator_path() -> Optional[Path]:
    """
    Get the installation path of skill-creator if available.

    Returns:
        Path to skill-creator directory, or None if not installed.
    """
    for path in SKILL_CREATOR_PATHS:
        skill_md = path / "SKILL.md"
        if skill_md.exists() and skill_md.is_file():
            return path
    return None


def should_handoff(
    confidence_score: float,
    force_handoff: bool = False,
    disable_handoff: bool = False,
    threshold: float = DEFAULT_HANDOFF_THRESHOLD,
) -> Tuple[bool, str]:
    """
    Determine if skill creation should be handed off to skill-creator.

    Uses Option B (conservative) with Option C (user control):
    - By default, only hands off when confidence is below threshold
    - User can force handoff with --use-skill-creator
    - User can disable handoff with --no-skill-creator

    Args:
        confidence_score: Confidence in template-based conversion (0.0-1.0)
        force_handoff: User explicitly requested skill-creator
        disable_handoff: User explicitly disabled skill-creator
        threshold: Confidence threshold below which handoff is recommended

    Returns:
        Tuple of (should_handoff: bool, reason: str)
    """
    # User control takes precedence
    if disable_handoff:
        return False, "User disabled skill-creator handoff"

    if force_handoff:
        if not is_skill_creator_available():
            return False, "skill-creator requested but not installed"
        return True, "User requested skill-creator handoff"

    # Auto-detect mode: check confidence
    if confidence_score < threshold:
        if is_skill_creator_available():
            return True, f"Low confidence ({confidence_score:.2f} < {threshold}) - recommending skill-creator"
        else:
            return False, "Low confidence but skill-creator not installed - using templates"

    return False, f"High confidence ({confidence_score:.2f}) - using template conversion"


def generate_handoff_context(
    source: str,
    source_type: str,
    scope: str,
    target_dir: str,
    analysis: Dict[str, Any],
    source_content: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Generate structured handoff context for skill-creator.

    This context provides skill-creator with all information needed
    to create a high-quality skill from the analyzed content.

    Args:
        source: Source repository URL or path
        source_type: Type of source (agentic_discovery, framework_conversion, workflow_generation)
        scope: Target scope (user or project)
        target_dir: Target directory for skill output
        analysis: Analysis results from MINE's scanning
        source_content: Optional extracted content (readme, prompts, docs)
        dry_run: Whether this is a dry-run operation

    Returns:
        Structured handoff context dict
    """
    context = {
        "handoff_type": "skill_creation",
        "source_skill": "mine",
        "version": "1.0",
        "request": {
            "action": "create_skill",
            "source_repo": source,
            "source_type": source_type,
            "analysis": {
                "detected_patterns": analysis.get("detected_patterns", []),
                "language": analysis.get("language", "unknown"),
                "frameworks": analysis.get("frameworks", []),
                "confidence_score": analysis.get("confidence_score", 0.0),
                "reason_for_handoff": analysis.get("reason_for_handoff", "Low confidence in template conversion"),
                "artifact_types": analysis.get("artifact_types", []),
            },
        },
        "constraints": {
            "scope": scope,
            "target_dir": target_dir,
            "dry_run": dry_run,
        },
    }

    # Add source content if provided
    if source_content:
        context["request"]["source_content"] = {
            "readme": source_content.get("readme", ""),
            "prompts": source_content.get("prompts", []),
            "docs": source_content.get("docs", []),
            "detected_files": source_content.get("detected_files", []),
        }

    return context


def create_skill_request_file(
    context: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Create a skill creation request file for skill-creator.

    This file can be used to communicate the request to skill-creator
    in a structured format.

    Args:
        context: Handoff context from generate_handoff_context()
        output_path: Optional output path for the request file

    Returns:
        Path to the created request file
    """
    if output_path is None:
        # Default to temp location
        output_path = Path.home() / ".claude" / "mine" / "skill_creator_request.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)

    return output_path


def format_handoff_message(
    context: Dict[str, Any],
    verbose: bool = False,
) -> str:
    """
    Format a human-readable handoff message for the user.

    This message explains what MINE is handing off to skill-creator
    and provides context for the user.

    Args:
        context: Handoff context from generate_handoff_context()
        verbose: Whether to include detailed information

    Returns:
        Formatted message string
    """
    request = context.get("request", {})
    analysis = request.get("analysis", {})
    constraints = context.get("constraints", {})

    lines = [
        "",
        "=" * 70,
        "SKILL-CREATOR HANDOFF",
        "=" * 70,
        "",
        f"Source: {request.get('source_repo', 'unknown')}",
        f"Reason: {analysis.get('reason_for_handoff', 'Low confidence')}",
        f"Confidence: {analysis.get('confidence_score', 0.0):.1%}",
        "",
    ]

    if verbose:
        lines.extend(
            [
                "Analysis:",
                f"  Language: {analysis.get('language', 'unknown')}",
                f"  Frameworks: {', '.join(analysis.get('frameworks', [])) or 'none detected'}",
                f"  Patterns: {len(analysis.get('detected_patterns', []))} detected",
                "",
            ]
        )

    lines.extend(
        [
            "To complete skill creation, use Anthropic's skill-creator skill:",
            "",
            "  1. Ensure skill-creator is installed: ~/.claude/skills/skill-creator/",
            "  2. Ask Claude: 'Create a skill for [your workflow description]'",
            "  3. skill-creator will guide you through the process",
            "",
            f"Target: {constraints.get('target_dir', 'unknown')}",
            f"Scope: {constraints.get('scope', 'unknown')}",
            "",
            "=" * 70,
            "",
        ]
    )

    return "\n".join(lines)


def get_skill_creator_instructions(
    source: str,
    description: str,
    target_scope: str,
) -> str:
    """
    Generate instructions for using skill-creator to complete the handoff.

    These instructions are included in MINE's output when it hands off
    to skill-creator, guiding the user on next steps.

    Args:
        source: Source repository URL or path
        description: Brief description of what the skill should do
        target_scope: Target scope (user or project)

    Returns:
        Instruction text for the user
    """
    return f"""
## Skill-Creator Handoff

MINE has analyzed the source but recommends using Anthropic's `skill-creator`
for higher-quality skill generation.

### Next Steps

Ask Claude to create a skill with this context:

> Create a skill from {source}
>
> The skill should: {description}
>
> Target scope: {target_scope}

skill-creator will:
1. Analyze the repository content
2. Generate an optimized SKILL.md
3. Create any necessary reference files
4. Provide a downloadable skill package

### Why Handoff?

MINE's template-based conversion had low confidence for this source.
skill-creator uses AI-assisted authoring for better results.
"""
