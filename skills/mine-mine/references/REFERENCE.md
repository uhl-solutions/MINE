# MINE MINE — Technical Reference

Detailed technical information about registry schema, update algorithms, and conflict resolution.

---

## Registry Schema

### Top-Level Structure

```json
{
  "version": "1.0",
  "config": {
    "search_roots": ["~/projects", "~/code"],
    "auto_track": true,
    "ask_confirmation": true
  },
  "integrations": {
    "<integration_id>": { ... }
  }
}
```

### Integration Entry Schema

```json
{
  "id": "user-my-repo",
  "source_url": "https://github.com/user/my-repo",
  "source_path": null,
  "target_scope": "user|project",
  "target_repo_path": "/home/user/.claude",
  "local_cache_clone_path": "/home/user/.claude/mine/sources/my-repo",
  "last_import_commit": "abc123def456...",
  "last_checked_commit": "abc123def456...",
  "markers": [
    {
      "type": "settings_import|hooks_import|mcp_import|claude_md_import|generated_skill",
      "file": "/path/to/marker",
      "dir": "/path/to/marker",
      "inferred_repo": "repo-name"
    }
  ],
  "artifact_mappings": [
    {
      "type": "skill|command|agent|hook|settings|mcp|claude_md",
      "source_relpath": ".claude/skills/my-skill/SKILL.md",
      "dest_abspath": "/home/user/.claude/skills/my-skill/SKILL.md",
      "last_import_hash": "sha256:...",
      "last_import_time": "2024-12-29T10:30:00Z"
    }
  ],
  "notes": "Optional notes",
  "update_plugins": false
}
```

---

## Discovery Patterns

### Integration Markers

| Marker | Location | Inferred From |
|--------|----------|---------------|
| `settings.imported.<name>.json` | `.claude/` | `<name>` portion |
| `hooks.imported.<name>/` | `.claude/` | `<name>` portion |
| `.mcp.imported.<name>.json` | Project root | `<name>` portion |
| `CLAUDE.imported.<name>.md` | `.claude/` | `<name>` portion |
| `<name>-workflow/` | `.claude/skills/` | `<name>` portion |

---

## Update Algorithm

### Phase 1: Clone/Fetch

```
1. Check if local_cache_clone_path exists
2. If not: clone source_url to cache
3. If exists: git fetch --all
4. Get current HEAD sha
5. Get remote HEAD sha (origin/main or origin/master)
```

### Phase 2: Change Analysis

```
1. Compare last_import_commit to remote HEAD
2. If same: report "up to date"
3. If different:
   a. Get commit log: git log <old>..<new>
   b. Get changed files: git diff --name-status <old>..<new>
   c. Categorize changes (features, fixes, breaking, docs)
```

### Phase 3: Mapping Check

```
For each artifact_mapping:
  1. Find corresponding changed file in upstream
  2. If file changed upstream:
     a. Hash local file
     b. Compare to last_import_hash
     c. If match: safe to update
     d. If mismatch: CONFLICT (local edit)
```

### Phase 4: Update Application

```
For safe updates:
  1. Checkout remote HEAD in cache
  2. Copy changed files to destinations
  3. Update last_import_hash for each
  4. Update last_import_commit

For conflicts:
  1. Generate diff: git diff <old>..<new> -- <file>
  2. Write to <dest>.diff.<timestamp>
  3. Skip update for this file
  4. Log conflict
```

---

## Conflict Resolution Strategies

### Strategy: .diff Patch Files (Default)

**When:** Local file modified, upstream also changed

**Action:**
1. Create `<dest>.diff.<timestamp>` with upstream changes
2. Skip automatic update
3. User manually reviews and applies

**Advantages:**
- Clean (no duplicate files)
- Reviewable (standard diff format)
- Applyable (`patch` command)

**Example:**
```bash
# Generated file
~/.claude/skills/my-skill/SKILL.md.diff.20241229_143022

# Review
cat ~/.claude/skills/my-skill/SKILL.md.diff.20241229_143022

# Apply
cd ~/.claude/skills/my-skill
patch < SKILL.md.diff.20241229_143022
```

---

## Unregister Algorithm

Remove an integration from the registry and optionally delete imported artifacts.

**Script:** `discover_integrations.py` (not `update_integrations.py`)

### Removal Process

