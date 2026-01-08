import sys
from pathlib import Path

# Locate skills directory relative to this script
# this script: skills/mine-mine/scripts/_init_shared.py
# parent: skills/mine-mine/scripts
# parent.parent: skills/mine-mine
# parent.parent.parent: skills
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SHARED_DIR = SKILLS_DIR / "_shared"

if str(SHARED_DIR) not in sys.path:
    # Insert at beginning to ensure shared modules are found first
    sys.path.insert(0, str(SHARED_DIR))

# Import bootstrap to ensure it runs its setup logic too
try:
    import _bootstrap
except ImportError:
    pass
