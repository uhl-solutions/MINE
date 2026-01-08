# Contributing

Thanks for your interest in contributing! This document explains how to propose changes, report issues, and submit pull requests in a way that’s easy to review and safe to ship.

## Table of Contents

- [Ways to Contribute](#ways-to-contribute)
- [Before You Start](#before-you-start)
- [Project Standards](#project-standards)
- [Development Setup](#development-setup)
- [Running Checks](#running-checks)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Commit & PR Guidelines](#commit--pr-guidelines)
- [Security Issues](#security-issues)
- [Release / Versioning Notes](#release--versioning-notes)
- [License](#license)

## Ways to Contribute

You can help by:

- Reporting bugs or confusing behavior
- Improving documentation and examples
- Adding tests (especially for edge cases)
- Implementing new features
- Refactoring for clarity/performance while keeping behavior stable
- Reviewing pull requests and issues

If you’re unsure where to start, look for issues labeled **good first issue**, **help wanted**, or **docs**.

## Before You Start

### Check existing work
Before opening a new issue or PR, please:

- Search existing issues and PRs for duplicates
- Skim the README and docs for relevant guidance
- If proposing a larger change, open an issue first to discuss approach and scope

### Be kind
This project follows the [Code of Conduct](./docs/CODE_OF_CONDUCT.md). By participating, you agree to follow it.

## Project Standards

We aim for:

- **Safety by default** (especially around IO, parsing, and inputs)
- **Clear behavior** with good error messages
- **Strong test coverage** for user-facing and security-sensitive code paths
- **Minimal surprises**: avoid breaking changes unless discussed

### Design principles
- Prefer **simple, explicit code** over cleverness.
- Validate inputs early and fail with actionable errors.
- Avoid introducing new dependencies unless there’s a strong reason.
- Keep public APIs stable; document changes when behavior changes.

## Development Setup

> The commands below assume you’re using Python and standard tooling. If your repo uses a different runner, align these commands with the project’s README.

1. **Fork** the repository and clone your fork:
   ```bash
   git clone https://github.com/<you>/<repo>.git
   cd <repo>
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # .venv\Scripts\activate   # Windows
   ```

3. **Install dependencies**:
   ```bash
   python -m pip install -U pip
   pip install -r requirements-dev.txt
   ```

4. **Install pre-commit hooks** (recommended):
   ```bash
   pre-commit install
   ```

## Running Checks

Run formatting, linting, and type checks (if configured):

```bash
pre-commit run --all-files
```

If you don’t use pre-commit, run the underlying tools directly (see `.pre-commit-config.yaml`).

## Testing

Run the full test suite:

```bash
pytest
```

Tips:
- Add or update tests for any behavior change.
- Prefer tests that prove behavior from the *public surface area* (CLI/API) unless testing an internal invariant.
- For security-sensitive behavior (e.g., path handling, file IO), include tests for:
  - traversal attempts
  - symlink edge cases (where applicable)
  - permission errors / read-only paths
  - invalid encodings / weird filenames

## Submitting a Pull Request

1. Create a branch from `main`:
   ```bash
   git checkout -b your-branch-name
   ```

2. Make your change with tests and docs updates.
3. Ensure checks pass:
   ```bash
   pre-commit run --all-files
   pytest
   ```

4. Push your branch:
   ```bash
   git push origin your-branch-name
   ```

5. Open a PR and fill out the template (below).

### PR checklist (please include in the PR body)

- [ ] I linked to the relevant issue (or explained why it’s not needed)
- [ ] I added/updated tests
- [ ] I updated docs / README (if needed)
- [ ] I ran `pre-commit run --all-files`
- [ ] I ran `pytest`
- [ ] I considered backwards compatibility and error messaging
- [ ] I did not add unnecessary dependencies

## Commit & PR Guidelines

### Commits
- Use clear, descriptive commit messages.
- Keep unrelated changes separate when possible.

### PR size & scope
- Smaller PRs merge faster. If a change is large, consider splitting it:
  - refactor (no behavior change)
  - behavior change + tests
  - docs/examples

### Style
- Follow the existing style and patterns in the codebase.
- Keep functions focused.
- Prefer explicit types and docstrings where they improve clarity.

## Security Issues

Please **do not** open public issues for security vulnerabilities.

Instead, follow the guidance in [SECURITY.md](./SECURITY.md). If no security process exists yet, email the maintainers privately with:

- a description of the issue
- steps to reproduce
- impact assessment
- suggested fix (if you have one)

We will coordinate a fix and disclosure timeline.

## Release / Versioning Notes

- This project aims to follow **semantic versioning** (SemVer) where feasible:
  - **MAJOR**: breaking changes
  - **MINOR**: backward-compatible feature additions
  - **PATCH**: backward-compatible bug fixes

If your PR changes user-facing behavior, include a short note in the PR describing:
- what changed
- why
- upgrade / migration notes (if any)

If the repo includes build or dist-manifest checks, ensure distribution artifacts remain clean and deterministic.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see [LICENSE](./LICENSE)).
