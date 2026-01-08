#!/usr/bin/env python3
"""
convert_framework.py - Convert AI framework artifacts to Claude Code format

Converts patterns, agents, and workflows from frameworks like Fabric, LangChain,
and AutoGen into Claude Code-compatible skills, commands, and agents.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import _init_shared
from safe_io import safe_write_text
from cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run


class FrameworkConverter:
    """Converts AI framework artifacts to Claude Code format."""

    def __init__(
        self,
        framework_type: str,
        source_path: Path,
        output_dir: Path,
        dry_run: bool = True,
        overwrite: bool = False,
        verbose: bool = False,
    ):
        self.framework_type = framework_type
        self.source_path = source_path
        self.output_dir = output_dir
        self.dry_run = dry_run
        self.overwrite = overwrite
        self.verbose = verbose
        self.conversions = []

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[CONVERT] {message}", file=sys.stderr)

    def convert(self) -> int:
        """Convert framework artifacts to Claude Code format."""
        print(f"Converting {self.framework_type} framework to Claude Code...")
        print(f"Source: {self.source_path}")
        print(f"Output: {self.output_dir}")
        print()

        # Check for conflicts
        conflicts = self._detect_conversion_conflicts()
        if conflicts:
            print("⚠ WARNING: Existing Claude artifacts detected:")
            for conflict in conflicts:
                print(f"  - {conflict}")

            if not self.overwrite:
                print("\nConversion will skip conflicting files.")
                print("Use --overwrite to replace existing artifacts.")

        if self.dry_run:
            print("=== DRY-RUN MODE ===")
            print("No files will be written. Use --dry-run=false to execute.")
            print()

        # Dispatch to framework-specific converter
        if self.framework_type == "fabric":
            return self._convert_fabric()
        elif self.framework_type == "langchain":
            return self._convert_langchain()
        elif self.framework_type == "autogen":
            return self._convert_autogen()
        else:
            print(f"Error: Unknown framework type: {self.framework_type}")
            return 1

    def _detect_conversion_conflicts(self) -> List[str]:
        """Detect existing Claude artifacts that conversion would overwrite."""
        conflicts = []
        if self.framework_type == "fabric":
            patterns_dir = self.source_path / "patterns"
            if patterns_dir.exists():
                for pattern_dir in patterns_dir.iterdir():
                    if not pattern_dir.is_dir():
                        continue

                    pattern_name = pattern_dir.name
                    # Read system.md for classification (simplified)
                    system_md = pattern_dir / "system.md"
                    content = ""
                    if system_md.exists():
                        try:
                            with open(system_md, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read(1000)
                        except (OSError, UnicodeError):
                            pass

                    artifact_type = self._classify_fabric_pattern_type(pattern_name, content)

                    potential_dest = None
                    if artifact_type == "agent":
                        potential_dest = self.output_dir / "agents" / f"{pattern_name}.md"
                    elif artifact_type == "command":
                        potential_dest = self.output_dir / "commands" / f"{pattern_name}.md"
                    else:
                        potential_dest = self.output_dir / "skills" / f"{pattern_name}-pattern"

                    if potential_dest and potential_dest.exists():
                        conflicts.append(str(potential_dest))

        return conflicts

    def _convert_fabric(self) -> int:
        """Convert Fabric patterns to Claude Code artifacts."""
        patterns_dir = self.source_path / "patterns"

        if not patterns_dir.exists():
            print(f"Error: Patterns directory not found: {patterns_dir}")
            return 1

        self._log(f"Scanning Fabric patterns in {patterns_dir}")

        # Count patterns
        pattern_dirs = [d for d in patterns_dir.iterdir() if d.is_dir()]
        print(f"Found {len(pattern_dirs)} Fabric patterns to convert")
        print()

        # Convert each pattern
        for pattern_dir in pattern_dirs:
            self._convert_fabric_pattern(pattern_dir)

        # Print summary
        print()
        print(f"Conversion complete: {len(self.conversions)} patterns converted")

        if not self.dry_run:
            print(f"✓ Artifacts written to {self.output_dir}")
        else:
            print("To execute conversion, run with: --dry-run=false")

        return 0

    def _convert_fabric_pattern(self, pattern_dir: Path):
        """Convert a single Fabric pattern to Claude Code format."""
        pattern_name = pattern_dir.name

        # Read system.md and user.md
        system_md = pattern_dir / "system.md"
        user_md = pattern_dir / "user.md"

        if not system_md.exists():
            self._log(f"Skipping {pattern_name}: no system.md")
            return

        # Read pattern content
        with open(system_md, "r", encoding="utf-8", errors="replace") as f:
            system_content = f.read()

        user_content = ""
        if user_md.exists():
            with open(user_md, "r", encoding="utf-8", errors="replace") as f:
                user_content = f.read()

        # Classify pattern type
        artifact_type = self._classify_fabric_pattern_type(pattern_name, system_content)

        # Convert to Claude Code format
        if artifact_type == "agent":
            claude_content = self._fabric_to_agent(pattern_name, system_content, user_content)
            output_file = self.output_dir / "agents" / f"{pattern_name}.md"
        elif artifact_type == "command":
            claude_content = self._fabric_to_command(pattern_name, system_content, user_content)
            output_file = self.output_dir / "commands" / f"{pattern_name}.md"
        else:  # skill
            claude_content = self._fabric_to_skill(pattern_name, system_content, user_content)
            output_file = self.output_dir / "skills" / f"{pattern_name}-pattern"

        # Record conversion
        self.conversions.append({"source": str(pattern_dir), "destination": str(output_file), "type": artifact_type})

        # Check overwrite
        if output_file.exists() and not self.overwrite:
            print(f"[SKIP] {output_file} (exists)")
            return

        print(f"[CONVERT] {pattern_name} → {artifact_type}: {output_file}")

        # Write file if not dry-run
        if not self.dry_run:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if artifact_type == "skill":
                # Skills need a SKILL.md file
                skill_file = output_file / "SKILL.md"
                skill_file.parent.mkdir(parents=True, exist_ok=True)
                if not safe_write_text(skill_file, claude_content):
                    print(f"[ERROR] Failed to write {skill_file}")
            else:
                if not safe_write_text(output_file, claude_content):
                    print(f"[ERROR] Failed to write {output_file}")

    def _classify_fabric_pattern_type(self, pattern_name: str, content: str) -> str:
        """Classify Fabric pattern into Claude Code artifact type."""
        pattern_lower = pattern_name.lower()
        content_lower = content[:1000].lower()

        # Agent indicators: complex analysis, multi-step reasoning
        agent_indicators = [
            "analyze",
            "review",
            "evaluate",
            "assess",
            "expert",
            "step by step",
            "first,",
            "second,",
            "then,",
            "finally,",
        ]

        if any(ind in pattern_lower or ind in content_lower for ind in agent_indicators):
            if len(content) > 500:  # Agents tend to be longer
                return "agent"

        # Command indicators: simple, action-oriented
        command_indicators = ["extract", "summarize", "create", "generate", "improve", "write", "list"]

        if any(ind in pattern_lower for ind in command_indicators):
            return "command"

        # Default to command for shorter patterns, skill for complex ones
        return "command" if len(content) < 1000 else "agent"

    def _fabric_to_agent(self, name: str, system_content: str, user_content: str) -> str:
        """Convert Fabric pattern to Claude Code agent format."""

        # Extract description from system content
        description = self._extract_description(system_content)

        # Build agent markdown
        agent_md = f"""---
