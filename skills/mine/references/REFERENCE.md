# MINE — Technical Reference

Detailed technical information about scan patterns, import rules, and generation strategies.

---

## Scan Patterns

### Directory Structure Patterns

The scanner looks for Claude artifacts in these locations:

**User-Level:**
- `~/.claude/skills/`
- `~/.claude/commands/`
- `~/.claude/agents/`
- `~/.claude/hooks/`

**Project-Level:**
- `.claude/skills/`
- `.claude/commands/`
- `.claude/agents/`
- `.claude/hooks/`
- `.claude/settings.json`
- `.claude/settings.local.json`

**Plugin-Style:**
- `skills/`
- `commands/`
- `agents/`
- `.claude-plugin/`
- `plugin.json`

### File Type Detection

#### Skills

Required: `SKILL.md` with YAML frontmatter containing `name` and `description`

**Locations:**
```
.claude/skills/**/SKILL.md
skills/**/SKILL.md
```

**Validation:**
- Valid YAML frontmatter
- `name` and `description` fields present
- May include: `scripts/`, `references/`, `assets/`

#### Commands

Markdown files in command directories.

**Locations:**
```
.claude/commands/*.md
commands/*.md
```

#### Agents

Agent definition files (Markdown format).

**Locations:**
```
.claude/agents/*.md
agents/*.md
```

#### Hooks

Executable scripts in hooks directories.

**Locations:**
```
.claude/hooks/**
```

**Risk Assessment:**
| Pattern | Severity |
|---------|----------|
| Shell scripts (.sh, .bash) | Medium |
| Execution permissions | Medium |
| External command references | High |
| Binary executables | High |

#### MCP Configurations

**Locations:**
```
.mcp.json
.claude-plugin/mcp.json
mcp.json
```

**Format:** JSON with MCP server configurations

#### Documentation

**CLAUDE.md:** Repository root (Claude-specific instructions)

**README and docs:** Used for generate mode workflow analysis
- `README.md`, `README.rst`, `README.txt`
- `docs/`, `documentation/`
- `CONTRIBUTING.md`

#### Build/Workflow Files

**Locations:**
```
Makefile
package.json
pyproject.toml
setup.py
requirements.txt
Cargo.toml
go.mod
```

**Purpose:** Extract common tasks and dependencies for skill generation

### Risk Detection

**Severity Levels:**
- `low`: Documentation files, static assets
- `medium`: Shell scripts, hooks, commands with file operations
- `high`: Binary executables, scripts with network/system calls

**Risk Types:**
- `hook`: Executable hooks that run automatically
- `script`: Shell scripts in commands or other locations
- `binary`: Compiled executables
- `config`: Configurations that modify behavior

---

## Agentic Discovery Patterns

Heuristic-based discovery of agentic content anywhere in a repository.

### Locations Searched

```
prompts/**/*.md
agents/**/*.md
tools/**/*.py
workflows/**/*.yml
```

### Classification Signals

| Type | Signals |
|------|---------|
| Prompts | "System Prompt", "Instructions", "Role:", "Constraints:" |
| Agents | "Agent", "role:", "goals:", "backstory:" |
| Tools | "Tool", "function", "input_schema" |
| Workflows | "steps:", "jobs:", "pipeline" |

### Confidence Scoring

| Level | Score | Description |
|-------|-------|-------------|
| High | >0.8 | Multiple strong signals (filename + content) |
| Medium | 0.5-0.8 | Strong signal or multiple weak signals |
| Low | <0.5 | Weak signals only (usually ignored) |

---

## Import Rules

### Destination Mapping

#### User Scope

```
Source                          → Destination
────────────────────────────────────────────────────────────
.claude/skills/foo/            → ~/.claude/skills/foo/
skills/foo/                    → ~/.claude/skills/foo/
.claude/commands/build.md      → ~/.claude/commands/build.md
commands/build.md              → ~/.claude/commands/build.md
.claude/agents/helper.md       → ~/.claude/agents/helper.md
agents/helper.md               → ~/.claude/agents/helper.md
```

#### Project Scope

```
Source                          → Destination (relative to target repo)
────────────────────────────────────────────────────────────────────────
.claude/skills/foo/            → .claude/skills/foo/
skills/foo/                    → .claude/skills/foo/
.claude/commands/build.md      → .claude/commands/build.md
commands/build.md              → .claude/commands/build.md
.claude/hooks/pre-commit       → .claude/hooks.imported.<repo>/pre-commit
```

### Special Handling

#### Hooks (Security-Sensitive)

**Import behavior:**
- Always imported to project scope only
- Destination: `.claude/hooks.imported.<repo>/`
- Never auto-enabled
- Requires manual review and migration

**Merge instructions:**
```bash
# Review imported hooks
ls -la .claude/hooks.imported.<repo>/

# After review, manually enable:
cp .claude/hooks.imported.<repo>/pre-commit .claude/hooks/pre-commit
chmod +x .claude/hooks/pre-commit
```

#### MCP Configurations

**Import behavior:**
- Destination: `.mcp.imported.<repo>.json`
- Never overwrites existing `.mcp.json`
- Requires manual merge

