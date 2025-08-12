import math
import os
import tempfile
from typing import Tuple


def build_static_map(lat: float, lon: float, radius_m: int = 300, size: Tuple[int, int] = (600, 600)) -> str:
    """Generate a static map image centered on (lat, lon).

    The map uses OpenStreetMap tiles, draws a red pin at the center and a
    translucent circle of `radius_m` metres around it. Returns the path to the
    generated temporary PNG file.
    """

    try:
        from staticmap import StaticMap, CircleMarker, Polygon
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "The 'staticmap' package is required to build map images. Install it with 'pip install staticmap'."
        ) from e

    m = StaticMap(size[0], size[1])
    m.add_marker(CircleMarker((lon, lat), 'red', 12))

    # approximate circle in geographic coordinates
    lat_radius = radius_m / 111_320.0
    lon_radius = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    pts = []
    for deg in range(0, 360, 15):
        rad = math.radians(deg)
        pts.append((lon + lon_radius * math.cos(rad), lat + lat_radius * math.sin(rad)))
    m.add_polygon(Polygon(pts, '#ff000040', '#ff0000'))

    image = m.render()
    fd, path = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    image.save(path)
    return path