name: {name}
description: {description}
---

# {name.replace("_", " ").replace("-", " ").title()}

{system_content}

"""

        if user_content:
            agent_md += f"""
## Usage Instructions

{user_content}
"""

        agent_md += """
## Notes

This agent was automatically converted from a Fabric pattern.
Original source: Fabric framework pattern repository.
"""

        return agent_md

    def _fabric_to_command(self, name: str, system_content: str, user_content: str) -> str:
        """Convert Fabric pattern to Claude Code command format."""

        description = self._extract_description(system_content)

        command_md = f"""---
name: {name}
description: {description}
---

# {name.replace("_", " ").replace("-", " ").title()}

## What This Command Does

{system_content}

## Usage

Simply say "{name.replace("_", " ").replace("-", " ")}" or describe your task.

"""

        if user_content:
            command_md += f"""## Additional Context

{user_content}

"""

        command_md += """## Notes

Converted from Fabric pattern.
"""

        return command_md

    def _fabric_to_skill(self, name: str, system_content: str, user_content: str) -> str:
        """Convert Fabric pattern to Claude Code skill format."""

        description = self._extract_description(system_content)

        skill_md = f"""---
name: {name}-pattern
description: {description}. Fabric pattern converted to Claude Code skill.
---

# {name.replace("_", " ").replace("-", " ").title()} Pattern

## Overview

This skill implements the {name} pattern from the Fabric framework.

