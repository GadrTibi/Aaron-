import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.views import estimation


def test_default_radius_value():
    assert estimation.DEFAULT_RADIUS_M == 300
