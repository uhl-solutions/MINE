"""
Centralized path setup for MINE shared modules.
Import this ONCE at the top of any script that needs shared utilities.
"""

import sys
from pathlib import Path

# Compute path reliably regardless of working directory
_SHARED_DIR = Path(__file__).parent.resolve()


def setup_shared_imports():
    """Add _shared to sys.path if not already present."""
    shared_str = str(_SHARED_DIR)
    if shared_str not in sys.path:
        sys.path.insert(0, shared_str)


# Auto-setup on import
setup_shared_imports()

# Re-export all shared modules for convenience
