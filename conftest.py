import sys
from pathlib import Path

# Put the repo root on sys.path so tests can import config and the src package.
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
