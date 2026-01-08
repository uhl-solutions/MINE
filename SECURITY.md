# Security Policy & Checklist (MINE)

This document describes the security posture, threat model, and an operator/maintainer checklist for **MINE (Modular Integration and Normalization Engine)**.

> Scope: This policy is written for the MINE workflow of **scanning, importing, converting, packaging, registering, and updating** artifacts and integrations from third-party repositories. [claim: feature_import_standard] [claim: feature_convert_frameworks] [claim: feature_agentic_discovery]

---

## 1) Goals, non-goals, and guarantees

### Security goals
MINE aims to:
- **Avoid executing untrusted code** during scan/import/update operations. [claim: security_no_execution]
- **Prevent writes outside the intended workspace** (path traversal / root-escape). [claim: path_safety_traversal_blocked]
- **Prevent silent overwrites** of existing user files (conflict detection, transactional updates). [claim: local_mods_protected]
- **Handle repositories safely at scale** (resource limits to reduce DoS risk). [claim: security_resource_limits]
- **Minimize credential exposure** during cloning and fetching. [claim: secrets_redacted]

### Non-goals
MINE does **not** aim to:
- Provide a sandbox for executing third-party code. [claim: security_policy_manual]
- Prove full integrity of external sources (e.g., defend against a compromised upstream). [claim: security_policy_manual]
- Replace standard secure development practices (CI, code review, dependency hygiene). [claim: security_policy_manual]

### Intended guarantees (operational)
When used as designed, MINE should:
- Only **read** external repositories during scan/discovery and only **write** to explicitly chosen target directories during import/update. [claim: path_safety_traversal_blocked]
- Never enable or execute imported hooks automatically; hooks should be **staged** for explicit manual enablement. [claim: hooks_staged]
- Fail safely: prefer aborting over partial/unsafe application when conflicts are detected. [claim: local_mods_protected]

---

## 2) Threat model

### Primary threats
- **Malicious repo content**: path traversal attempts, symlinks, huge files, tricky names, zip bombs, commit history bloat.
- **Credential leakage**: tokens embedded in clone URLs, stored in logs, `.git/config`, crash reports, command history.
- **Corrupted state**: partial writes leading to broken provenance/registry and inconsistent updates.
- **Update drift**: unexpected changes during sync leading to accidental overwrites or file removal.
- **Local environment exposure**: tools invoked with privileged permissions, running on shared machines.

### Trust assumptions
- The operator controls the machine/account running MINE.
- The operator can verify the source repository/commit where needed (e.g., via signed tags, known owners).
- Local filesystem permissions and OS security controls are configured reasonably (e.g., not running as root unnecessarily).

---

## 3) Operator safety checklist

### Before scanning a repository
- [x] Confirm the repo source (owner/org, URL) and desired **ref** (branch/tag/commit). [claim: security_policy_manual]
- [x] Prefer scanning **pinned commits** over mutable branches for reproducibility. [claim: security_policy_manual]
- [x] Avoid scanning as a highly privileged user (e.g., root). [claim: security_policy_manual]
- [x] Ensure the workspace is separate from sensitive directories (SSH keys, secrets, home dotfiles, etc.). [claim: security_policy_manual]

### During scan/discovery
- [x] Keep **time/file-size/candidate limits** enabled (avoid unbounded traversal). [claim: security_resource_limits]
- [x] Treat non-text/binary files as untrusted and avoid processing beyond metadata unless required. [claim: security_policy_manual]
- [x] Avoid attempting to parse or execute scripts; only classify based on file layout and static inspection. [claim: security_no_execution]

### Importing assets (writes)
- [x] Default to **dry-run**; review planned changes. [claim: dry_run_default]
- [x] Verify the destination directory is correct and not a symlink to somewhere else. [claim: security_policy_manual]
- [x] Ensure conflict checks are enabled: [claim: local_mods_protected]
  - [x] Detect exact path collisions [claim: overlapping_destinations_blocked]
  - [x] Detect parent/child overlaps (directory vs file) [claim: overlapping_destinations_blocked]
- [x] Use staging directories where feasible, then apply atomically. [claim: local_mods_protected]

### Hooks
- [x] Hooks must be **staged** (e.g., `.claude/hooks.imported.<source>/`) and **not enabled automatically**. [claim: hooks_staged]
- [x] Review hook scripts manually before enabling. [claim: security_policy_manual]
- [x] Keep a record of enabled hooks and their source commit. [claim: security_policy_manual]
- [x] Re-verify hooks after updates (hooks are code). [claim: security_policy_manual]

### Updating integrations (sync)
- [x] Require a valid provenance/registry entry before applying updates. [claim: security_policy_manual]
- [x] Prefer transactional updates: [claim: local_mods_protected]
  - [x] Validate plan [claim: dry_run_default]
  - [x] Apply to temp/staging [claim: local_mods_protected]
  - [x] Atomic swap [claim: local_mods_protected]
  - [x] Rollback on error [claim: local_mods_protected]
- [x] Ensure update logic never deletes outside managed paths. [claim: path_safety_traversal_blocked]
- [x] Consider using a “two-person review” for updates in sensitive environments. [claim: security_policy_manual]

---

## 4) Maintainer checklist (codebase)

### Authentication and cloning
- [x] Detect upstream force-pushes/history rewrites. [claim: force_push_detected]
- [x] **Do not embed tokens in clone URLs** (e.g., `https://TOKEN@...`). [claim: secrets_redacted]
  - Prefer `gh auth` flows, credential helpers, or header-based auth. [claim: security_policy_manual]
