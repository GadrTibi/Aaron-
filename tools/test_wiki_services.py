"""Quick CLI for testing Wikimedia-based POI services."""
from __future__ import annotations

import argparse
import pprint
from typing import List

from services.wiki_images import WikiImageService
from services.wiki_poi import POI, WikiPOIService


def _format_poi(poi: POI) -> str:
    return f"{poi.name_display} ({poi.distance_m:.0f} m)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Wikipedia/Wikidata POI discovery")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--radius", type=int, default=1500, help="Radius in meters")
    parser.add_argument("--lang", type=str, default="fr", help="Wikipedia language")
    args = parser.parse_args()

    poi_service = WikiPOIService(lang=args.lang)
    categories = poi_service.list_by_category(args.lat, args.lon, args.radius)

    limits = {"incontournables": 15, "spots": 10, "visits": 10}
    for category, limit in limits.items():
        items: List[POI] = categories.get(category, [])
        print(f"{category} → {len(items)} items")
        for poi in items[: min(3, len(items))]:
            print("  -", _format_poi(poi))

    visits = categories.get("visits", [])
    if not visits:
        print("No visits category items available for image testing.")
        return

    visit = visits[0]
    print(f"\nFetching image candidates for: {visit.title} ({visit.qid})")
    image_service = WikiImageService(lang=args.lang)
    candidates = image_service.candidates(visit.qid, visit.title, None, None)
    pprint.pprint([candidate.to_dict() for candidate in candidates])
    if candidates:
        try:
            path = image_service.download(candidates[0].url)
            print("Downloaded candidate to:", path)
        except Exception as exc:  # pragma: no cover - interactive usage
            print("Failed to download image:", exc)


if __name__ == "__main__":
    main()