## Pattern Instructions

{system_content}

"""

        if user_content:
            skill_md += f"""
## Usage Guidelines

{user_content}

"""

        skill_md += """
## Conversion Notes

This skill was automatically converted from a Fabric pattern.
The original pattern's logic and instructions have been preserved.

"""

        return skill_md

    def _extract_description(self, content: str) -> str:
        """Extract a concise description from pattern content."""
        lines = content.split("\n")

        # Look for first meaningful paragraph
        for line in lines[:10]:
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 20:
                # Truncate to reasonable length
                if len(line) > 150:
                    return line[:147] + "..."
                return line

        # Fallback: use first line
        return lines[0][:150] if lines else "Converted Fabric pattern"

    def _convert_langchain(self) -> int:
        """Convert LangChain project to Claude Code scaffolds."""
        print("Analyzing LangChain project...")

        # Detect LangChain files
        langchain_files = self._detect_langchain_files()

        if not langchain_files:
            print("No LangChain files detected.")
            print("Looking for: chains/*.py, agents/*.py, langchain imports")
            return 1

        print(f"Found {len(langchain_files)} LangChain-related files")
        print()

        # Generate run command
        run_command = self._generate_langchain_run_command(langchain_files)
        run_cmd_path = self.output_dir / "commands" / "run-langchain.md"

        # Generate assistant agent
        assistant_agent = self._generate_langchain_assistant(langchain_files)
        agent_path = self.output_dir / "agents" / "langchain-assistant.md"

        # Generate conversion report
        report = self._generate_langchain_report(langchain_files)
        report_path = self.output_dir / "skills" / "langchain-project" / "SKILL.md"

        self.conversions.extend(
            [
                {"source": str(self.source_path), "destination": str(run_cmd_path), "type": "command"},
                {"source": str(self.source_path), "destination": str(agent_path), "type": "agent"},
                {"source": str(self.source_path), "destination": str(report_path), "type": "skill"},
            ]
        )

        print("[CONVERT] LangChain project → run-langchain.md (command)")
        print("[CONVERT] LangChain project → langchain-assistant.md (agent)")
        print("[CONVERT] LangChain project → langchain-project/SKILL.md (skill)")

        if not self.dry_run:
            run_cmd_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(run_cmd_path, run_command)

            agent_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(agent_path, assistant_agent)

            report_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(report_path, report)

            print(f"\n✓ Scaffold written to {self.output_dir}")
        else:
            print("\nTo execute conversion, run with: --dry-run=false")

        return 0

    def _detect_langchain_files(self) -> List[Path]:
        """Detect LangChain-related Python files."""
        langchain_files = []

        for py_file in self.source_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                if any(
                    imp in content
                    for imp in [
                        "from langchain",
                        "import langchain",
                        "from langgraph",
                        "import langgraph",
                        "ChatOpenAI",
                        "LLMChain",
                        "AgentExecutor",
                    ]
                ):
                    langchain_files.append(py_file)
            except OSError:
                continue

        return langchain_files

    def _generate_langchain_run_command(self, files: List[Path]) -> str:
        """Generate a run command for LangChain project."""
        main_files = [f for f in files if f.stem in ("main", "app", "run", "cli")]
        entry_point = main_files[0] if main_files else (files[0] if files else Path("main.py"))
        rel_entry = entry_point.relative_to(self.source_path) if entry_point.is_absolute() else entry_point

        return f"""---
name: run-langchain
description: Run the LangChain application from this project
---

# Run LangChain Application

This command runs the LangChain project.

## Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
# or
pip install langchain langchain-openai langgraph
```

## Running

```bash
python {rel_entry}
```

## Environment Variables

Ensure these are set:
- `OPENAI_API_KEY` - Your OpenAI API key (if using OpenAI)
- `ANTHROPIC_API_KEY` - Your Anthropic API key (if using Claude)

## Entry Points

Detected entry points in this project:
{chr(10).join(f"- `{f.relative_to(self.source_path)}`" for f in files[:5])}

## Notes

Scaffolded from LangChain project by mine.
Review and customize the run command for your specific setup.
"""

    def _generate_langchain_assistant(self, files: List[Path]) -> str:
        """Generate an assistant agent for working with LangChain code."""
        return f"""---
name: langchain-assistant
description: Expert assistant for working with this LangChain project
---

# LangChain Project Assistant

I am an assistant specialized in working with this LangChain project.

## My Capabilities

1. **Code Navigation** - I understand the project structure and can help navigate chains, agents, and tools
2. **Debugging** - I can help debug LangChain execution flows and trace issues
3. **Extension** - I can help add new chains, tools, or agents to the project
4. **Best Practices** - I know LangChain best practices and can suggest improvements

## Project Structure

This project contains {len(files)} LangChain-related files:
{chr(10).join(f"- `{f.relative_to(self.source_path)}`" for f in files[:10])}

## How to Use Me

Ask me to:
- Explain how a specific chain works
- Add a new tool to an agent
- Debug why output isn't as expected
- Optimize prompt templates
- Migrate to newer LangChain patterns

## Notes

Generated by mine from LangChain project analysis.
Customize this agent's instructions based on your specific needs.
"""

    def _generate_langchain_report(self, files: List[Path]) -> str:
        """Generate a skill with conversion report for LangChain project."""
        return f"""---
name: langchain-project
description: Documentation and workflow for this LangChain project
---

# LangChain Project

## Overview

This skill provides context for working with the LangChain codebase.

## Detected Components

**{len(files)} LangChain files found:**

{chr(10).join(f"- [{f.stem}]({f.relative_to(self.source_path)})" for f in files[:15])}

## Conversion Report

| Component | Status | Notes |
|-----------|--------|-------|
| Chains | Scaffolded | Entry points detected |
| Agents | Scaffolded | Assistant agent generated |
| Tools | Review needed | Inspect for custom tools |
| Memory | Review needed | Check memory configuration |

## Generated Artifacts

- `commands/run-langchain.md` - Run command
- `agents/langchain-assistant.md` - Project assistant

## Next Steps

1. Review generated scaffolds
2. Customize run commands for your environment
3. Add project-specific context to the assistant
4. Consider adding tool-specific commands

---

*Generated by mine on {datetime.now().strftime("%Y-%m-%d")}*
"""

    def _convert_autogen(self) -> int:
        """Convert AutoGen project to Claude Code scaffolds."""
        print("Analyzing AutoGen project...")

        # Detect AutoGen files
        autogen_files = self._detect_autogen_files()

        if not autogen_files:
            print("No AutoGen files detected.")
            print("Looking for: autogen imports, AssistantAgent, UserProxyAgent")
            return 1

        print(f"Found {len(autogen_files)} AutoGen-related files")
        print()

        # Generate run command
        run_command = self._generate_autogen_run_command(autogen_files)
        run_cmd_path = self.output_dir / "commands" / "run-autogen.md"

        # Generate coordinator agent
        coordinator = self._generate_autogen_coordinator(autogen_files)
        agent_path = self.output_dir / "agents" / "autogen-coordinator.md"

        # Generate conversion report
        report = self._generate_autogen_report(autogen_files)
        report_path = self.output_dir / "skills" / "autogen-project" / "SKILL.md"

        self.conversions.extend(
            [
                {"source": str(self.source_path), "destination": str(run_cmd_path), "type": "command"},
                {"source": str(self.source_path), "destination": str(agent_path), "type": "agent"},
                {"source": str(self.source_path), "destination": str(report_path), "type": "skill"},
            ]
        )

        print("[CONVERT] AutoGen project → run-autogen.md (command)")
        print("[CONVERT] AutoGen project → autogen-coordinator.md (agent)")
        print("[CONVERT] AutoGen project → autogen-project/SKILL.md (skill)")

        if not self.dry_run:
            run_cmd_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(run_cmd_path, run_command)

            agent_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(agent_path, coordinator)

            report_path.parent.mkdir(parents=True, exist_ok=True)
            safe_write_text(report_path, report)

            print(f"\n✓ Scaffold written to {self.output_dir}")
        else:
            print("\nTo execute conversion, run with: --dry-run=false")

        return 0

    def _detect_autogen_files(self) -> List[Path]:
        """Detect AutoGen-related Python files."""
        autogen_files = []

        for py_file in self.source_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                if any(
                    imp in content
                    for imp in [
                        "from autogen",
                        "import autogen",
                        "AssistantAgent",
                        "UserProxyAgent",
                        "ConversableAgent",
                        "GroupChat",
                    ]
                ):
                    autogen_files.append(py_file)
            except OSError:
                continue

        return autogen_files

    def _generate_autogen_run_command(self, files: List[Path]) -> str:
        """Generate a run command for AutoGen project."""
        main_files = [f for f in files if f.stem in ("main", "app", "run", "cli")]
        entry_point = main_files[0] if main_files else (files[0] if files else Path("main.py"))
        rel_entry = entry_point.relative_to(self.source_path) if entry_point.is_absolute() else entry_point

        return f"""---
name: run-autogen
description: Run the AutoGen multi-agent application from this project
---

# Run AutoGen Application

This command runs the AutoGen multi-agent project.

## Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
# or
pip install pyautogen
```

