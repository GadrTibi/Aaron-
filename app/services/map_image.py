import os
import math
import tempfile
from typing import Optional, Tuple

try:
    from staticmap import StaticMap, CircleMarker, Polygon
except Exception:  # pragma: no cover - optional dependency
    StaticMap = CircleMarker = Polygon = None


def _circle_coords(lat: float, lon: float, radius_m: float, steps: int = 36):
    lat_rad = math.radians(lat)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(lat_rad)
    coords = []
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        dlat = (radius_m * math.sin(angle)) / m_per_deg_lat
        dlon = (radius_m * math.cos(angle)) / m_per_deg_lon
        coords.append((lon + dlon, lat + dlat))
    return coords


def build_static_map(
    lat: float,
    lon: float,
    radius_m: float = 300,
    size: Tuple[int, int] = (600, 600),
) -> Optional[str]:
    """Generate a static map PNG around ``lat``/``lon`` with a red marker and circle.

    Returns the path to a temporary PNG file.
    """
    if StaticMap is None or CircleMarker is None or Polygon is None:
        return None

    m = StaticMap(size[0], size[1])
    m.add_marker(CircleMarker((lon, lat), "red", 12))
    circle = Polygon(
        _circle_coords(lat, lon, radius_m),
        fill_color=(255, 0, 0, 60),
        outline_color=(255, 0, 0, 60),
    )
    m.add_polygon(circle)
    image = m.render(zoom=None, center=(lon, lat))
    fd, path = tempfile.mkstemp(suffix=".png"); os.close(fd)
    image.save(path)
    return path

