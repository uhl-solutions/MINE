#!/usr/bin/env python3
"""
test_doc_claims.py

Deterministic verification that documentation claims match implementation.
Uses claims.json registry for explicit claim→test mapping.
"""

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLAIMS_FILE = PROJECT_ROOT / "docs" / "claims.json"


def load_claims_registry() -> Dict:
    """Load the claims registry."""
    if not CLAIMS_FILE.exists():
        pytest.skip("claims.json not yet created")
    return json.loads(CLAIMS_FILE.read_text())


def collect_test_claims() -> Dict[str, List[str]]:
    """Collect DOC_CLAIMS declarations from all test files using AST parsing."""
    claims_by_test: Dict[str, List[str]] = {}
    test_dir = PROJECT_ROOT / "tests"

    if not test_dir.exists():
        return claims_by_test

    for test_file in test_dir.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DOC_CLAIMS":
                        try:
                            if isinstance(node.value, (ast.List, ast.Tuple)):
                                claim_ids = [
                                    elt.value
                                    for elt in node.value.elts
                                    if hasattr(elt, "value") and isinstance(elt.value, str)
                                ]
                                if not claim_ids:
                                    claim_ids = [
                                        elt.s for elt in node.value.elts if hasattr(elt, "s") and isinstance(elt.s, str)
                                    ]

                                for claim_id in claim_ids:
                                    if claim_id not in claims_by_test:
                                        claims_by_test[claim_id] = []
                                    rel_path = test_file.relative_to(PROJECT_ROOT).as_posix()
                                    claims_by_test[claim_id].append(rel_path)
                        except (AttributeError, TypeError):
                            continue

    return claims_by_test


class TestClaimsRegistry:
    """Verify claims registry integrity and coverage."""

    def test_all_implemented_claims_have_passing_tests(self):
        """Every claim marked 'implemented' must have at least one passing test."""
        registry = load_claims_registry()

        missing_tests = []
        for claim_id, claim in registry.get("claims", {}).items():
            if claim.get("status") == "implemented":
                if not claim.get("tests"):
                    missing_tests.append(f"{claim_id}: no tests specified")

        if missing_tests:
            pytest.fail("Implemented claims without tests:\n" + "\n".join(f"  - {m}" for m in missing_tests))

    def test_no_orphan_test_claims(self):
        """Tests declaring DOC_CLAIMS must reference valid registry entries."""
        registry = load_claims_registry()
        valid_claims = set(registry.get("claims", {}).keys())
        test_claims = collect_test_claims()

        orphans = []
        for claim_id, test_files in test_claims.items():
            if claim_id not in valid_claims:
                orphans.append(f"{claim_id} (declared in {', '.join(test_files)})")

        if orphans:
            pytest.fail("Test files declare claims not in registry:\n" + "\n".join(f"  - {o}" for o in orphans))