## Running

```bash
python {rel_entry}
```

## Environment Variables

Ensure these are set:
- `OPENAI_API_KEY` - Your OpenAI API key
- `OAI_CONFIG_LIST` - Path to config list JSON (if using)

## Entry Points

Detected entry points in this project:
{chr(10).join(f"- `{f.relative_to(self.source_path)}`" for f in files[:5])}

## Notes

Scaffolded from AutoGen project by mine.
Review and customize for your specific multi-agent setup.
"""

    def _generate_autogen_coordinator(self, files: List[Path]) -> str:
        """Generate a coordinator agent for working with AutoGen code."""
        return f"""---
name: autogen-coordinator
description: Expert coordinator for working with this AutoGen multi-agent project
---

# AutoGen Project Coordinator

I am a coordinator specialized in managing this AutoGen multi-agent project.

## My Capabilities

1. **Agent Management** - I understand the agent topology and can help manage interactions
2. **Configuration** - I can help configure agent models, prompts, and behaviors
3. **Debugging** - I can trace multi-agent conversations and identify issues
4. **Extension** - I can help add new agents or modify group chat dynamics

## Project Structure

This project contains {len(files)} AutoGen-related files:
{chr(10).join(f"- `{f.relative_to(self.source_path)}`" for f in files[:10])}

## How to Use Me

Ask me to:
- Explain the agent interaction flow
- Add a new specialized agent
- Debug conversation loops
- Optimize agent configurations
- Implement custom reply functions

## Notes

Generated by mine from AutoGen project analysis.
Customize based on your multi-agent architecture.
"""

    def _generate_autogen_report(self, files: List[Path]) -> str:
        """Generate a skill with conversion report for AutoGen project."""
        return f"""---
name: autogen-project
description: Documentation and workflow for this AutoGen multi-agent project
---

# AutoGen Multi-Agent Project

## Overview

This skill provides context for working with the AutoGen codebase.

## Detected Components

**{len(files)} AutoGen files found:**

{chr(10).join(f"- [{f.stem}]({f.relative_to(self.source_path)})" for f in files[:15])}

## Conversion Report

| Component | Status | Notes |
|-----------|--------|-------|
| Agents | Scaffolded | Agent definitions detected |
| GroupChat | Review needed | Check group configurations |
| Tools | Review needed | Inspect function calling |
| Config | Review needed | Verify OAI config |

## Generated Artifacts

- `commands/run-autogen.md` - Run command
- `agents/autogen-coordinator.md` - Project coordinator

## Next Steps

1. Review generated scaffolds  
2. Map your agent hierarchy
3. Add agent-specific commands if needed
4. Configure model settings

---

*Generated by mine on {datetime.now().strftime("%Y-%m-%d")}*
"""


def main():
    parser = argparse.ArgumentParser(
        description="Convert AI framework artifacts to Claude Code format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert Fabric patterns (dry-run)
  %(prog)s --framework fabric --source /path/to/fabric --output ~/.claude

  # Actually convert
  %(prog)s --framework fabric --source /path/to/fabric --output ~/.claude --dry-run=false
  
  # Convert to project scope
  %(prog)s --framework fabric --source /path/to/fabric --output ./.claude --dry-run=false
        """,
    )

    parser.add_argument(
        "--framework", required=True, choices=["fabric", "langchain", "autogen"], help="Framework type to convert from"
    )

    parser.add_argument("--source", required=True, help="Path to framework repository or patterns directory")

    parser.add_argument("--output", required=True, help="Output directory for converted Claude Code artifacts")

    # Add standardized dry-run and apply arguments
    add_dry_run_argument(parser, help_text="Preview conversion without writing (default: true)")
    add_apply_argument(parser)

    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing artifacts")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Resolve effective dry-run state (--apply overrides --dry-run)
    effective_dry_run = resolve_dry_run(args)

    try:
        converter = FrameworkConverter(
            framework_type=args.framework,
            source_path=Path(args.source),
            output_dir=Path(args.output),
            dry_run=effective_dry_run,
            overwrite=args.overwrite,
            verbose=args.verbose,
        )

        return converter.convert()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
