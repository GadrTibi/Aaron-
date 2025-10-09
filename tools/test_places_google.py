from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_repo_root() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_repo_root()

from app.views.settings_keys import read_local_secret  # noqa: E402
from services.places_google import GooglePlacesService  # noqa: E402


def _format_place(name: str, distance_m: float) -> str:
    return f"{name} ({round(distance_m)} m)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Google Places integration")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--radius", type=int, default=1500, help="Search radius in meters")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run the quick nearby search around the Eiffel Tower (debug)",
    )
    args = parser.parse_args()

    api_key = read_local_secret("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("GOOGLE_MAPS_API_KEY introuvable. Configurez la clé via la page Paramètres / Clés API.")
        return

    service = GooglePlacesService(api_key)

    if args.quick:
        print("Test rapide : list_incontournables(48.8583, 2.2945, 1200, 15)")
        try:
            results = service.list_incontournables(48.8583, 2.2945, 1200, limit=15)
            for place in results[:5]:
                print("  -", _format_place(place.name, place.distance_m))
        except Exception as exc:  # pragma: no cover - network failure handling
            body = getattr(exc, "response_body", None)
            snippet = (body or str(exc))[:150]
            print(f"Erreur: {snippet}")
        return

    try:
        incontournables = service.list_incontournables(args.lat, args.lon, args.radius, limit=5)
    except Exception as exc:  # pragma: no cover - network failure handling
        print(f"Erreur lors de la récupération des incontournables: {exc}")
        incontournables = []

    try:
        spots = service.list_spots(args.lat, args.lon, args.radius, limit=5)
    except Exception as exc:  # pragma: no cover
        print(f"Erreur lors de la récupération des spots: {exc}")
        spots = []

    try:
        visits = service.list_visits(args.lat, args.lon, args.radius, limit=5)
    except Exception as exc:  # pragma: no cover
        print(f"Erreur lors de la récupération des visites: {exc}")
        visits = []

    print("\nIncontournables:")
    if incontournables:
        for place in incontournables:
            print("  -", _format_place(place.name, place.distance_m))
    else:
        print("  (aucun)")

    print("\nSpots:")
    if spots:
        for place in spots:
            print("  -", _format_place(place.name, place.distance_m))
    else:
        print("  (aucun)")

    print("\nVisites:")
    if visits:
        for place in visits:
            print("  -", _format_place(place.name, place.distance_m))
    else:
        print("  (aucun)")


if __name__ == "__main__":
    main()
