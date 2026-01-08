"""
conftest.py - Pytest configuration for MINE tests

Sets up import paths for skill modules.
"""

import sys
from pathlib import Path

# Add skill scripts directories to Python path
REPO_ROOT = Path(__file__).parent.parent
MINE_SCRIPTS = REPO_ROOT / "skills" / "mine" / "scripts"
MINE_MINE_SCRIPTS = REPO_ROOT / "skills" / "mine-mine" / "scripts"
SHARED_SCRIPTS = REPO_ROOT / "skills" / "_shared"

sys.path.insert(0, str(MINE_MINE_SCRIPTS))
sys.path.insert(0, str(MINE_SCRIPTS))
sys.path.insert(0, str(SHARED_SCRIPTS))
