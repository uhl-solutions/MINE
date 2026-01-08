# CLAUDE.md — MINE (Modular Integration and Normalization Engine)

This file is the **Claude Code + contributor reference** for **MINE**: a toolkit that **integrates, normalizes, and safely updates** Claude Code resources from external repositories.

MINE ships as **two Claude Code skills**:

- **`mine`** — import Claude artifacts, convert framework patterns (Fabric / LangChain / AutoGen), discover “agentic” content, and generate workflow skill packs.
- **`mine-mine`** — discover registered integrations and **sync updates from upstream** with strong safety guarantees (dry-run defaults, conflict protection, `.diff` patches).

> Author: **uhl.solutions** (see `LICENSE`).

---

## Repository layout

```text
.
├─ README.md
├─ CLAUDE.md
├─ SECURITY.md
├─ LICENSE
├─ config/
├─ docs/
│  ├─ CHANGELOG.md
│  ├─ CODE_OF_CONDUCT.md
│  └─ CONTRIBUTING.md
├─ scripts/
└─ skills/
   ├─ mine/
   │  ├─ SKILL.md
   │  ├─ references/
   │  └─ scripts/
   └─ mine-mine/
      ├─ SKILL.md
      ├─ references/
      └─ scripts/
         └─ discover/
```

Per-skill docs live in:

- `skills/mine/SKILL.md`
- `skills/mine-mine/SKILL.md`

Project documentation:
- `docs/BASELINE.md` — Tool versions and CI configuration.
- `docs/METRICS.md` — Coverage reports and quality metrics.
- `docs/CLAIMS.json` — Verified feature claims mapping.
- `docs/CHANGELOG.md` — Version history and release notes.

---

## Quick start (human + Claude Code)

### Install skills (user scope)

**One-line install:**

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/uhl-solutions/MINE/main/scripts/install.sh | bash

# Windows
irm https://raw.githubusercontent.com/uhl-solutions/MINE/main/scripts/install.ps1 | iex
```

**Local / Manual:**

```bash
# From repo root
./scripts/install.sh  # or .\scripts\install.ps1

# (shell scripts call scripts/install_skills.py)

# Manual copy
cp -r skills/mine        ~/.claude/skills/
cp -r skills/mine-mine   ~/.claude/skills/
cp -r skills/_shared     ~/.claude/skills/
```

### Integrate a repository (dry-run default)

```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user
```

Apply writes by disabling dry-run:

```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source https://github.com/user/repo \
  --scope user \
  --apply
```

### Keep integrations updated

```bash
# Discover existing integrations
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py --discover

# Check updates
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py --check --all

# Apply updates (dry-run is default; set false to write)
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo --dry-run=false
```

---

## Primary entrypoints

### `mine`

#### `import_assets.py` (main workflow)

```bash
python3 ~/.claude/skills/mine/scripts/import_assets.py \
  --source <url_or_path> \
  --scope user|project \
  [--mode auto|import|convert|generate] \
  [--apply] \
  [--dry-run] \
  [--target-repo <path>] \
  [--overwrite-with-backup] \
  [--verbose] \
  [--ref <git_ref>] \
  [--discover-agentic] \
  [--min-confidence <0.0-1.0>]
```

Key flags:

- `--mode`
  - `auto` (default): detect whether to import, convert, or generate
  - `import`: copy existing Claude artifacts
  - `convert`: convert supported framework patterns + optionally agentic discovery
  - `generate`: generate a workflow skill pack from repo conventions/docs
- `--scope`
  - `user`: writes to `~/.claude/...`
  - `project`: writes to `./.claude/...` (use `--target-repo` if you’re not running inside the target repo)
- `--apply`: **actually write files** (alias for `--dry-run=false`)
- `--dry-run=false`: alternative way to disable dry-run
- `--discover-agentic`: enable experimental “Phase 5” agentic discovery/conversion
- `--min-confidence`: threshold for agentic conversion (default `0.65`)

#### `convert_framework.py` (standalone converter)

```bash
python3 ~/.claude/skills/mine/scripts/convert_framework.py \
  --framework fabric|langchain|autogen \
  --source <path> \
  --output <output_dir> \
  [--dry-run]
```

#### `generate_skillpack.py` (standalone generator)

```bash
python3 ~/.claude/skills/mine/scripts/generate_skillpack.py \
  --source <url_or_path> \
  --target-dir <output_path> \
  [--repo-name <name>] \
  [--dry-run]
```

---

### `mine-mine`

#### `discover_integrations.py`

```bash
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py --discover

# Manual registration
python3 ~/.claude/skills/mine-mine/scripts/discover_integrations.py \
  --register \
  --source https://github.com/user/repo \
  --scope user \
  [--target-repo <path>] \
  [--registry <path>] \
  [--no-confirm] \
  [--verbose]
```

#### `update_integrations.py`

```bash
# Check
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py --check --all

# Apply (writes only when dry-run is false)
python3 ~/.claude/skills/mine-mine/scripts/update_integrations.py \
  --apply --id user-my-repo \
  --dry-run=false \
  [--overwrite-with-backup] \
  [--auto-import-new] \
  [--delete-policy soft|hard|ask|skip] \
  [--registry <path>] \
  [--verbose]
