---
name: mine
description: Import Claude Code resources from GitHub repositories or local paths, and convert AI framework patterns to Claude Code format. Use when the user wants to integrate Claude artifacts (skills, commands, agents, hooks, MCP configs) from a repo, scan a repo for Claude Code assets, install skills from a GitHub repository, convert a repository into a Claude skill, convert Fabric patterns to Claude agents/commands, convert LangChain chains to agents, import workflow automation from existing codebases, or transform AI framework repositories into Claude-compatible resources. Automatically detects Claude Code resources and AI frameworks (Fabric, LangChain, AutoGen) with dry-run defaults and conflict protection.
---

# MINE

Import and integrate Claude Code resources from GitHub repositories or local paths. This skill scans repositories for Claude artifacts (skills, commands, agents, hooks, MCP configs, CLAUDE.md), converts AI framework patterns (Fabric, LangChain, AutoGen) to Claude Code format, and generates new skill packs from repository workflows.

## Quick Start

### Import Claude Artifacts
```bash
# Dry-run scan (preview, no writes)
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --dry-run

# Apply import after reviewing
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --apply
```

### Convert Fabric Patterns
```bash
# Auto-detect and convert Fabric patterns
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/danielmiessler/fabric \
  --scope user \
  --mode convert \
  --apply

# Result: patterns/ → Claude agents/commands
# - patterns/extract_wisdom → ~/.claude/agents/extract_wisdom.md
# - patterns/summarize → ~/.claude/commands/summarize.md
```

### Discover Agentic Content
```bash
# Find and convert prompts, agents, tools anywhere in a repo
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --discover-agentic \
  --min-confidence 0.65 \
  --apply
```

### Generate Skill Pack
```bash
# Create skill from repository without Claude artifacts
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope project \
  --mode generate \
  --target-repo ~/projects/myapp \
  --apply
```

---

## Import Modes

### Import (Default)

Copies detected Claude artifacts to the appropriate locations:

| Artifact | User Scope | Project Scope |
|----------|------------|---------------|
| Skills | `~/.claude/skills/` | `.claude/skills/` |
| Commands | `~/.claude/commands/` | `.claude/commands/` |
| Agents | `~/.claude/agents/` | `.claude/agents/` |
| Hooks | `~/.claude/hooks/` | `.claude/hooks.imported.<repo>/` |
| MCP configs | `~/.mcp.imported.<repo>.json` | `.mcp.imported.<repo>.json` |
| CLAUDE.md | `~/.claude/CLAUDE.imported.<repo>.md` | `.claude/CLAUDE.imported.<repo>.md` |

### Convert

Converts AI framework patterns to Claude Code format:

**Fabric Framework:**
- Detects `patterns/` directory with `system.md` files
- Simple patterns → Commands (extract, summarize, create)
- Complex patterns → Agents (analyze, review, evaluate)
- Multi-step patterns → Skills with workflows

**LangChain Framework:**
- Detects LangChain/LangGraph dependencies and imports
- Generates scaffold commands and assistant agents
- Includes conversion report with entry points

**AutoGen Framework:**
- Detects AutoGen dependencies and agent definitions
- Generates scaffold commands and coordinator agents
- Includes conversion report with agent mappings

### Agentic Discovery

Heuristic scanner that finds agentic content anywhere in a repository:

- **Enable:** `--discover-agentic` flag
- **Threshold:** `--min-confidence <0.0-1.0>` (default: 0.65)
- **Detects:** System prompts, agent definitions, tool specs, workflows
- **Converts to:** Claude Code artifacts with provenance tracking
- **Safety:** Automatic secret redaction before conversion

### Generate

Creates skill packs from repositories without Claude artifacts:

- Analyzes README, docs, package.json, pyproject.toml, Makefile
- Creates `.claude/skills/<repo>-workflow/` with SKILL.md
- Optionally creates commands for common tasks
- Includes Context7 hints when MCP is configured

### Skill-Creator Integration

For complex repositories where template-based generation produces suboptimal results,
MINE can hand off to Anthropic's `skill-creator` skill for AI-assisted skill authoring.

**Behavior:**
- **Auto-detect (default)**: Hands off when confidence is low AND skill-creator is installed
- **Force handoff**: Use `--use-skill-creator` to always use skill-creator
- **Disable handoff**: Use `--no-skill-creator` to use templates only

```bash
# Auto-detect (default) - uses skill-creator if installed and appropriate
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --mode generate

# Force skill-creator handoff
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --use-skill-creator

# Disable skill-creator (templates only)
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --no-skill-creator
```

**When Handoff Occurs:**
| Trigger | Confidence | Action |
|---------|------------|--------|
| Known framework | > 50% | Template conversion |
| No artifacts detected | < 50% | Handoff if skill-creator installed |
| User request | Any | `--use-skill-creator` forces handoff |
| User disabled | Any | `--no-skill-creator` prevents handoff |

**Requirements:**
- Anthropic's `skill-creator` skill installed at `~/.claude/skills/skill-creator/`
- skill-creator is **recommended but not required** — MINE works without it

---

## Safety Features

### Dry-Run Default
All operations preview changes without writing. Use `--apply` (or `--dry-run=false`) to apply.

### Conflict Protection
Overlapping destinations are blocked unless `--force-conflicting` is specified.

