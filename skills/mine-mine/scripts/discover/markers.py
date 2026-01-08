"""
Marker detection patterns and functions for integration discovery.

Provides pattern definitions and functions for finding integration markers
in Claude Code directories.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# Marker pattern definitions
MARKER_PATTERNS = {
    "settings_import": {
        "pattern": "settings.imported.*.json",
        "extract_name": lambda name: name.replace("settings.imported.", "").replace(".json", ""),
        "type": "settings_import",
    },
    "hooks_import": {
        "pattern": "hooks.imported.*",
        "extract_name": lambda name: name.replace("hooks.imported.", ""),
        "type": "hooks_import",
        "is_directory": True,
    },
    "mcp_import": {
        "pattern": ".mcp.imported.*.json",
        "extract_name": lambda name: name.replace(".mcp.imported.", "").replace(".json", ""),
        "type": "mcp_import",
        "check_parent": True,
    },
    "claude_md_import": {
        "pattern": "CLAUDE.imported.*.md",
        "extract_name": lambda name: name.replace("CLAUDE.imported.", "").replace(".md", ""),
        "type": "claude_md_import",
    },
    "generated_skill": {
        "pattern": "*-workflow",
        "extract_name": lambda name: name.replace("-workflow", ""),
        "type": "generated_skill",
        "is_directory": True,
        "subdir": "skills",
    },
}


def find_markers(claude_dir: Path) -> List[Dict[str, Any]]:
    """
    Find integration markers in a .claude directory.

    Searches for various marker patterns that indicate imported or
    generated Claude Code artifacts.

    Args:
        claude_dir: Path to the .claude directory to scan

    Returns:
        List of marker dictionaries with type, file/dir, and inferred_repo
    """
    markers = []

    # Pattern 1: settings.imported.<name>.json
    for settings_file in claude_dir.glob("settings.imported.*.json"):
        name = settings_file.stem.replace("settings.imported.", "")
        markers.append({"type": "settings_import", "file": str(settings_file), "inferred_repo": name})

    # Pattern 2: hooks.imported.<name>/
    for hooks_dir in claude_dir.glob("hooks.imported.*"):
        if hooks_dir.is_dir():
            name = hooks_dir.name.replace("hooks.imported.", "")
            markers.append({"type": "hooks_import", "dir": str(hooks_dir), "inferred_repo": name})

    # Pattern 3: .mcp.imported.<name>.json (in parent of .claude)
    if claude_dir.name == ".claude":
        parent = claude_dir.parent
        for mcp_file in parent.glob(".mcp.imported.*.json"):
            name = mcp_file.stem.replace(".mcp.imported.", "")
            markers.append({"type": "mcp_import", "file": str(mcp_file), "inferred_repo": name})

    # Pattern 4: CLAUDE.imported.<name>.md
    for claude_md in claude_dir.glob("CLAUDE.imported.*.md"):
        name = claude_md.stem.replace("CLAUDE.imported.", "")
        markers.append({"type": "claude_md_import", "file": str(claude_md), "inferred_repo": name})

    # Pattern 5: skills/<name>-workflow/ (generated packs)
    skills_dir = claude_dir / "skills"
    if skills_dir.exists():
        for skill_dir in skills_dir.glob("*-workflow"):
            if skill_dir.is_dir():
                name = skill_dir.name.replace("-workflow", "")
                markers.append({"type": "generated_skill", "dir": str(skill_dir), "inferred_repo": name})

    # Pattern 6: .provenance/<n>.json (from mine imports)
    provenance_markers = find_provenance_markers(claude_dir)
    markers.extend(provenance_markers)

    return markers


def find_provenance_markers(claude_dir: Path) -> List[Dict[str, Any]]:
    """
    Find provenance markers in both user and project scope locations.

    Provenance files track the source of imported artifacts and are
    deduplicated by repo_id, keeping the newest import.

    Args:
        claude_dir: Path to the .claude directory

    Returns:
        List of provenance marker dictionaries
    """
    provenance_locations = []

    if claude_dir.name == ".claude":
        # User scope: ~/.claude/mine/.provenance/
        user_prov = claude_dir / "mine" / ".provenance"
        if user_prov.exists():
            provenance_locations.append(user_prov)

        # Project scope: .claude/.provenance/
        project_prov = claude_dir / ".provenance"
        if project_prov.exists():
            provenance_locations.append(project_prov)

    # Deduplicate provenance by repo_id, keeping newest (by import_time)
    provenance_by_repo: Dict[str, Dict[str, Any]] = {}

    for provenance_dir in provenance_locations:
        for prov_file in provenance_dir.glob("*.json"):
            marker = parse_provenance_file(prov_file)
            if marker:
                repo_id = marker.get("inferred_repo", prov_file.stem)
                import_time = marker.get("import_time", "")

                # Keep newest provenance per repo_id
                if repo_id in provenance_by_repo:
                    existing_time = provenance_by_repo[repo_id].get("import_time", "")
                    if import_time > existing_time:
                        provenance_by_repo[repo_id] = marker
                else:
                    provenance_by_repo[repo_id] = marker

    return list(provenance_by_repo.values())


def parse_provenance_file(prov_file: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a provenance JSON file and extract marker information.

    Args:
        prov_file: Path to the provenance file

    Returns:
        Marker dictionary or None if parsing fails
    """
    try:
        with open(prov_file, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            repo_id = data.get("repo_id", prov_file.stem)
            return {
                "type": "provenance",
                "file": str(prov_file),
                "source_url": data.get("source_url"),
                "source_path": data.get("source_path"),
                "import_commit": data.get("import_commit"),
                "import_scope": data.get("import_scope"),
                "import_time": data.get("import_time", ""),
                "artifact_mappings": data.get("artifact_mappings", []),
                "inferred_repo": repo_id,
            }
    except (json.JSONDecodeError, IOError):
        return None


def infer_repo_name(markers: List[Dict[str, Any]]) -> str:
    """
    Infer repository name from a list of markers.

    Counts occurrences of each inferred repo name and returns
    the most common one.

    Args:
        markers: List of marker dictionaries

    Returns:
        Most common inferred repository name, or "unknown"
    """
    names: Dict[str, int] = {}
    for marker in markers:
        name = marker.get("inferred_repo", "unknown")
        names[name] = names.get(name, 0) + 1

    if names:
        return max(names.items(), key=lambda x: x[1])[0]

    return "unknown"


def group_markers_by_repo(markers: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group markers by their inferred repository name.

    Args:
        markers: List of marker dictionaries

    Returns:
        Dictionary mapping repo names to lists of markers
    """
    repo_groups: Dict[str, List[Dict[str, Any]]] = {}

    for marker in markers:
        if marker["type"] == "provenance":
            repo_id = marker.get("inferred_repo", "unknown")
        else:
            repo_id = marker.get("inferred_repo", "misc")

        if repo_id not in repo_groups:
            repo_groups[repo_id] = []
        repo_groups[repo_id].append(marker)

    return repo_groups
