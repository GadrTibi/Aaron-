from __future__ import annotations

import argparse

from services import image_service, poi_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Wikimedia POI pipeline")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=int, default=1200)
    parser.add_argument("--lang", type=str, default="fr")
    parser.add_argument(
        "--category",
        type=str,
        choices=["transport", "incontournables", "spots", "lieux_a_visiter"],
        default="lieux_a_visiter",
    )
    args = parser.parse_args()

    pois = poi_service.get_pois(args.lat, args.lon, args.radius, args.category, lang=args.lang)
    provider_label = f"provider=\"wikipedia\", nb_pages={len(pois)}"
    print(provider_label)
    print(f"nb_poi_filtrés={len(pois)}")
    for poi in pois[:3]:
        candidates = image_service.candidate_images(poi["pageid"], poi.get("qid"), lang=args.lang)
        print(f"- {poi['display']} → {len(candidates)} image(s)")

    if pois:
        poi = pois[0]
        candidates = image_service.candidate_images(poi["pageid"], poi.get("qid"), lang=args.lang)
        if not candidates:
            candidates = [{"url": image_service.ensure_placeholder(), "provider": "placeholder"}]
        chosen = candidates[0]
        slug = image_service.slugify(poi["display"])
        local_path = image_service.download_image(chosen["url"], slug)
        print(f"Image téléchargée pour {poi['display']} → {local_path}")

    print("\nChecklist:")
    print("- [ ] GeoSearch renvoie >0 pages (Tour Eiffel, radius 1200 m)")
    print("- [ ] Catégorisation fonctionne (incontournables/spots/transport)")
    print("- [ ] Pour un POI, 1–5 images candidates listées")
    print("- [ ] Téléchargement image → fichier >5KB sous out/images/poi/")
    print("- [ ] UI Estimation montre les vignettes et enregistre le choix → PPTX injecte l’image choisie")


if __name__ == "__main__":
    main()