### Path Safety
- Path traversal (`../`) is blocked [claim: path_safety_traversal_blocked]
- All paths validated against scope roots [claim: path_safety_traversal_blocked]
- Symlinks are skipped to prevent traversal attacks [claim: symlink_safety_skipped]

### Hook Security
- Hooks import to `.claude/hooks.imported.<repo>/` (never auto-enabled) [claim: hooks_staged]
- Manual review and merge required [claim: hooks_staged]

### Secret Protection
- Never stores credentials on disk [claim: secrets_redacted]
- Uses environment variables (`GITHUB_TOKEN`) when needed [claim: secrets_redacted]
- Automatic redaction during agentic conversion [claim: secrets_redacted]

---

## Scripts

### scan_repo.py

Scans a repository and outputs a JSON report of detected artifacts.

```bash
python3 ~/.claude/skills/mine/scripts/scan_repo.py \
  --source <url_or_path> \
  [--output report.json]
```

**Output:**
```json
{
  "repo_id": "user/repo",
  "source": "https://github.com/user/repo",
  "framework_type": "fabric",
  "detected_artifacts": [...],
  "suggested_actions": ["convert"],
  "risks": []
}
```

### import_assets.py

Main import/convert/generate workflow.

```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source <url_or_path> \
  --scope user|project \
  [--mode auto|import|convert|generate] \
  [--apply] \
  [--dry-run] \
  [--target-repo <path>] \
  [--overwrite-with-backup] \
  [--discover-agentic] \
  [--min-confidence <0.0-1.0>]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `--source` | GitHub URL or local path |
| `--scope` | `user` (~/.claude/) or `project` (.claude/) |
| `--mode` | `auto`, `import`, `convert`, or `generate` |
| `--apply` | Apply changes (disable dry-run) |
| `--dry-run` | Preview changes (default: true) |
| `--target-repo` | Target repo path (required for project scope) |
| `--overwrite-with-backup` | Backup before overwriting |
| `--discover-agentic` | Enable agentic content discovery |
| `--min-confidence` | Confidence threshold (default: 0.65) |

### convert_framework.py

Standalone framework converter.

```bash
python3 ~/.claude/skills/mine/scripts/convert_framework.py \
  --framework fabric|langchain|autogen \
  --source <path> \
  --output <output_dir> \
  [--apply]
```

### generate_skillpack.py

Standalone skill pack generator.

```bash
python3 ~/.claude/skills/mine/scripts/generate_skillpack.py \
  --source <url_or_path> \
  --target-dir <output_path> \
  [--repo-name <name>] \
  [--apply]
```

---

## Detection Patterns

### Claude Artifacts
| Type | Locations |
|------|-----------|
| Skills | `.claude/skills/**/SKILL.md`, `skills/**/SKILL.md` |
| Commands | `.claude/commands/*.md`, `commands/*.md` |
| Agents | `.claude/agents/*.md`, `agents/*.md` |
| Hooks | `.claude/hooks/**` |
| MCP | `.mcp.json` |
| Docs | `CLAUDE.md` |

### Frameworks
| Framework | Detection |
|-----------|-----------|
| Fabric | `patterns/` with `system.md` files |
| LangChain | `langchain`/`langgraph` imports |
| AutoGen | `autogen` imports, agent configs |

### Agentic Content
| Type | Signals |
|------|---------|
| Prompts | "System Prompt", "Instructions", "Role:" |
| Agents | "Agent", "role:", "goals:", "backstory:" |
| Tools | "Tool", "function", "input_schema" |
| Workflows | "steps:", "jobs:", "pipeline" |

---

## Context7 Integration

When Context7 MCP is configured (detected via `.mcp.json`), generated artifacts include Context7 usage hints:

- Commands include "Documentation" sections for API docs
- Agents include "Docs policy" sections recommending Context7
- Conversion reports note when Context7 is not configured

**Note:** The skill generates documentation that instructs Claude to use Context7; it does not directly invoke Context7 tools.

To enable Context7:
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

---

## GitHub Authentication

Authentication methods (in order of preference):

1. **GitHub CLI (`gh`)** — Uses existing authentication
2. **GITHUB_TOKEN** — Environment variable (never stored on disk)
3. **Unauthenticated** — Falls back to `git clone` for public repos

```bash
# Optional: Set GitHub token
export GITHUB_TOKEN="ghp_your_token_here"
```

---

## Platform Compatibility

- **Cross-platform paths:** Uses `pathlib` consistently
- **Windows long paths:** Handles paths >260 chars via `\\?\` prefix
- **Case-insensitive filesystems:** Safe two-step renames
- **Subprocess portability:** Uses `sys.executable` for Python calls

---

## Examples

### Convert Fabric Framework
```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/danielmiessler/fabric \
  --scope user \
  --apply
```

### Import from Public Repository
```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/example/claude-pdf-tools \
  --scope user \
  --apply
```

### Generate Workflow Skill
```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source ~/code/my-python-app \
  --scope project \
  --mode generate \
  --target-repo ~/code/my-python-app \
  --apply
```

### Scan Without Importing
```bash
python3 ~/.claude/skills/mine/scripts/scan_repo.py \
  --source https://github.com/example/repo \
  --output scan-results.json
```

---

## Reference

For detailed technical information, see `references/REFERENCE.md`.
