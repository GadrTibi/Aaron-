"""Command-line utility to exercise the POI pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.poi_fetcher import POIService, LOGGER


def _main() -> None:
    parser = argparse.ArgumentParser(description="Test the POI fetching pipeline")
    parser.add_argument("--lat", type=float, required=True, help="Latitude in decimal degrees")
    parser.add_argument("--lon", type=float, required=True, help="Longitude in decimal degrees")
    parser.add_argument("--radius", type=int, default=1200, help="Search radius in metres")
    parser.add_argument(
        "--category",
        type=str,
        required=True,
        choices=["transport", "incontournables", "spots", "lieux_a_visiter"],
        help="POI category to request",
    )
    parser.add_argument("--lang", type=str, default="fr", help="Language (used for Wikipedia fallback)")
    args = parser.parse_args()

    service = POIService()
    items = service.get_pois(args.lat, args.lon, radius_m=args.radius, category=args.category, lang=args.lang)
    result = service.last_result

    provider = result.provider if result else ""
    endpoint = result.endpoint if result else None
    status = result.status if result else None
    duration = result.duration_ms if result else None

    LOGGER.info(
        "cli | category=%s | lat=%.6f | lon=%.6f | radius=%s | provider=%s | endpoint=%s | status=%s | duration_ms=%s | items=%s",
        args.category,
        args.lat,
        args.lon,
        args.radius,
        provider,
        endpoint,
        status,
        duration,
        len(items),
    )

    print("=== POI Test Report ===")
    print(f"Category : {args.category}")
    print(f"Coordinates : ({args.lat:.6f}, {args.lon:.6f})")
    print(f"Radius : {args.radius} m")
    print(f"Language : {args.lang}")
    print(f"Provider : {provider or 'n/a'}")
    print(f"Endpoint : {endpoint or 'n/a'}")
    print(f"HTTP status : {status or 'n/a'}")
    print(f"Duration : {duration:.1f} ms" if duration is not None else "Duration : n/a")
    print(f"Items : {len(items)}")

    def _main_tag(entry: Dict[str, Any]) -> str:
        tags = entry.get("tags") or {}
        for key in ("tourism", "amenity", "historic", "leisure", "public_transport", "railway"):
            if key in tags:
                return f"{key}={tags[key]}"
        return ""

    for idx, entry in enumerate(items[:3], start=1):
        name = entry.get("name") or _main_tag(entry) or f"POI {idx}"
        lat = entry.get("lat")
        lon = entry.get("lon")
        distance = entry.get("distance")
        tag = _main_tag(entry)
        print(
            f"#{idx}: {name} | lat={lat} lon={lon} | distance={distance:.0f} m" if isinstance(distance, (int, float)) else f"#{idx}: {name} | lat={lat} lon={lon}"
            + (f" | {tag}" if tag else "")
        )

    print("\nChecklist :")
    print("[ ] Overpass OK → nb items > 0 pour 2–3 tests (Paris/Eiffel etc.)")
    print("[ ] Si Overpass down → Wikipedia se déclenche (provider=wikipedia), nb items > 0")
    print("[ ] Rotation miroirs testée (au moins 2 endpoints pingés)")
    print("[ ] Cache out/cache/poi/ écrit et lu (hit en 2e appel)")
    print("[ ] UI affiche un message doux si 0 item et propose rayon ↑")


if __name__ == "__main__":
    _main()