**Merge instructions:**
```bash
# Review imported MCP config
cat .mcp.imported.<repo>.json

# Manually merge with existing config
```

#### CLAUDE.md

**Import behavior:**
- Destination: `.claude/CLAUDE.imported.<repo>.md`
- Never overwrites existing `CLAUDE.md`
- Provides merge guidance

### Conflict Resolution

#### Default Behavior (Skip)

1. Log the conflict
2. Skip the import
3. Add to conflict report
4. Continue with remaining files

#### Overwrite with Backup

When `--overwrite-with-backup` is enabled:

1. Create backup: `filename.bak.YYYYMMDD_HHMMSS`
2. Write new file
3. Log the backup location

### Directory Handling

**Create parent directories:**
```python
os.makedirs(os.path.dirname(dest_path), exist_ok=True)
```

**Preserve directory structure:**
- Skills: Copy entire skill directory with subdirectories
- Commands: Copy individual files only
- Agents: Copy individual files only

---

## Generation Strategies

### Workflow Analysis

When no Claude artifacts are found, analyze repository to generate a skill pack.

#### Step 1: Extract Repository Metadata

**From package.json:**
```json
{
  "name": "my-app",
  "scripts": {
    "build": "webpack build",
    "test": "jest",
    "lint": "eslint src/"
  }
}
```

**From pyproject.toml:**
```toml
[project]
name = "my-app"

[project.scripts]
build = "python -m build"
test = "pytest"
```

**From Makefile:**
```makefile
build:
    cargo build --release

test:
    cargo test
```

#### Step 2: Identify Common Tasks

| Pattern | Tasks |
|---------|-------|
| Build | `build`, `compile`, `make` |
| Test | `test`, `check`, `verify` |
| Lint | `lint`, `format`, `style` |
| Run | `start`, `serve`, `dev` |
| Deploy | `deploy`, `publish`, `release` |

#### Step 3: Generate SKILL.md

```markdown
---
name: <repo>-workflow
description: Workflow automation for <repo>
---

# <Repo Name> Workflow

## Overview
[Generated from README/docs]

## Quick Start
[Installation and setup instructions]

## Common Tasks

### Build
[How to build the project]

### Test
[How to run tests]

### Lint
[How to lint/format code]
```

#### Step 4: Generate Commands (Optional)

Create command files for 1-3 most common tasks.

#### Step 5: Context7 Integration

If Context7 MCP is configured, generated artifacts include instructions for using Context7 to fetch current docs.

**Note:** The skill does not directly invoke Context7 tools; it generates documentation that instructs Claude to use Context7 when appropriate.

---

## Clone Strategies

### GitHub CLI (Preferred)

```bash
gh repo clone <owner>/<repo> <dest> -- --depth 1
```

**Advantages:** Uses existing authentication, supports private repos

### Git with Token

```bash
git clone --depth 1 https://${GITHUB_TOKEN}@github.com/<owner>/<repo>.git <dest>
```

**Advantages:** Works without gh CLI, supports private repos

### Unauthenticated Git

```bash
git clone --depth 1 https://github.com/<owner>/<repo>.git <dest>
```

**Limitations:** Public repositories only, subject to rate limits

### Local Path

```bash
# Use source directly, no cloning needed
repo_path="$source"
```

---

## Validation

### SKILL.md Validation

**Required checks:**
1. Valid YAML frontmatter
2. `name` field present and non-empty
3. `description` field present (>50 chars recommended)
4. Markdown body present

**Optional checks:**
1. References to bundled resources exist
2. Code examples are syntactically valid
3. Links are not broken

### Script Validation

**Python scripts:**
```bash
python3 -m py_compile script.py
python3 script.py --help
```

**Shell scripts:**
```bash
bash -n script.sh
shellcheck script.sh  # If available
```

---

## Dry-Run Implementation

All write operations check dry-run flag:

```python
def write_file(dest_path, content, dry_run=True):
    if dry_run:
        print(f"[DRY-RUN] Would write: {dest_path}")
        return

    with open(dest_path, 'w') as f:
        f.write(content)
    print(f"✓ Wrote: {dest_path}")
```

**Dry-run output format:**
```
=== DRY-RUN MODE ===
No files will be modified. Use --dry-run=false to execute.

PLANNED OPERATIONS:
[CREATE] ~/.claude/skills/foo/SKILL.md
[CREATE] ~/.claude/skills/foo/scripts/helper.py
[SKIP]   ~/.claude/commands/build.md (exists)
[BACKUP] ~/.claude/agents/assistant.md → assistant.md.bak.20241229_143022
[CREATE] ~/.claude/agents/assistant.md

CONFLICTS:
- ~/.claude/commands/build.md (exists)

RISKS:
- .claude/hooks/pre-commit (shell script, medium severity)

To execute, run with: --dry-run=false
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Clone failures | Not found, auth failed, network | Check URL, verify auth |
| Invalid artifacts | Missing frontmatter or fields | Validate YAML format |
| Permission errors | Insufficient permissions | Check directory permissions |
| Merge conflicts | File exists, no overwrite | Use `--overwrite-with-backup` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Clone/download failed |
| 4 | Validation failed |
| 5 | Write permission denied |