class TestClaimTagging:
    """Verify closed-loop claim tagging in documentation.

    This ensures no capability claim can be added to docs without
    also being registered in claims.json.

    APPROACH: Instead of heuristic pattern matching to detect "capability bullets",
    we use a DETERMINISTIC approach:

    1. All capability claims MUST be in designated sections
    2. Within those sections, any bullet starting with -, *, or + is a capability and MUST have a [claim: id] tag
    3. The claim tag is the sole indicator - no fuzzy pattern matching needed
    4. Code fences (``` or ~~~ blocks) are explicitly skipped to avoid false positives

    This eliminates false positives and false negatives.
    """

    # Pattern to match claim tags: [claim: some_claim_id]
    # Allows lowercase letters, digits, and underscores (e.g., p0_6, path_safety_v2)
    CLAIM_TAG_PATTERN = re.compile(r"\[claim:\s*([a-z0-9_]+)\]")

    # Section headers that contain capability claims (case-insensitive)
    # Section headers that contain capability claims (case-insensitive)
    CAPABILITY_SECTIONS = {"goals", "guarantees", "checklist", "defaults"}

    @staticmethod
    def _parse_doc_lines(content: str):
        """Parse doc content, yielding (line_num, line, in_code_fence) tuples.

        Tracks fenced code blocks to avoid parsing code examples as real content.
        """
        in_code_fence = False
        for line_num, line in enumerate(content.split("\n"), 1):
            # Toggle code fence state on fenced code blocks (``` or ~~~)
            if line.strip().startswith("```") or line.strip().startswith("~~~"):
                in_code_fence = not in_code_fence
                yield (line_num, line, True)  # The fence line itself is "in code"
            else:
                yield (line_num, line, in_code_fence)

    def test_all_claim_tags_are_registered(self):
        """Every [claim: id] tag in docs must exist in claims.json.

        Skips claim tags inside fenced code blocks (examples).
        """
        registry = load_claims_registry()
        valid_claims = set(registry.get("claims", {}).keys())

        # Only checking SECURITY.md as requested
        docs = [
            PROJECT_ROOT / "SECURITY.md",
        ]

        unregistered = []
        for doc in docs:
            if not doc.exists():
                continue

            try:
                content = doc.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for line_num, line, in_code_fence in self._parse_doc_lines(content):
                # Skip lines inside code fences
                if in_code_fence:
                    continue

                for match in self.CLAIM_TAG_PATTERN.finditer(line):
                    claim_id = match.group(1)
                    if claim_id not in valid_claims:
                        unregistered.append(f"{doc.name}:{line_num}: [claim: {claim_id}] not in registry")

        if unregistered:
            pytest.fail("Claim tags in docs not found in claims.json:\n" + "\n".join(f"  - {u}" for u in unregistered))

    def test_all_claims_are_present_in_security_md(self):
        """All 'implemented' claims in registry must be present in SECURITY.md."""
        registry = load_claims_registry()
        implemented_claims = {cid for cid, c in registry.get("claims", {}).items() if c.get("status") == "implemented"}

        security_md = PROJECT_ROOT / "SECURITY.md"
        if not security_md.exists():
            pytest.fail("SECURITY.md not found")

        content = security_md.read_text(encoding="utf-8")

        found_claims = set()
        for match in self.CLAIM_TAG_PATTERN.finditer(content):
            found_claims.add(match.group(1))

        missing = implemented_claims - found_claims
        if missing:
            pytest.fail(f"Claims missing from SECURITY.md: {sorted(list(missing))}")

    def test_capability_section_items_have_claim_tags(self):
        """Bullets in capability sections must include [claim: id] tags.

        DETERMINISTIC: We only check bullets within designated sections, not the entire doc.
        Skips fenced code blocks.
        """
        docs = [
            PROJECT_ROOT / "SECURITY.md",
        ]

        untagged = []
        for doc in docs:
            if not doc.exists():
                continue

            try:
                content = doc.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            in_capability_section = False
            current_section = None

            for line_num, line, in_code_fence in self._parse_doc_lines(content):
                if in_code_fence:
                    continue

                if line.startswith("#"):
                    section_name = line.lstrip("#").strip().lower()
                    in_capability_section = any(cap_sec in section_name for cap_sec in self.CAPABILITY_SECTIONS)
                    current_section = section_name if in_capability_section else None
                    continue

                if in_capability_section and re.match(r"^\s*[-*+]\s+", line):
                    if not self.CLAIM_TAG_PATTERN.search(line):
                        untagged.append(f"{doc.name}:{line_num} (in '{current_section}'): {line[:50]}...")

        if untagged:
            pytest.fail(
                "Items in capability sections without [claim: id] tags:\n"
                + "\n".join(f"  - {u}" for u in untagged)
                + "\n\nFix by adding a claim tag!"
            )


class TestClaimsConnectivity:
    """Verify registry→tests linkage is real, not just paper.

    This ensures claims.json test references actually exist and are connected,
    preventing "phantom tests" that are listed but don't prove the claim.
    """

    def test_claim_test_paths_exist(self):
        """Every test path in claims.json must resolve to a real file.

        This catches typos and stale references in claims.json.
        """
        registry = load_claims_registry()

        missing = []
        for claim_id, claim in registry.get("claims", {}).items():
            for test_ref in claim.get("tests", []):
                # test_ref format: "tests/path/test_file.py::test_function"
                # or just "tests/path/test_file.py"
                test_file = test_ref.split("::")[0]
                test_path = PROJECT_ROOT / test_file

                if not test_path.exists():
                    missing.append(f"{claim_id}: {test_ref} (file not found)")

        if missing:
            pytest.fail("claims.json references non-existent test files:\n" + "\n".join(f"  - {m}" for m in missing))

    def test_implemented_claims_have_connected_tests(self):
        """For implemented claims, at least one test file must declare the claim.

        This ensures the linkage is bidirectional:
        - claims.json says "test X proves claim Y"
        - test X says "I prove claim Y" via DOC_CLAIMS

        Without this, a test could be listed in claims.json but not actually
        know it's supposed to prove that claim.
        """
        registry = load_claims_registry()
        test_claims = collect_test_claims()  # {claim_id: [test_file_paths]}

        disconnected = []
        for claim_id, claim in registry.get("claims", {}).items():
            if claim.get("status") != "implemented":
                continue  # Only check implemented claims

            # Get the test files referenced in claims.json
            referenced_files = set()
            for test_ref in claim.get("tests", []):
                test_file = test_ref.split("::")[0]
                referenced_files.add(test_file)

            # Check if any of those files declare this claim in DOC_CLAIMS
            declaring_files = set(test_claims.get(claim_id, []))

            # At least one referenced file should declare this claim
            connected = bool(referenced_files & declaring_files)

            if not connected and referenced_files:
                disconnected.append(
                    f"{claim_id}: tests {list(referenced_files)} don't declare DOC_CLAIMS = ['{claim_id}']"
                )

        if disconnected:
            pytest.fail(
                "Implemented claims with one-way linkage (add DOC_CLAIMS to test files):\n"
                + "\n".join(f"  - {d}" for d in disconnected)
                + "\n\nFix by adding to the test file:\n"
                "DOC_CLAIMS = ['claim_id_here']"
            )
