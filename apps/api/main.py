import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from translator.api import app

__all__ = ["app"]
