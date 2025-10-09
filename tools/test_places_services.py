from __future__ import annotations

import argparse
from services.places_geoapify import GeoapifyPlacesService
from services.places_otm import OpenTripMapService


def _print_preview(title: str, count: int, items: list[object]) -> None:
    print(f"\n[{title}] {count} résultat(s)")
    for item in items[:5]:
        name = getattr(item, "name", "?")
        distance = getattr(item, "distance_m", 0.0)
        print(f" - {name} ({distance:.0f} m)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test Geoapify/OpenTripMap services")
    parser.add_argument("--lat", type=float, required=True, help="Latitude de la zone")
    parser.add_argument("--lon", type=float, required=True, help="Longitude de la zone")
    parser.add_argument("--radius", type=int, default=1500, help="Rayon de recherche en mètres")
    args = parser.parse_args(argv)

    try:
        geo_service = GeoapifyPlacesService()
    except ValueError as exc:
        print(f"Geoapify indisponible: {exc}")
        geo_service = None

    try:
        otm_service = OpenTripMapService()
    except ValueError as exc:
        print(f"OpenTripMap indisponible: {exc}")
        otm_service = None

    if geo_service:
        incontournables = geo_service.list_incontournables(args.lat, args.lon, args.radius, limit=15)
        spots = geo_service.list_spots(args.lat, args.lon, args.radius, limit=10)
        _print_preview("Incontournables", len(incontournables), incontournables)
        _print_preview("Spots", len(spots), spots)

    if otm_service:
        visits = otm_service.list_visits(args.lat, args.lon, args.radius, limit=10)
        _print_preview("Visits", len(visits), visits)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
