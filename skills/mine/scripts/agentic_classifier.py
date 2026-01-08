#!/usr/bin/env python3
"""
agentic_classifier.py

Classifies discovered files as agentic artifacts with confidence scores.
Deterministic signal-based classification (no ML required).

Part of Agentic Discovery & Conversion
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Signal categories and their confidence contributions
SIGNAL_WEIGHTS = {
    # Markdown signals
    "system_prompt_heading": 0.30,
    "tools_heading": 0.20,
    "agent_heading": 0.25,
    "instructions_keyword": 0.15,
    "prompt_directory": 0.25,
    "agent_directory": 0.25,
    "claude_named_file": 0.30,
    # Framework signals
    "langchain_framework": 0.20,
    "autogen_framework": 0.20,
    "crewai_framework": 0.20,
    "openai_framework": 0.15,
    # Config signals
    "mcp_config": 0.95,
    "tools_schema": 0.40,
    "agent_config": 0.30,
    "llm_config": 0.25,
    # Workflow signals
    "github_actions_workflow": 0.80,
}


class AgenticClassifier:
    """Classifies files as agentic artifacts with confidence scoring."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(f"[AGENTIC-CLASSIFY] {message}", file=sys.stderr)

    def classify(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a candidate file.

        Args:
            candidate: Dictionary with 'path', 'rel_path', 'category', 'size_bytes'

        Returns classification dict:
        {
            'source_path': str,
            'rel_path': str,
            'kind': 'prompt|agent|tooling|workflow|mcp|unknown',
            'signals': List[str],
            'confidence': float (0.0-1.0),
            'title': str,
            'suggested_output': {
                'type': 'skill|command|agent|hook|mcp_fragment|doc_only',
                'name': str
            }
        }
        """
        file_path = candidate["path"]
        if isinstance(file_path, str):
            file_path = Path(file_path)

        category = candidate.get("category", "unknown")
        rel_path = candidate.get("rel_path", str(file_path))

        try:
            content = self._read_file_safe(file_path)
            if not content:
                return self._default_classification(file_path, rel_path)

            # Detect file type and classify
            suffix = file_path.suffix.lower()

            if suffix in (".yml", ".yaml"):
                return self._classify_yaml(file_path, rel_path, content, category)
            elif suffix == ".json":
                return self._classify_json(file_path, rel_path, content, category)
            elif suffix in (".md", ".txt", ""):
                return self._classify_markdown(file_path, rel_path, content, category)
            else:
                return self._default_classification(file_path, rel_path)

        except Exception as e:
            self._log(f"Classification error for {file_path}: {e}")
            return self._default_classification(file_path, rel_path)

    def _read_file_safe(self, file_path: Path, max_bytes: int = 100_000) -> Optional[str]:
        """Safely read file content (up to max_bytes)."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_bytes)
        except (OSError, UnicodeDecodeError):
            return None

    def _classify_markdown(self, file_path: Path, rel_path: str, content: str, category: str) -> Dict[str, Any]:
        """Classify markdown/text files."""
        signals = []
        confidence = 0.0
        kind = "unknown"

        content_lower = content.lower()

        # Signal detection - headings
        if re.search(r"#\s*(system\s+prompt|system\s+message|system\s+instructions)", content_lower):
            signals.append("system_prompt_heading")
            confidence += SIGNAL_WEIGHTS["system_prompt_heading"]

        if re.search(r"#\s*(tools|functions|function\s+calling)", content_lower):
            signals.append("tools_heading")
            confidence += SIGNAL_WEIGHTS["tools_heading"]

        if re.search(r"#\s*(agent|planner|critic|assistant|role)", content_lower):
            signals.append("agent_heading")
            confidence += SIGNAL_WEIGHTS["agent_heading"]

        # Keyword signals
        if re.search(r"\binstructions?:", content_lower):
            signals.append("instructions_keyword")
            confidence += SIGNAL_WEIGHTS["instructions_keyword"]

        # Category bonuses
        if category == "prompt_dirs":
            signals.append("prompt_directory")
            confidence += SIGNAL_WEIGHTS["prompt_directory"]
        elif category == "agent_dirs":
            signals.append("agent_directory")
            confidence += SIGNAL_WEIGHTS["agent_directory"]
        elif category == "root_file":
            if "claude" in file_path.name.lower():
                signals.append("claude_named_file")
                confidence += SIGNAL_WEIGHTS["claude_named_file"]

        # Framework detection
        if "langchain" in content_lower or "langgraph" in content_lower:
            signals.append("langchain_framework")
            confidence += SIGNAL_WEIGHTS["langchain_framework"]
            if kind == "unknown":
                kind = "agent"

        if "autogen" in content_lower:
            signals.append("autogen_framework")
            confidence += SIGNAL_WEIGHTS["autogen_framework"]
            if kind == "unknown":
                kind = "agent"

        if "crewai" in content_lower:
            signals.append("crewai_framework")
            confidence += SIGNAL_WEIGHTS["crewai_framework"]
            if kind == "unknown":
                kind = "agent"

        if "openai" in content_lower and ("api" in content_lower or "gpt" in content_lower):
            signals.append("openai_framework")
            confidence += SIGNAL_WEIGHTS["openai_framework"]

        # Determine kind based on signals
        if kind == "unknown":
            if any(s in signals for s in ["agent_heading", "agent_directory"]):
                kind = "agent"
            elif any(s in signals for s in ["system_prompt_heading", "prompt_directory", "instructions_keyword"]):
                kind = "prompt"
            elif "tools_heading" in signals:
                kind = "tooling"

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        # Suggest output type
        output_type = self._suggest_output_type(kind, confidence, signals)

        return {
            "source_path": str(file_path),
            "rel_path": rel_path,
            "kind": kind,
            "signals": signals,
            "confidence": round(confidence, 2),
            "title": self._extract_title(content, file_path.stem),
            "suggested_output": output_type,
        }

    def _classify_yaml(self, file_path: Path, rel_path: str, content: str, category: str) -> Dict[str, Any]:
        """Classify YAML files (workflows, configs)."""
        signals = []
        confidence = 0.0
        kind = "unknown"

        content_lower = content.lower()

        # GitHub Actions detection
        if "jobs:" in content_lower and ("steps:" in content_lower or "uses:" in content_lower):
            signals.append("github_actions_workflow")
            confidence = SIGNAL_WEIGHTS["github_actions_workflow"]
            kind = "workflow"

        # Agent config detection
        if "agent" in content_lower or "agents" in content_lower:
            signals.append("agent_config")
            confidence += SIGNAL_WEIGHTS["agent_config"]
            if kind == "unknown":
                kind = "agent"

        if "tools" in content_lower or "functions" in content_lower:
            signals.append("tools_schema")
            confidence += SIGNAL_WEIGHTS["tools_schema"]
            if kind == "unknown":
                kind = "tooling"

        # Model configuration
        if "model" in content_lower and ("openai" in content_lower or "anthropic" in content_lower):
            signals.append("llm_config")
            confidence += SIGNAL_WEIGHTS["llm_config"]

        confidence = min(confidence, 1.0)
        output_type = self._suggest_output_type(kind, confidence, signals)

        return {
            "source_path": str(file_path),
            "rel_path": rel_path,
            "kind": kind,
            "signals": signals,
            "confidence": round(confidence, 2),
            "title": file_path.stem,
            "suggested_output": output_type,
        }

    def _classify_json(self, file_path: Path, rel_path: str, content: str, category: str) -> Dict[str, Any]:
        """Classify JSON files (configs, schemas)."""
        signals = []
        confidence = 0.0
        kind = "unknown"

        try:
            data = json.loads(content)

            # MCP server detection
            if isinstance(data, dict):
                if "mcpServers" in data or "mcp_servers" in data:
                    signals.append("mcp_config")
                    confidence = SIGNAL_WEIGHTS["mcp_config"]
                    kind = "mcp"

                # Agent/tool config detection
                if "tools" in data or "functions" in data:
                    signals.append("tools_schema")
                    confidence += SIGNAL_WEIGHTS["tools_schema"]
                    if kind == "unknown":
                        kind = "tooling"

                if "agent" in data or "agents" in data:
                    signals.append("agent_config")
                    confidence += SIGNAL_WEIGHTS["agent_config"]
                    if kind == "unknown":
                        kind = "agent"

                if "model" in data and ("system" in data or "messages" in data):
                    signals.append("llm_config")
                    confidence += SIGNAL_WEIGHTS["llm_config"]
                    if kind == "unknown":
                        kind = "agent"

        except json.JSONDecodeError:
            return self._default_classification(file_path, rel_path)

        confidence = min(confidence, 1.0)
        output_type = self._suggest_output_type(kind, confidence, signals)

        return {
            "source_path": str(file_path),
            "rel_path": rel_path,
            "kind": kind,
            "signals": signals,
            "confidence": round(confidence, 2),
            "title": file_path.stem,
            "suggested_output": output_type,
        }

    def _suggest_output_type(self, kind: str, confidence: float, signals: List[str]) -> Dict[str, str]:
        """Suggest Claude Code output type based on classification."""
        # Below threshold = doc_only
        if confidence < 0.65:
            return {"type": "doc_only", "name": "manual_review"}

        if kind == "prompt":
            return {"type": "command", "name": "generated_command"}
        elif kind == "agent":
            return {"type": "agent", "name": "generated_agent"}
        elif kind == "tooling":
            return {"type": "skill", "name": "generated_skill"}
        elif kind == "workflow":
            return {"type": "command", "name": "generated_runbook"}
        elif kind == "mcp":
            return {"type": "mcp_fragment", "name": "generated_mcp"}
        else:
            return {"type": "doc_only", "name": "manual_review"}

    def _extract_title(self, content: str, fallback: str) -> str:
        """Extract title from content (first heading or fallback)."""
        # Look for first H1 heading
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Remove markdown formatting
            title = re.sub(r"[*_`]", "", title)
            return title[:100]

        # Look for first non-empty line
        for line in content.split("\n")[:10]:
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 5:
                return line[:100]

        return fallback

    def _default_classification(self, file_path: Path, rel_path: str) -> Dict[str, Any]:
        """Return default low-confidence classification."""
        return {
            "source_path": str(file_path),
            "rel_path": rel_path,
            "kind": "unknown",
            "signals": [],
            "confidence": 0.0,
            "title": file_path.stem if isinstance(file_path, Path) else Path(file_path).stem,
            "suggested_output": {"type": "doc_only", "name": "manual_review"},
        }


def classify_candidates(candidates: List[Dict[str, Any]], verbose: bool = False) -> List[Dict[str, Any]]:
    """
    Convenience function to classify a list of candidates.

    Args:
        candidates: List of candidate dictionaries from AgenticDiscoverer
        verbose: Enable verbose logging

    Returns:
        List of classification dictionaries
    """
    classifier = AgenticClassifier(verbose=verbose)
    return [classifier.classify(c) for c in candidates]


def main():
    """CLI entry point for standalone classification."""
    import argparse

    parser = argparse.ArgumentParser(description="Classify agentic candidates")

    parser.add_argument("--file", required=True, help="Path to file to classify")

    parser.add_argument("--category", default="unknown", help="Category hint (prompt_dirs, agent_dirs, etc.)")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    candidate = {
        "path": file_path,
        "rel_path": str(file_path),
        "category": args.category,
        "size_bytes": file_path.stat().st_size,
    }

    classifier = AgenticClassifier(verbose=args.verbose)
    result = classifier.classify(candidate)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
