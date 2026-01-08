#!/usr/bin/env python3
"""
cache_eviction.py

Manages the repository cache to prevent unlimited growth.
Implements LRU (Least Recently Used) eviction based on last access time.
"""

import os
import shutil
from pathlib import Path

# Default limits
MAX_CACHE_SIZE_MB = 1000  # 1GB
MAX_CACHE_ITEMS = 50  # Keep max 50 repos
MIN_FREE_SPACE_MB = 500  # Ensure at least 500MB free disk space


class CacheManager:
    """Manages cache size and eviction."""

    def __init__(
        self,
        cache_dir: Path,
        max_size_mb: int = MAX_CACHE_SIZE_MB,
        max_items: int = MAX_CACHE_ITEMS,
        verbose: bool = False,
    ):
        self.cache_dir = cache_dir
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_items = max_items
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(f"[CACHE] {message}")

    def get_dir_size(self, path: Path) -> int:
        """Calculate directory size in bytes."""
        total = 0
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += self.get_dir_size(Path(entry.path))
        except OSError:
            pass
        return total

    def cleanup(self) -> int:
        """
        Enforce cache limits.
        Returns number of evicted items.
        """
        if not self.cache_dir.exists():
            return 0

        items = []
        total_size = 0

        # Scan cache items
        for item in self.cache_dir.iterdir():
            if item.is_dir():
                try:
                    stats = item.stat()
                    # Use modification time as proxy for "last used" if access time not reliable?
                    # best is to update mtime when we use it in update_integrations.
                    last_access = stats.st_mtime
                    size = self.get_dir_size(item)
                    items.append((last_access, size, item))
                    total_size += size
                except OSError:
                    continue

        # Sort by last access (oldest first)
        items.sort(key=lambda x: x[0])

        evicted_count = 0

        # Evict if too many items
        while len(items) > self.max_items:
            _, size, path = items.pop(0)
            self._evict(path)
            total_size -= size
            evicted_count += 1

        # Evict if too large
        while total_size > self.max_size_bytes and items:
            _, size, path = items.pop(0)
            self._evict(path)
            total_size -= size
            evicted_count += 1

        return evicted_count

    def _evict(self, path: Path):
        """Delete a cache item."""
        self._log(f"Evicting {path.name}...")
        try:
            shutil.rmtree(path)
        except OSError as e:
            self._log(f"Failed to evict {path.name}: {e}")

    def touch(self, repo_name: str):
        """Update last access time for a repo."""
        path = self.cache_dir / repo_name
        if path.exists():
            path.touch()


def enforce_limits(cache_dir: Path, verbose: bool = False):
    """Convenience function to run cleanup."""
    manager = CacheManager(cache_dir, verbose=verbose)
    manager.cleanup()
