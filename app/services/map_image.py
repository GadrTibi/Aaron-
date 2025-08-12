import math
import os
import tempfile
from typing import Tuple

from staticmap import StaticMap, CircleMarker, Line

EARTH_RADIUS = 6371000  # in meters

def _circle_coordinates(lat: float, lon: float, radius_m: int, segments: int = 36) -> list[Tuple[float, float]]:
    coords = []
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    d = radius_m / EARTH_RADIUS
    for deg in range(0, 360, int(360 / segments)):
        brng = math.radians(deg)
        lat2 = math.asin(math.sin(lat_rad) * math.cos(d) + math.cos(lat_rad) * math.sin(d) * math.cos(brng))
        lon2 = lon_rad + math.atan2(
            math.sin(brng) * math.sin(d) * math.cos(lat_rad),
            math.cos(d) - math.sin(lat_rad) * math.sin(lat2)
        )
        coords.append((math.degrees(lon2), math.degrees(lat2)))
    coords.append(coords[0])
    return coords

def build_static_map(lat: float, lon: float, radius_m: int = 300, size=(600, 600)) -> str:
    """
    Génére un PNG OSM centré sur (lat, lon) avec un marqueur rouge et un cercle radius_m.
    Retourne le chemin du PNG temporaire.
    """
    m = StaticMap(size[0], size[1])
    m.add_marker(CircleMarker((lon, lat), "#ff0000", 12))
    circle_coords = _circle_coordinates(lat, lon, radius_m)
    m.add_line(Line(circle_coords, "#ff0000", 2))
    image = m.render()
    fd, path = tempfile.mkstemp(suffix=".png"); os.close(fd)
    image.save(path)
    return path
