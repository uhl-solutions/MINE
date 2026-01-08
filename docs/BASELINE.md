# MINE Baseline Configuration

This document captures the baseline configuration and tool versions for the MINE project.
It serves as a reference for reproducible builds and consistent development environments.

---

## Tool Versions

| Tool | Version | Configuration Source |
|------|---------|---------------------|
| **Python** | 3.9+ (tested on 3.10, 3.11, 3.12) | `pyproject.toml` |
| **Ruff** | 0.14.0 | `.pre-commit-config.yaml`, `config/requirements-dev.txt` |
| **pytest** | 8.3.5 | `config/requirements-dev.txt` |
| **pytest-cov** | 6.1.1 | `config/requirements-dev.txt` |
| **pre-commit** | latest | `.pre-commit-config.yaml` |

### Version Synchronization

Tool versions are kept in sync across:
- `.pre-commit-config.yaml` (pre-commit hooks)
- `config/requirements-dev.txt` (development dependencies)
- `pyproject.toml` (project configuration)

A CI check (`scripts/check_version_drift.py`) validates that these versions remain aligned.

---

## CI Matrix

Tests are run on the following combinations:

| OS | Python Versions | Coverage Config |
|----|-----------------|-----------------|
| Ubuntu (latest) | 3.10, 3.11, 3.12 | `.coveragerc.posix` |
| macOS (latest) | 3.11 | `.coveragerc.posix` |
| Windows (latest) | 3.11 | `.coveragerc.windows` |

---

## Coverage Summary

See [`docs/METRICS.md`](METRICS.md) for detailed coverage metrics.

### Targets

| Scope | Target | Rationale |
|-------|--------|-----------|
| **Overall** | 50%+ | Broad coverage across all skills |
| **Safety-critical modules** | 100% | High-confidence for security-sensitive code |

### Safety-Critical Modules (100% coverage required)

- `skills/_shared/path_safety.py` - Path traversal prevention
- `skills/_shared/safe_io.py` - Atomic file operations
- `skills/_shared/redaction.py` - Secret redaction
- `skills/_shared/url_utils.py` - URL credential handling
- `skills/_shared/platform_utils.py` - Cross-platform safety
- `skills/_shared/skill_creator_bridge.py` - Skill-Creator handoff safety
- `skills/_shared/logging_utils.py` - Standardized safety logging
- `skills/_shared/hash_helpers.py` - Content verification safety

---

## CI Checks

### Automated Checks

| Check | Enforced | Description |
|-------|----------|-------------|
| **Version drift** | Yes | Validates tool version consistency |
| **Lint (ruff)** | Yes | Code style and error detection |
| **Format (ruff)** | Yes | Code formatting consistency |
| **Tests** | Yes | Unit and integration tests |
| **Coverage** | Yes | Minimum 50% overall coverage |
| **Security patterns** | Yes | Token-in-URL, non-atomic writes, shell=True |
| **Distribution** | Yes | Build and verify dist package |
| **Smoke test** | Yes | Install and run basic commands |

### Pre-commit Hooks

| Hook | Purpose |
|------|---------|
| `ruff` | Lint Python code |
| `ruff-format` | Format Python code |
| `check-yaml` | Validate YAML syntax |
| `end-of-file-fixer` | Ensure files end with newline |
| `trailing-whitespace` | Remove trailing whitespace |
| `mixed-line-ending` | Enforce LF line endings |
| `check-added-large-files` | Prevent large file commits (>500KB) |
| `detect-private-key` | Block accidental key commits |

---

## Installation

### Recommended: Skills Distribution

```bash
# Clone the repository
git clone https://github.com/uhl-solutions/MINE.git
cd MINE

# Install skills to user scope
python scripts/install_skills.py

# Or preview first
python scripts/install_skills.py --dry-run
```

### Alternative: Manual Copy

```bash
cp -r skills/mine        ~/.claude/skills/
cp -r skills/mine-mine   ~/.claude/skills/
cp -r skills/_shared     ~/.claude/skills/
```

---

## Development Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install development dependencies
pip install -r config/requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=skills --cov-report=term-missing
```

---

## Updating Tool Versions

When updating tool versions:

1. Update the version in the primary source file
2. Run `scripts/check_version_drift.py` to identify any drift
3. Update all related configuration files
4. Run pre-commit: `pre-commit run --all-files`
5. Run tests: `pytest tests/ -v`

---

*Last updated: 2026-01-08*
