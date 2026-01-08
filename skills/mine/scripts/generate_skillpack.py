#!/usr/bin/env python3
"""
generate_skillpack.py - Generate Claude skill packs from repository workflows

Analyzes repositories without Claude artifacts and generates new skill packs
based on build systems, documentation, and common workflow patterns.
"""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

import _init_shared
from safe_io import safe_write_text
from cli_helpers import add_dry_run_argument, add_apply_argument, resolve_dry_run


def create_reproducible_zip(output_path: Path, source_dir: Path):
    """Create a reproducible zip archive of a directory.

    Ensures deterministic output by:
    1. Sorting files by name
    2. Using a fixed timestamp (2025-01-01)
    3. Setting consistent permissions
    """
    # Fixed timestamp: 2025-01-01 00:00:00
    substantive_timestamp = (2025, 1, 1, 0, 0, 0)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            # Sort files for deterministic order
            files.sort()

            for filename in files:
                file_path = Path(root) / filename
                arcname = file_path.relative_to(source_dir)

                # Create ZipInfo with fixed timestamp
                zinfo = zipfile.ZipInfo(str(arcname), substantive_timestamp)

                # Set permissions (normalize to 644 or 755)
                # Include file type bits (S_IFREG = 0o100000) for compatibility
                REG_FILE = 0o100000
                st = os.stat(file_path)
                mode = st.st_mode

                perm = 0o755 if (mode & stat.S_IXUSR) else 0o644
                zinfo.external_attr = ((REG_FILE | perm) & 0xFFFF) << 16

                # Write file content
                with open(file_path, "rb") as f:
                    zf.writestr(zinfo, f.read())


