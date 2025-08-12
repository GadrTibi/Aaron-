import tempfile
import os
from staticmap import StaticMap, CircleMarker
from PIL import Image, ImageDraw


def build_static_map(lat: float, lon: float, pixel_radius: int = 60, size=(900, 900)) -> str:
    """
    Renvoie le chemin d'un PNG avec une carte OSM centrée sur (lat, lon),
    un marker rouge au centre et un cercle rouge semi-transparent.
    """
    m = StaticMap(size[0], size[1])
    m.add_marker(CircleMarker((lon, lat), "red", 12))
    img = m.render(zoom=None)

    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = size[0] // 2, size[1] // 2
    r = pixel_radius
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        outline=(255, 0, 0, 255),
        width=4,
        fill=(255, 0, 0, 64),
    )

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path, format="PNG")
    return path