```
1. Validate integration_id exists in registry
2. For each artifact_mapping:
   a. Check if file exists and hash matches
   b. Categorize: clean (can delete) vs modified (skip by default)
3. Preview actions (dry-run default)
4. If --delete-files:
   a. Create backup with .unregister-bak.<timestamp> suffix
   b. Delete original file
   c. Also clean up staged imports (hooks.imported, .mcp.imported, etc.)
5. Remove integration entry from registry
6. Save registry
```

### Flags

| Flag | Description |
|------|-------------|
| `--unregister <id>` | Integration ID to remove |
| `--delete-files` | Also delete imported artifacts |
| `--force` | Delete even locally modified files |
| `--dry-run=false` | Execute (default is preview) |

---

## Git Operations

### Clone Strategy

Priority order:
1. `gh repo clone` (if gh CLI authenticated)
2. `git clone` with GITHUB_TOKEN (if env var set)
3. `git clone` unauthenticated (public repos only)

### Fetch Operations

```bash
git -C <repo_path> fetch --all
```

### Commit Operations

```bash
# Get current HEAD
git -C <repo_path> rev-parse HEAD

# Get remote HEAD
git -C <repo_path> rev-parse origin/main
git -C <repo_path> rev-parse origin/master  # fallback

# Get commit log
git -C <repo_path> log <old>..<new> --pretty=format:'%H|||%an|||%ae|||%aI|||%s'

# Get changed files
git -C <repo_path> diff --name-status <old>..<new>

# Get file diff
git -C <repo_path> diff <old>..<new> -- <file>
```

---

## Hash Operations

### File Hashing

```python
import hashlib

def hash_file(path):
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
```

### Change Detection

```python
def has_file_changed(file_path, expected_hash):
    current_hash = hash_file(file_path)
    return current_hash != expected_hash
```

---

## Safety Guarantees

### Never Auto-Enabled

**Hooks:**
- Always written to `.claude/hooks.imported.<name>/`
- Never copied to `.claude/hooks/`
- User must manually review and enable

**Settings with Hooks:**
- Written to separate `.imported` file
- User must manually merge

### Never Overwrite Silently

**Local Edits:**
- Detected via hash comparison
- `.diff` patch created
- Original file preserved

### Never Store Secrets

**GitHub Authentication:**
- Prefers gh CLI (uses system credentials)
- Accepts GITHUB_TOKEN from environment
- Never writes tokens to disk or registry

---

## File System Layout

```
~/.claude/
├── mine/
│   ├── registry.json           # Integration registry
│   └── sources/                # Cached clones
│       ├── repo1/
│       ├── repo2/
│       └── ...
└── skills/
    └── mine-mine/
        ├── SKILL.md
        ├── references/
        │   └── REFERENCE.md
        └── scripts/
            ├── discover/               # Discovery package
            ├── discover_integrations.py
            ├── update_integrations.py
            ├── git_helpers.py
            ├── transaction.py
            └── cache_eviction.py
```

---

## Error Handling

### Clone Failures

| Cause | Handling |
|-------|----------|
| Network issues | Try multiple methods, report error |
| Authentication required | Suggest gh CLI or GITHUB_TOKEN |
| Repository not found | Skip integration, continue with others |

### Fetch Failures

| Cause | Handling |
|-------|----------|
| Network issues | Report error, skip update |
| Repository deleted/renamed | Don't modify registry |

### Hash Mismatches

| Cause | Handling |
|-------|----------|
| Line ending changes (CRLF/LF) | Treat as conflict |
| Permission changes | Treat as conflict |
| Actual content edits | Create .diff patch, skip update |

---

## Performance Considerations

### Caching
- Clone once to `~/.claude/mine/sources/`
- Reuse for all future updates
- Only fetch (not full clone) on subsequent checks

### Large Repositories
- Uses shallow clones where possible
- Fetches only needed commits
- Doesn't clone full history unless needed

---

## Extensibility

### Custom Conflict Strategies

Future: Allow per-integration conflict strategy:
```json
{
  "conflict_strategy": "diff|skip|backup|three_way"
}
```

### Plugin Update Integration

When `update_plugins: true`:
- Check if artifacts are plugin-managed
- Defer to plugin update mechanism
- Coordinate updates

### Custom Update Hooks

Future: Pre/post-update hooks:
```json
{
  "hooks": {
    "pre_update": "/path/to/script.sh",
    "post_update": "/path/to/script.sh"
  }
}
```