class SkillpackGenerator:
    """Generates skill packs from repository analysis."""

    def __init__(
        self,
        source: str,
        target_dir: str,
        repo_name: Optional[str] = None,
        dry_run: bool = True,
        verbose: bool = False,
        output_zip: Optional[str] = None,
    ):
        self.source = source
        self.target_dir = Path(target_dir)
        self.repo_name = repo_name or self.target_dir.name
        self.dry_run = dry_run
        self.verbose = verbose
        self.output_zip = output_zip
        self.repo_path: Optional[Path] = None
        self.temp_dir: Optional[str] = None

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[GENERATE] {message}", file=sys.stderr)

    def _clone_repo(self) -> Path:
        """Clone or access repository.

        Uses centralized clone helper with secure GIT_ASKPASS authentication.
        """
        if not self.source.startswith("http"):
            self._log(f"Using local path: {self.source}")
            return Path(self.source).resolve()

        # Import secure helpers
        try:
            from url_utils import clone_with_auth_fallback, redact_url_credentials
        except ImportError:
            redact_url_credentials = lambda x: x
            clone_with_auth_fallback = None

        self.temp_dir = tempfile.mkdtemp(prefix="claude-skillgen-")
        dest = Path(self.temp_dir) / "repo"

        self._log(f"Cloning {redact_url_credentials(self.source)}")

        # Use centralized clone helper (handles gh CLI, askpass, and plain git fallback)
        if clone_with_auth_fallback is not None:
            if clone_with_auth_fallback(self.source, dest, depth=1, verbose=self.verbose):
                return dest

        # Ultimate fallback: plain git clone (no auth)
        subprocess.run(["git", "clone", "--depth", "1", self.source, str(dest)], check=True, capture_output=True)
        return dest

    def generate(self) -> int:
        """Generate skill pack from repository analysis."""
        try:
            self.repo_path = self._clone_repo()

            print(f"Generating skill pack: {self.repo_name}-workflow")
            print(f"Target directory: {self.target_dir}")
            if self.output_zip:
                print(f"Output archive: {self.output_zip}")
            print()

            # Analyze repository
            analysis = self._analyze_repo()

            # Generate SKILL.md
            skill_md = self._generate_skill_md(analysis)

            # Generate REFERENCE.md if needed
            reference_md = self._generate_reference_md(analysis)

            # Generate commands if applicable
            commands = self._generate_commands(analysis)

            # Print what will be created
            print("Will create:")
            print(f"  {self.target_dir}/SKILL.md")
            if reference_md:
                print(f"  {self.target_dir}/references/REFERENCE.md")
            for cmd_name in commands:
                scope_dir = "~/.claude/commands" if self.dry_run else ".claude/commands"
                print(f"  {scope_dir}/{cmd_name}.md")
            print()

            # Execute if not dry-run
            if not self.dry_run:
                self._write_skill_pack(skill_md, reference_md, commands)
                print("✓ Skill pack generated successfully")

                if self.output_zip:
                    print(f"Creating reproducible archive: {self.output_zip}...")
                    create_reproducible_zip(Path(self.output_zip), self.target_dir)
                    print("✓ Zip archive created")

                print()
                print("To use: Restart Claude Code and the skill will be available")
            else:
                print("To execute, run with: --dry-run=false")

            return 0

        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _analyze_repo(self) -> Dict[str, Any]:
        """Analyze repository structure and extract metadata."""
        analysis = {
            "name": self.repo_name,
            "description": "",
            "language": None,
            "build_system": None,
            "tasks": {},
            "dependencies": [],
            "readme_content": "",
            "has_docs": False,
            "context7_enabled": False,
        }

        # Read README
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = self.repo_path / readme_name
            if readme_path.exists():
                try:
                    with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                        analysis["readme_content"] = f.read()
                    # Extract first paragraph as description
                    lines = analysis["readme_content"].split("\n")
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            analysis["description"] = line[:200]
                            break
                except (OSError, UnicodeError):
                    pass
                break

        # Check for docs directory
        analysis["has_docs"] = (self.repo_path / "docs").exists()

        # Detect Context7 MCP configuration
        analysis["context7_enabled"] = self._detect_context7()

        # Detect language and build system
        self._detect_python(analysis)
        self._detect_javascript(analysis)
        self._detect_rust(analysis)
        self._detect_go(analysis)
        self._detect_makefile(analysis)

        return analysis

    def _detect_context7(self) -> bool:
        """
        Detect if Context7 MCP is configured in the repository or user config.

        Looks for 'context7' key in any .mcp*.json file.
        """
        if not self.repo_path:
            return False

        try:
            # Check .mcp.json and .mcp*.json files in repo
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

    def _detect_python(self, analysis: Dict[str, Any]):
        """Detect Python project and extract tasks."""
        pyproject = self.repo_path / "pyproject.toml"
        setup_py = self.repo_path / "setup.py"
        requirements = self.repo_path / "requirements.txt"

        if pyproject.exists():
            analysis["language"] = "Python"
            analysis["build_system"] = "pyproject.toml"

            try:
                with open(pyproject, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Extract scripts/tasks
                if "[project.scripts]" in content or "[tool.poetry.scripts]" in content:
                    analysis["tasks"]["run"] = "See scripts in pyproject.toml"

                # Common Python tasks
                analysis["tasks"]["test"] = "pytest"
                analysis["tasks"]["lint"] = "ruff check . or flake8 ."
                analysis["tasks"]["format"] = "black . or ruff format ."

                # Extract dependencies
                deps_match = re.findall(r'"([a-zA-Z0-9_-]+)[>=<]', content)
                analysis["dependencies"] = list(set(deps_match))[:10]

            except (OSError, UnicodeError):
                pass

        elif setup_py.exists():
            analysis["language"] = "Python"
            analysis["build_system"] = "setup.py"
            analysis["tasks"]["install"] = "pip install -e ."
            analysis["tasks"]["test"] = "python setup.py test"

        elif requirements.exists():
            analysis["language"] = "Python"
            analysis["tasks"]["install"] = "pip install -r requirements.txt"

    def _detect_javascript(self, analysis: Dict[str, Any]):
        """Detect JavaScript/Node project and extract tasks."""
        package_json = self.repo_path / "package.json"

        if package_json.exists():
            analysis["language"] = "JavaScript/TypeScript"
            analysis["build_system"] = "npm/yarn"

            try:
                with open(package_json, "r", encoding="utf-8", errors="replace") as f:
                    pkg = json.load(f)

                # Extract scripts
                scripts = pkg.get("scripts", {})
                for script_name in ["build", "test", "lint", "dev", "start"]:
                    if script_name in scripts:
                        analysis["tasks"][script_name] = f"npm run {script_name}"

                # Extract dependencies
                deps = list(pkg.get("dependencies", {}).keys())
                dev_deps = list(pkg.get("devDependencies", {}).keys())
                analysis["dependencies"] = (deps + dev_deps)[:10]

            except Exception:
                pass

    def _detect_rust(self, analysis: Dict[str, Any]):
        """Detect Rust project and extract tasks."""
        cargo_toml = self.repo_path / "Cargo.toml"

        if cargo_toml.exists():
            analysis["language"] = "Rust"
            analysis["build_system"] = "Cargo"
            analysis["tasks"]["build"] = "cargo build --release"
            analysis["tasks"]["test"] = "cargo test"
            analysis["tasks"]["lint"] = "cargo clippy"
            analysis["tasks"]["run"] = "cargo run"

    def _detect_go(self, analysis: Dict[str, Any]):
        """Detect Go project and extract tasks."""
        go_mod = self.repo_path / "go.mod"

        if go_mod.exists():
            analysis["language"] = "Go"
            analysis["build_system"] = "go modules"
            analysis["tasks"]["build"] = "go build"
            analysis["tasks"]["test"] = "go test ./..."
            analysis["tasks"]["run"] = "go run ."

    def _detect_makefile(self, analysis: Dict[str, Any]):
        """Detect Makefile and extract tasks."""
        makefile = self.repo_path / "Makefile"

        if makefile.exists():
            if not analysis["build_system"]:
                analysis["build_system"] = "Make"

            try:
                with open(makefile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Extract targets
                targets = re.findall(r"^([a-zA-Z0-9_-]+):", content, re.MULTILINE)
                for target in ["build", "test", "clean", "install", "lint"]:
                    if target in targets:
                        analysis["tasks"][target] = f"make {target}"
            except (OSError, UnicodeError):
                pass

    def _generate_skill_md(self, analysis: Dict[str, Any]) -> str:
        """Generate SKILL.md content."""
        description = analysis["description"] or f"Workflow automation for {analysis['name']}"

        # Build tasks section
        tasks_section = ""
        if analysis["tasks"]:
            tasks_section = "## Common Tasks\n\n"
            for task_name, task_cmd in analysis["tasks"].items():
                tasks_section += f"### {task_name.title()}\n\n"
                tasks_section += f"```bash\n{task_cmd}\n```\n\n"

        # Build dependencies section
        deps_section = ""
        if analysis["dependencies"]:
            deps_section = "## Key Dependencies\n\n"
            for dep in analysis["dependencies"][:5]:
                deps_section += f"- `{dep}`\n"
            deps_section += "\n"

        # Build documentation section
        docs_section = ""
        if analysis["has_docs"]:
            docs_section = "## Documentation\n\nSee the `docs/` directory for detailed documentation.\n\n"

        skill_md = f"""---
name: {analysis["name"]}-workflow
description: Workflow automation for {analysis["name"]}. {description[:150]}. Use when working with this repository, running builds, tests, or deployments.
---

# {analysis["name"].replace("-", " ").title()} Workflow

## Overview

{description}

## Quick Start

"""

        # Add language-specific quick start
        if analysis["language"] == "Python":
            skill_md += """**Python Project Setup:**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
"""
            if "pyproject.toml" in analysis.get("build_system", ""):
                skill_md += "pip install -e .\n"
            else:
                skill_md += "pip install -r requirements.txt\n"
            skill_md += "```\n\n"

        elif analysis["language"] == "JavaScript/TypeScript":
            skill_md += """**Node.js Project Setup:**
```bash
# Install dependencies
npm install  # or: yarn install

# Run development server (if applicable)
npm run dev
```\n\n"""

        elif analysis["language"] == "Rust":
            skill_md += """**Rust Project Setup:**
```bash
# Build project
cargo build --release

# Run tests
cargo test
```\n\n"""

        skill_md += tasks_section
        skill_md += deps_section
        skill_md += docs_section

        # Add Context7 hint if enabled
        if analysis.get("context7_enabled"):
            skill_md += """## Documentation Tools

> **💡 Context7 Integration**: This project is configured with Context7 MCP.
> When you need up-to-date API documentation for dependencies, use the
> `resolve-library-id` and `get-library-docs` tools from Context7.

"""

        if analysis["readme_content"]:
            skill_md += "## Additional Information\n\nSee README.md for complete project documentation.\n\n"

        return skill_md

    def _generate_reference_md(self, analysis: Dict[str, Any]) -> Optional[str]:
        """Generate REFERENCE.md if there's extensive documentation."""
        if not analysis["dependencies"]:
            return None

        reference_md = f"""# {analysis["name"].title()} Reference

## Dependencies

"""

        for dep in analysis["dependencies"][:10]:
            reference_md += f"### {dep}\n\n"
            reference_md += "A dependency used in this project. See package documentation for details.\n\n"

        if analysis["has_docs"]:
            reference_md += "## Project Documentation\n\n"
            reference_md += "See the `docs/` directory for detailed project documentation.\n\n"

        return reference_md

    def _get_context7_hint_for_command(self) -> str:
        """Get the Context7 hint section for command templates."""
        if not self._detect_context7():
            return ""

        return """
## Documentation

If you have Context7 MCP configured, you can retrieve current API docs by asking Claude to use Context7 tools.
"""

    def _generate_commands(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """Generate command files for common tasks."""
        commands = {}
        hint = self._get_context7_hint_for_command()

        # Generate build command if applicable
        if "build" in analysis["tasks"]:
            build_cmd = analysis["tasks"]["build"]
            commands["build-project"] = f"""---
name: build-project
description: Build the {analysis["name"]} project
---

# Build Project

Builds the project using: `{build_cmd}`

## Usage

Just say "build the project" or "run the build"
{hint}"""

        # Generate test command if applicable
        if "test" in analysis["tasks"]:
            test_cmd = analysis["tasks"]["test"]
            commands["run-tests"] = f"""---
name: run-tests
description: Run tests for {analysis["name"]}
---

# Run Tests

Runs the test suite using: `{test_cmd}`

## Usage

Just say "run tests" or "test the project"
{hint}"""

        # Generate setup-context7 helper if Context7 not configured
        if not analysis.get("context7_enabled"):
            commands["setup-context7"] = self._generate_context7_setup_helper(analysis)

        return commands

    def _generate_context7_setup_helper(self, analysis: Dict[str, Any]) -> str:
        """
        Generate a helper command for setting up Context7 MCP.

        This provides instructions for users who don't have Context7 configured
        but may want to add it for better documentation access.
        """
        return f"""---
name: setup-context7
description: Instructions for setting up Context7 MCP integration
---

# Setup Context7 MCP

Context7 is a Model Context Protocol (MCP) server that provides access to
up-to-date API documentation for popular libraries and frameworks.

## Quick Setup

Add Context7 to your `.mcp.json` file:

```json
{{
  "mcpServers": {{
    "context7": {{
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }}
  }}
}}
```

## Why Use Context7?

This project ({analysis["name"]}) uses the following dependencies:

{chr(10).join(f"- `{dep}`" for dep in analysis.get("dependencies", [])[:5]) or "- (no dependencies detected)"}

Context7 can provide up-to-date documentation for these libraries, ensuring
you have accurate API references when working with this codebase.

## Usage

Once configured, use these tools:

1. `resolve-library-id("{analysis["name"]}")` - Find library ID
2. `get-library-docs(library_id, topic)` - Get specific documentation

## Reference

https://github.com/upstash/context7
"""

    def _write_skill_pack(self, skill_md: str, reference_md: Optional[str], commands: Dict[str, str]):
        """Write skill pack files to disk."""
        # Create skill directory
        self.target_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        if not safe_write_text(self.target_dir / "SKILL.md", skill_md):
            print(f"Error: Failed to write SKILL.md to {self.target_dir}", file=sys.stderr)

        # Write REFERENCE.md if applicable
        if reference_md:
            refs_dir = self.target_dir / "references"
            refs_dir.mkdir(exist_ok=True)
            if not safe_write_text(refs_dir / "REFERENCE.md", reference_md):
                print(f"Error: Failed to write REFERENCE.md to {refs_dir}", file=sys.stderr)

        # Write commands (to parent .claude/commands if project scope)
        if commands:
            # Determine commands directory
            if ".claude" in str(self.target_dir):
                # Project scope: write to .claude/commands
                commands_dir = self.target_dir.parent / "commands"
            else:
                # User scope: write to ~/.claude/commands
                commands_dir = Path.home() / ".claude" / "commands"

            commands_dir.mkdir(parents=True, exist_ok=True)

            for cmd_name, cmd_content in commands.items():
                if not safe_write_text(commands_dir / f"{cmd_name}.md", cmd_content):
                    print(f"Error: Failed to write command {cmd_name} to {commands_dir}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Claude skill pack from repository workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate skill pack (dry-run)
  %(prog)s --source https://github.com/user/repo --target-dir ~/.claude/skills/my-workflow

  # Actually generate
  %(prog)s --source ~/code/project --target-dir .claude/skills/project-workflow --dry-run=false
  
  # Generate and archive to zip
  %(prog)s --source ~/code/project --target-dir .claude/skills/project-workflow --output my-skill.zip --dry-run=false
        """,
    )

    parser.add_argument("--source", required=True, help="GitHub URL or local path to repository")

    parser.add_argument("--target-dir", required=True, help="Target directory for generated skill pack")

    parser.add_argument("--repo-name", help="Repository name (defaults to target directory name)")

    parser.add_argument("--output", dest="output_zip", help="Optional: path to output zip archive")

    # Add standardized dry-run and apply arguments
    add_dry_run_argument(parser, help_text="Preview without writing (default: true)")
    add_apply_argument(parser)

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Resolve effective dry-run state (--apply overrides --dry-run)
    effective_dry_run = resolve_dry_run(args)

    try:
        generator = SkillpackGenerator(
            source=args.source,
            target_dir=args.target_dir,
            repo_name=args.repo_name,
            dry_run=effective_dry_run,
            verbose=args.verbose,
            output_zip=args.output_zip,
        )

        return generator.generate()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