- [x] Redact secrets from: [claim: secrets_redacted]
  - [x] Logs [claim: secrets_redacted]
  - [x] Exceptions [claim: secrets_redacted]
  - [x] Stored provenance/registry JSON [claim: secrets_redacted]
- [x] Avoid printing full remote URLs when they may contain credentials. [claim: secrets_redacted]

### Filesystem safety
- [x] Use hash-based naming for cached sources to prevent collisions. [claim: cache_collision_safe]
- [x] All write operations must pass through:
  - [x] **Path containment** checks (resolve + `relative_to`) [claim: path_safety_traversal_blocked]
  - [x] Symlink-aware logic where applicable [claim: path_safety_traversal_blocked]
- [x] Use a single authoritative helper for safe joins/validation to prevent bypasses. [claim: path_safety_traversal_blocked]
- [x] Guard against: [claim: path_safety_traversal_blocked]
  - [x] `..` traversal [claim: path_safety_traversal_blocked]
  - [x] absolute paths [claim: path_safety_traversal_blocked]
  - [x] UNC paths / drive letter edge cases (Windows) [claim: path_safety_traversal_blocked]
  - [x] case-insensitive filesystem quirks [claim: case_insensitive_collisions]
  - [x] weird unicode normalization issues (NFC/NFD) [claim: path_safety_traversal_blocked]

### Atomic writes & locking
- [x] Write critical state files (provenance, registry, manifests) using: [claim: local_mods_protected]
  - [x] temp file → fsync → atomic replace [claim: local_mods_protected]
  - [x] file locks to avoid concurrent writers [claim: local_mods_protected]
- [x] Ensure crash safety: a power loss should not corrupt state files. [claim: local_mods_protected]

### Resource limits
- [x] Enforce scan limits: [claim: security_resource_limits]
  - [x] max file size [claim: security_resource_limits]
  - [x] max files/candidates [claim: security_resource_limits]
  - [x] max scan duration [claim: security_resource_limits]
- [x] Cap recursion depth and avoid following symlinks during traversal unless explicitly required and safe. [claim: symlink_safety_skipped]

### Subprocess safety
- [x] Use `subprocess.run([...], shell=False)` with explicit args. [claim: security_no_execution]
- [x] Validate or constrain arguments derived from user input. [claim: security_no_execution]
- [x] Capture and handle errors without dumping secrets. [claim: secrets_redacted]

### Supply-chain and artifacts
- [x] Do not commit or ship `__pycache__`, `.pyc`, or other build artifacts. [claim: security_clean_artifacts]
- [x] Keep a `.gitignore`/packaging rules to exclude: [claim: security_clean_artifacts]
  - [x] `__pycache__/` [claim: security_clean_artifacts]
  - [x] `*.pyc` [claim: security_clean_artifacts]
  - [x] `.pytest_cache/` [claim: security_clean_artifacts]
  - [x] local logs [claim: security_clean_artifacts]
- [x] Prefer reproducible builds/exports of skillpacks. [claim: security_clean_artifacts]

---

## 5) Testing requirements (minimum baseline)

### Unit tests (recommended minimum)
- [x] `path_safety`:
  - [x] blocks `../` traversal
  - [x] blocks absolute paths
  - [x] blocks root-escape via symlink chains
  - [x] behaves correctly on case-insensitive paths
- [x] `safe_io`:
  - [x] atomic write leaves valid JSON on forced interruption simulation
  - [x] lock prevents concurrent writers (or resolves conflicts safely)
- [x] transactional updates:
  - [x] rollback restores original state on failures
  - [x] partial apply never leaves mixed old/new files

### Integration tests (recommended)
- [x] scan a repo with:
  - [x] huge file(s)
  - [x] deep directory nesting
  - [x] symlinks
  - [x] odd unicode names
- [x] import with conflicts and confirm abort behavior
- [x] update flows with changed/deleted files and confirm safety invariants

---

## 6) CI baseline (recommended)

At minimum, CI should run on each PR:
- [x] `python -m py_compile` on all shipped scripts
- [x] unit tests
- [x] lint/format (optional but recommended)
- [x] packaging check to ensure no compiled artifacts (`*.pyc`) are included [claim: security_clean_artifacts]

---

## 7) Security reporting

If you discover a vulnerability:
1. Do **not** publish details publicly until a fix is available.
2. Provide:
   - Steps to reproduce
   - Affected versions/commits
   - Impact assessment (what can be read/written/executed)
   - Suggested patch (if available)

**Suggested contact process (maintainers):**
- Add a dedicated security email or GitHub Security Advisory workflow.
- Acknowledge reports within 72 hours.
- Provide an estimated fix window and mitigations for operators.

**Contact:**
- Please report security issues via GitHub Issues with the `security` label, or email security@uhl.solutions.
- We aim to acknowledge reports within 72 hours.


---

## 8) Quick “secure defaults” summary

- Default to **dry-run** for anything that writes. [claim: dry_run_default]
- **Never** auto-enable hooks; stage them. [claim: hooks_staged]
- Avoid tokens in URLs; **redact secrets**. [claim: secrets_redacted]
- Use **atomic writes + locks** for state. [claim: local_mods_protected]
- Keep strict **path containment** checks everywhere. [claim: path_safety_traversal_blocked]
- Keep **resource limits** on scan/discovery. [claim: security_resource_limits]
- Add **tests + CI** for the primitives that enforce safety. [claim: security_policy_manual]