```

---

## Where MINE writes and what it tracks

### Scopes

| Scope | Writes to | Typical use |
|---|---|---|
| `user` | `~/.claude/...` | Your global Claude setup |
| `project` | `./.claude/...` | Keep artifacts with a repo |

### Persistent state (registry + cache)

- **Registry (source of truth):** `~/.claude/mine/registry.json`
- **Cloned sources cache:** `~/.claude/mine/sources/`
- **Agentic provenance (user scope):** `~/.claude/mine/.provenance/`  
  (Project scope writes provenance to `<output_dir>/.provenance/`)

### Integration markers (used by discovery)

MINE uses “marker” files/folders to detect integrations in the wild:

- `.claude/settings.imported.<repo>.json`
- `.claude/hooks.imported.<repo>/` *(staged for review; not auto-enabled)*
- `.mcp.imported.<repo>.json`
- `.claude/CLAUDE.imported.<repo>.md`
- `.claude/skills/<repo>-workflow/` *(generated packs)*

`<repo>` is “repo-safe” (e.g., `owner-repo`), derived from `owner/repo` by replacing `/` with `-`.

---

## Architecture (modules you’ll touch most)

### Repo Integrator (`skills/mine/scripts/`)

| Component | File | Responsibility |
|---|---|---|
| `AssetImporter` | `import_assets.py` | Orchestrates import/convert/generate |
| `RepoScanner` | `scan_repo.py` | Detects Claude artifacts and risk signals |
| Framework conversion | `convert_framework.py` | Fabric/LangChain/AutoGen converters |
| Skill pack generation | `generate_skillpack.py` | Workflow pack synthesis from docs/conventions |
| Agentic pipeline (P5) | `agentic_*.py` | Discover → classify → convert → provenance |

### Repo Integrator Update (`skills/mine-mine/scripts/`)

| Component | File | Responsibility |
|---|---|---|
| Discovery + registration | `discover/` (pkg) | Finds integrations + maintains registry (CLI: `discover_integrations.py`) |
| Update engine | `update_integrations.py` | Checks and applies upstream changes |
| Transaction manager | `transaction.py` | Atomic file operations + rollbacks |
| Git helper | `git_helpers.py` | Clone/fetch fallback chain + safety |
| Cache policy | `cache_eviction.py` | Keeps cached sources bounded |

### Shared Safety Utilities (`skills/_shared/`)

| Component | File | Responsibility |
|---|---|---|
| Path safety | `path_safety.py` | Traversal and “write root” enforcement |
| Atomic IO | `safe_io.py` | Atomic writes + lock discipline |
| Redaction | `redaction.py` | Removes common credential patterns |
| URL & Auth safety | `url_utils.py` | Secure cloning + credential redaction |
| Platform utils | `platform_utils.py` | Windows/WSL/Case-sensitivity helpers |
| Skill-creator bridge | `skill_creator_bridge.py` | Detection and handoff to Anthropic's skill-creator |

---

## Safety rules (don’t break these)

MINE’s behavior is intentionally conservative. When changing code, **preserve** these guarantees:

1. **Dry-run is the default**
   - Preview changes unless `--dry-run=false` is explicitly set.
2. **Never overwrite silently**
   - Locally modified files are protected; updates produce timestamped `.diff` patches.
3. **No path escapes**
   - Prevent `../` traversal; write only under approved roots for the chosen scope.
4. **Hooks are never auto-enabled**
   - Hook configs and hook scripts are staged into `*.imported.*` locations for manual review.
5. **Secrets should not be persisted**
   - Redaction runs before converting agentic content; avoid writing tokens into generated artifacts.
6. **Be robust on case-insensitive filesystems**
   - Windows/macOS collisions must be detected and handled deterministically.

For a full breakdown of safety guarantees and operator checklists, see [SECURITY.md](SECURITY.md).

---

## How updates work (mental model)

Update flow (simplified):

1. **Discover** integrations via markers + `registry.json`
2. **Clone/fetch** upstream source into cache
3. **Analyze changes** (hash/commit mapping + file-level deltas)
4. **Apply transactionally** (atomic writes; backups optional)
5. **Protect local edits** with `.diff` patches and conflict logs
6. **Enforce cache limits** (post-run housekeeping)

---

## Development notes

### Requirements

- Python **3.9+**
- Git **2.0+**
- Optional: GitHub CLI (`gh`) or `GITHUB_TOKEN` for private repos

### Style & quality

- Keep scripts **stdlib-only** unless there’s a strong reason.
- Prefer small, testable helpers over monolith functions.
- **Coverage**: Target 100% for shared utilities; 50%+ overall for the `skills/` tree.
- Preserve deterministic output (stable ordering, stable IDs).
- Always keep “dry-run” and “apply” code paths in parity.

### Adding support for new artifact types

Where to look first:

- `scan_repo.py` — detection rules + destination suggestions
- `import_assets.py` — install/copy rules + marker creation
- `path_safety.py` / `safe_io.py` — safe write primitives (use these, don’t bypass)

### Adding a new framework adapter

- Start in `convert_framework.py`
- Add a **clear detection signal** and a **well-defined output mapping**
- Ensure conversion output includes provenance or clear source references
- Keep conversions review-friendly (no surprises, no implicit execution)

---

## License

MIT. See `LICENSE`.

**Copyright (c) 2025 uhl.solutions**
