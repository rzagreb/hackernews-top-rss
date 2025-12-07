import sys
from pathlib import Path

CUR_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import src  # noqa: E402, F401
