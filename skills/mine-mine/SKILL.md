---
name: mine-mine
description: Update integrated Claude Code repositories from upstream. Use when the user wants to update integrated repos, refresh imported skills, sync Claude artifacts from GitHub, update hooks/commands/skills from repo, check for updates to integrated repositories, or keep imported Claude resources in sync with their source repositories. Automatically discovers integrated repos, checks for upstream changes, and safely applies updates with dry-run defaults and conflict protection.
---

# MINE MINE

Keep your integrated Claude Code resources in sync with their upstream repositories. This skill discovers previously integrated repositories (imported via mine), checks for upstream updates, and safely applies changes while protecting your local modifications.

## Quick Start

### Discover Integrations
```bash
# Find all integrations in current repo and user scope
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --discover

# Search in specific roots
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --discover \
  --search-roots ~/projects,~/code
```

### Check for Updates
```bash
# Check all registered integrations
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --all

# Check specific integration
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --id user-my-repo
```

### Apply Updates
```bash
# Dry-run (preview changes)
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo

# Actually apply updates
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo \
  --dry-run=false
```

---

## Integration Markers

The skill recognizes these integration patterns:

| Marker | Location | Source |
|--------|----------|--------|
| `settings.imported.<repo>.json` | `.claude/` | mine import |
| `hooks.imported.<repo>/` | `.claude/` | mine import |
| `.mcp.imported.<repo>.json` | Project root | mine import |
| `CLAUDE.imported.<repo>.md` | `.claude/` | mine import |
| `<repo>-workflow/` | `.claude/skills/` | mine generate |

User-scope artifacts tracked via registry:
- `~/.claude/skills/*`
- `~/.claude/commands/*`
- `~/.claude/agents/*`

---

## Safety Features

### Dry-Run Default
All operations preview changes without writing. Use `--dry-run=false` to apply.

### Update Safety
| Scenario | Behavior |
|----------|----------|
| Unchanged files | ✅ Updates automatically |
| Locally modified files | ⚠️ Creates `.diff` patch for review |
| Conflicts | ❌ Never overwrites silently |
| Hooks | 🔒 Never auto-enabled (stays in `.imported`) |
| Path traversal | 🛡️ Blocked and rejected |
| Secrets | 🔑 Never stored (uses env vars) |
| Failures | 🔄 Transactional rollback |

### Force-Push Detection
Detects upstream history rewrites and recommends reimport.

---

## Core Workflow

### 1. Discovery Phase

**First time setup:**
```bash
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --discover \
  --search-roots ~/projects,~/code
```

The skill will:
- Scan for integration markers
- Ask for confirmation before tracking
- Request source URLs when unknown
- Save to registry (`~/.claude/mine/registry.json`)

**Manual registration:**
```bash
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --register \
  --source https://github.com/user/repo \
  --scope user
```

### 2. Check Phase

```bash
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --all
```

Output shows:
- Integration ID
- Number of new commits
- Number of files changed
- Update status

### 3. Review Phase

```bash
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --id user-my-repo
```

Shows:
- Commit log summary
- Changed files list
- Potential conflicts

### 4. Apply Phase

```bash
# Dry-run to preview
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo

# Apply after review
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo \
  --dry-run=false
```

### 5. Unregister Phase

Remove an integration from the registry and optionally delete its artifacts:

```bash
# Preview what would be removed (dry-run default)
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --unregister user-my-repo

# Remove from registry only (keep files)
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --unregister user-my-repo \
  --dry-run=false

# Remove from registry AND delete imported files (with backup)
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --unregister user-my-repo \
  --delete-files \
  --dry-run=false

# Force delete even locally modified files
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --unregister user-my-repo \
  --delete-files \
  --force \
  --dry-run=false
```

**Safety:**
- Locally modified files are skipped by default (use `--force` to include)
- All deleted files get `.unregister-bak.<timestamp>` backups
- Staged imports (hooks, MCP, CLAUDE.md) are also cleaned up
- Transactional: rolls back on any failure

---

## Registry Structure

Location: `~/.claude/mine/registry.json`

```json
{
  "version": "1.0",
  "config": {
    "search_roots": ["~/projects", "~/code"],
    "auto_track": true,
    "ask_confirmation": true
  },
  "integrations": {
    "user-my-skills": {
      "id": "user-my-skills",
      "source_url": "https://github.com/user/my-skills",
      "target_scope": "user",
      "target_repo_path": "/home/user/.claude",
      "local_cache_clone_path": "/home/user/.claude/mine/sources/my-skills",
      "last_import_commit": "abc123...",
      "last_checked_commit": "abc123...",
      "markers": [...],
      "artifact_mappings": [...]
    }
  }
}
```

---

## Conflict Resolution

When upstream has changes AND local file was modified:

**What happens:**
1. Update script detects hash mismatch
2. Creates `.diff` patch file:
   ```
   ~/.claude/skills/my-skill/SKILL.md.diff.20241229_143022
   ```
3. Skips automatic update
4. Logs conflict in output

**How to resolve:**
```bash
# Review the diff
cat ~/.claude/skills/my-skill/SKILL.md.diff.20241229_143022

# Apply manually if desired
cd ~/.claude/skills/my-skill
patch < SKILL.md.diff.20241229_143022

# Or merge manually using your preferred tool
```

---

## Examples

### Update All Integrated Repos

```bash
# Step 1: Check what's available
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --all

# Output:
# Updates available for 2 integration(s):
#   - user-claude-skills: 3 commits
#   - project-infrastructure: 1 commit

# Step 2: Apply updates (dry-run)
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --all

# Step 3: Review conflicts (if any)
# Check for .diff files and merge manually

# Step 4: Apply for real
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --all --dry-run=false
```

### Register and Update New Integration

```bash
# Register a repository you previously integrated
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --register \
  --source https://github.com/user/repo \
  --scope user

# Check for updates
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --check --id user-repo

# Apply if updates found
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-repo \
  --dry-run=false
```

### Resolve a Conflict

```bash
# Apply update (finds conflict)
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-skills

# Output shows conflict with .diff file created

# Review the diff
cat ~/.claude/skills/my-skill/SKILL.md.diff.20241229_143022

# Manually merge
cd ~/.claude/skills/my-skill
patch < SKILL.md.diff.20241229_143022
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No source URL" | Register manually with source URL |
| "Failed to clone" | Use gh CLI or set GITHUB_TOKEN |
| Rate limiting | Authenticate with gh CLI for higher limits |

---

## Data Storage

| Data | Location |
|------|----------|
| Registry | `~/.claude/mine/registry.json` |
| Cached clones | `~/.claude/mine/sources/` |
| Conflict patches | `<file>.diff.<timestamp>` |
| Unregister backups | `<file>.unregister-bak.<timestamp>` |


---

## Platform Compatibility

- **Windows long paths:** All operations handle paths >260 chars via `\\?\` prefix
- **Transaction safety:** Atomic file operations with rollback on failure
- **Chmod preservation:** Detects and preserves executable bits using `shutil.copy2`

---

## Integration with mine

| Skill | Purpose |
|-------|---------|
| **mine** | Initial import/conversion |
| **mine-mine** | Keep imports in sync |

---

## Reference

For detailed technical information, see `references/REFERENCE.md`.
