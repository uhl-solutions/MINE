# MINE Quality Metrics

This document tracks key quality and coverage metrics for the MINE project.

---

## Coverage Metrics

| Metric | Current | Target |
|--------|---------|--------|
| **Overall Coverage** | 55% | 50%+ |
| **Safety-Critical Modules** | 100% | 100% |

### Shared Utilities (Critical Safety)

| Module | Coverage | Target | Status |
|--------|----------|--------|--------|
| `skills/_shared/artifact_types.py` | 100% | 100%+ | ✅ |
| `skills/_shared/cli_helpers.py` | 100% | 100%+ | ✅ |
| `skills/_shared/hash_helpers.py` | 100% | 100%+ | ✅ |
| `skills/_shared/logging_utils.py` | 100% | 100%+ | ✅ |
| `skills/_shared/path_safety.py` | 100% | 100%+ | ✅ |
| `skills/_shared/platform_utils.py` | 100% | 100%+ | ✅ |
| `skills/_shared/redaction.py` | 100% | 100%+ | ✅ |
| `skills/_shared/safe_io.py` | 100% | 100%+ | ✅ |
| `skills/_shared/skill_creator_bridge.py` | 100% | 100%+ | ✅ |
| `skills/_shared/url_utils.py` | 100% | 100%+ | ✅ |

### Script Coverage

**High Coverage (>90%)**
| Module | Coverage |
|--------|----------|
| `skills/mine-mine/scripts/discover/errors.py` | 100% |
| `skills/mine-mine/scripts/discover/types.py` | 100% |
| `skills/mine-mine/scripts/discover/cli_ui.py` | 96% |
| `skills/mine-mine/scripts/discover/config.py` | 96% |

**Medium Coverage (50-89%)**
| Module | Coverage |
|--------|----------|
| `skills/mine-mine/scripts/discover/markers.py` | 88% |
| `skills/mine-mine/scripts/transaction.py` | 85% |
| `skills/mine-mine/scripts/discover/scanner.py` | 77% |
| `skills/mine-mine/scripts/discover/main.py` | 76% |
| `skills/mine-mine/scripts/discover/registry.py` | 73% |
| `skills/mine-mine/scripts/_init_shared.py` | 70% |
| `skills/mine/scripts/agentic_discovery.py` | 65% |
| `skills/mine/scripts/convert_framework.py` | 56% |
| `skills/mine/scripts/import_assets.py` | 55% |
| `skills/mine-mine/scripts/update_integrations.py` | 53% |
| `skills/mine-mine/scripts/git_helpers.py` | 52% |

**Low Coverage (<50%)** - *Future Improvement Targets*
| Module | Coverage |
|--------|----------|
| `skills/mine/scripts/scan_repo.py` | 46% |
| `skills/mine-mine/scripts/cache_eviction.py` | 31% |
| `skills/mine-mine/scripts/discover_integrations.py` | 31% |
| `skills/mine/scripts/agentic_provenance.py` | 18% |
| `skills/mine/scripts/generate_skillpack.py` | 16% |
| `skills/mine/scripts/agentic_converter.py` | 13% |
| `skills/mine/scripts/agentic_classifier.py` | 10% |
| `skills/mine-mine/scripts/discover/unregister.py` | 6% |

---

## CI Status

| Check | Status |
|-------|--------|
| Tests (Ubuntu/macOS/Windows) | ![CI](https://github.com/uhl-solutions/MINE/actions/workflows/ci.yml/badge.svg) |
| Lint (ruff) | Included in CI |
| Security Checks | Token-in-URL, non-atomic writes, shell=True |

---

## Test Distribution

- **25+ test files** covering:
  - Secret redaction (including custom Azure/AWS patterns)
  - Path safety, traversal prevention, and symlink handling
  - Atomic I/O operations and lock safety
  - Git helpers, authentication, and ASKPASS integration
  - Framework detection
  - Import/update safety
  - End-to-end golden tests for workflows

---

## Build Metrics

| Metric | Status |
|--------|--------|
| Dist Determinism | Verified via `build_dist.py --verify` |
| Tests Excluded | Yes (dist only includes runtime files) |
| CI Artifacts Excluded | Yes |

---

## Security Signals

- [x] Token-in-URL pattern detection (CI)
- [x] Non-atomic write detection (CI)
- [x] Shell injection prevention (`shell=True` blocked)
- [x] Private key detection (pre-commit)

---

*Last updated: 2026-01-08*
