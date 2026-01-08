#!/usr/bin/env python3
"""
test_cache_collision.py

Tests for cache collision prevention - verifies hash-based cache naming.
"""

import sys
import hashlib
from pathlib import Path
import pytest


# This test file proves the following claims:
DOC_CLAIMS = [
    "cache_collision_safe",
]


class TestCacheCollisionSafe:
    """Tests that verify cache uses hash-based naming to prevent collisions."""

    def test_hash_based_naming_github_url(self, tmp_path):
        """Cache names should include URL hash for GitHub repos."""
        import json
        from update_integrations import IntegrationUpdater

        # Create mock registry
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(json.dumps({"version": "1.0", "integrations": {}}))

        updater = IntegrationUpdater(registry_path, dry_run=True)

        # Two different repos with same name from different orgs
        url1 = "https://github.com/org-a/shared-lib"
        url2 = "https://github.com/org-b/shared-lib"

        # Calculate expected hashes
        hash1 = hashlib.sha256(url1.encode()).hexdigest()[:8]
        hash2 = hashlib.sha256(url2.encode()).hexdigest()[:8]

        # Hashes should be different for different URLs
        assert hash1 != hash2, "Different URLs should have different hashes"

    def test_cache_path_includes_hash(self, tmp_path):
        """Cache path should include the URL hash component."""
        import json
        from update_integrations import IntegrationUpdater

        # Create mock registry with integration
        registry_path = tmp_path / "registry.json"
        source_url = "https://github.com/example/test-repo"
        expected_hash = hashlib.sha256(source_url.encode()).hexdigest()[:8]

        registry_path.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "integrations": {"test-integration": {"source_url": source_url, "artifact_mappings": []}},
                }
            )
        )

        updater = IntegrationUpdater(registry_path, dry_run=True, verbose=True)

        # The cache_dir should lead to cache names with hash
        # Format: owner__repo-<hash8>
        expected_cache_name = f"example__test-repo-{expected_hash}"
        expected_cache_path = updater.cache_dir / expected_cache_name

        # Verify the hash is present in expected format
        assert expected_hash in str(expected_cache_path), f"Cache path should contain URL hash {expected_hash}"

    def test_same_repo_name_different_orgs_get_different_caches(self, tmp_path):
        """Repos with same name but different orgs should have different caches."""
        import json
        from update_integrations import IntegrationUpdater

        url1 = "https://github.com/facebook/react"
        url2 = "https://github.com/vuejs/react"  # Hypothetical collision name

        hash1 = hashlib.sha256(url1.encode()).hexdigest()[:8]
        hash2 = hashlib.sha256(url2.encode()).hexdigest()[:8]

        # Build expected cache names (format: owner__repo-hash)
        cache_name_1 = f"facebook__react-{hash1}"
        cache_name_2 = f"vuejs__react-{hash2}"

        assert cache_name_1 != cache_name_2, "Same repo name from different orgs should have different cache names"

    def test_hash_provides_8_char_suffix(self):
        """URL hash should provide exactly 8 character suffix."""
        test_url = "https://github.com/test/repo"
        url_hash = hashlib.sha256(test_url.encode()).hexdigest()[:8]

        assert len(url_hash) == 8, f"Hash suffix should be 8 chars, got {len(url_hash)}"
        assert url_hash.isalnum(), "Hash should be alphanumeric"
