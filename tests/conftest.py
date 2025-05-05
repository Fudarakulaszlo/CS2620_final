"""
Pytest startup hook: prepend the project root to sys.path so that modules
like `algorithms.wmsr` and `comm.zmq_transport` import without requiring
`pip install -e .`.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
