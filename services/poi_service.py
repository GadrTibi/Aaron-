"""Utilities to retrieve and prepare POIs from Wikimedia."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import requests

from . import wiki_client

HEADERS = wiki_client.HEADERS
GEO_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_CACHE_DIR = Path("out/cache/geo/rev")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL_SECONDS = 30 * 24 * 3600

_CATEGORY_REGEX: Dict[str, Iterable[re.Pattern[str]]] = {
    "transport": [
        re.compile(r"\b(gare|station|metro|métro|tram|bus|railway|airport|aéroport|train|subway)\b", re.I),
        re.compile(r"transport", re.I),
    ],
    "incontournables": [
        re.compile(r"(monument|patrimoine|world heritage|unesco|historic|cath(é|e)dral|basilique)", re.I),
        re.compile(r"(musée|museum|palace|palais|tourisme incontournable)", re.I),
    ],
    "spots": [
        re.compile(r"(panorama|view|belvédère|lookout|promenade|parc|park|square|esplanade)", re.I),
        re.compile(r"(photograph|instagram|spot)", re.I),
    ],
    "lieux_a_visiter": [
        re.compile(r"(tourisme|visitor attraction|landmark|site touristique)", re.I),
        re.compile(r"(château|castle|abbaye|zoo|aquarium|jardin|garden)", re.I),
    ],
}

_CATEGORY_PRIORITY = {
    "incontournables": 0,
    "lieux_a_visiter": 0,
    "spots": 1,
    "transport": 2,
}
def _geo_cache_path(lat: float, lon: float, lang: str) -> Path:
    key = f"{lat:.5f}_{lon:.5f}_{lang}"
    return _CACHE_DIR / f"{key}.json"


def reverse_geocode(lat: float, lon: float, lang: str = "fr") -> Optional[str]:
    cache_path = _geo_cache_path(lat, lon, lang)
    now = time.time()
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if now - raw.get("timestamp", 0) < _CACHE_TTL_SECONDS:
                return raw.get("city")
        except (OSError, json.JSONDecodeError):
            cache_path.unlink(missing_ok=True)
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "accept-language": lang,
    }
    response = requests.get(
        GEO_REVERSE_URL,
        params=params,
        headers={**HEADERS, "User-Agent": HEADERS.get("User-Agent", "")},
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    address = data.get("address", {}) if isinstance(data, dict) else {}
    city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
    if city:
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump({"city": city, "timestamp": now}, fh, ensure_ascii=False)
    return city


def categorize_from_categories(categories: List[str]) -> Set[str]:
    matches: Set[str] = set()
    for category in categories:
        lowered = category.lower()
        for key, patterns in _CATEGORY_REGEX.items():
            if any(pattern.search(lowered) for pattern in patterns):
                matches.add(key)
    return matches


def _extract_page_categories(page: Dict[str, any]) -> List[str]:
    result: List[str] = []
    for cat in page.get("categories", []) or []:
        title = cat.get("title")
        if title:
            result.append(title)
    return result


def _extract_coords(page: Dict[str, any]) -> Optional[Dict[str, float]]:
    coords = page.get("coordinates")
    if not coords:
        return None
    coord = coords[0]
    lat = coord.get("lat")
    lon = coord.get("lon")
    if lat is None or lon is None:
        return None
    return {"lat": float(lat), "lon": float(lon)}


def get_pois(lat: float, lon: float, radius_m: int, category: str, lang: str = "fr") -> List[Dict[str, any]]:
    geodata = wiki_client.geosearch(lat, lon, radius_m, lang=lang)
    geolist = geodata.get("query", {}).get("geosearch", [])
    if not geolist:
        return []

    pageid_to_geo = {item["pageid"]: item for item in geolist}
    pageids = list(pageid_to_geo.keys())

    details: Dict[str, Dict[str, any]] = {}
    for idx in range(0, len(pageids), 50):
        chunk = pageids[idx : idx + 50]
        detail_data = wiki_client.page_details(chunk, lang=lang)
        pages = detail_data.get("query", {}).get("pages", {})
        for pid, pdata in pages.items():
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue
            details[pid_int] = pdata

    city = reverse_geocode(lat, lon, lang=lang)

    pois: List[Dict[str, any]] = []
    for pid, geoitem in pageid_to_geo.items():
        page = details.get(pid)
        if not page:
            continue
        categories = _extract_page_categories(page)
        matched = categorize_from_categories(categories)
        if category not in matched:
            continue
        coords = _extract_coords(page) or {"lat": geoitem.get("lat"), "lon": geoitem.get("lon")}
        title = page.get("title") or geoitem.get("title") or ""
        display = title
        if city:
            display = f"{title} — {city}"
        qid = None
        pageprops = page.get("pageprops") or {}
        if isinstance(pageprops, dict):
            qid = pageprops.get("wikibase_item")
        pois.append(
            {
                "pageid": pid,
                "title": title,
                "display": display,
                "lat": float(coords.get("lat")) if coords and coords.get("lat") is not None else None,
                "lon": float(coords.get("lon")) if coords and coords.get("lon") is not None else None,
                "distance_m": float(geoitem.get("dist", 0.0)),
                "qid": qid,
                "categories": categories,
            }
        )

    def _sort_key(item: Dict[str, any]) -> tuple[float, int]:
        priority = _CATEGORY_PRIORITY.get(category, 5)
        for matched in categorize_from_categories(item.get("categories", [])):
            priority = min(priority, _CATEGORY_PRIORITY.get(matched, priority))
        return (item.get("distance_m", 0.0), priority)

    pois.sort(key=_sort_key)
    trimmed = []
    seen_titles: Set[str] = set()
    for poi in pois:
        if poi["title"] in seen_titles:
            continue
        seen_titles.add(poi["title"])
        trimmed.append({
            "pageid": poi["pageid"],
            "title": poi["title"],
            "display": poi["display"],
            "lat": poi["lat"],
            "lon": poi["lon"],
            "distance_m": poi["distance_m"],
            "qid": poi["qid"],
        })
        if len(trimmed) >= 15:
            break
    return trimmed
