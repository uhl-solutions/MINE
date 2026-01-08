# MINE - Makefile for common development commands
# Usage: make <target>

.PHONY: help lint format test coverage build dist-verify clean install-hooks

# Default target
help:
	@echo "MINE Development Commands"
	@echo "========================="
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Run ruff formatter"
	@echo "  make test         - Run tests with coverage"
	@echo "  make coverage     - Generate HTML coverage report"
	@echo "  make build        - Build distribution"
	@echo "  make dist-verify  - Verify distribution contents"
	@echo "  make clean        - Remove build artifacts"
	@echo "  make install-hooks - Install pre-commit hooks"

# Linting
lint:
	ruff check skills/ tests/

# Formatting
format:
	ruff format skills/ tests/

# Run tests with coverage
test:
	python -m pytest tests/ -v --cov=skills --cov-report=term-missing

# Generate HTML coverage report
coverage:
	python -m pytest tests/ -v --cov=skills --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# Build distribution
build:
	python scripts/build_dist.py --manifest config/dist-manifest.json --output dist/ --clean

# Verify distribution
dist-verify:
	python scripts/build_dist.py --manifest config/dist-manifest.json --output dist/ --verify --clean

# Clean build artifacts
clean:
	rm -rf dist/ htmlcov/ .coverage coverage.xml .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Install pre-commit hooks
install-hooks:
	pip install pre-commit
	pre-commit install
	@echo "Pre-commit hooks installed!"
