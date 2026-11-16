"""Root conftest: puts the repo root on sys.path so `agent_app` imports
as a top-level package under any pytest invocation (the bare `pytest`
console script does not add the working directory to sys.path the way
`python -m pytest` does).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
