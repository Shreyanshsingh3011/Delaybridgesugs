import os
import sys

# Make the backend modules importable (they use flat imports like `from server import db`).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from server import app  # noqa: E402,F401  (Vercel serves this ASGI `app`)
