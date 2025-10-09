import math
import requests
from typing import Any, Dict, Iterable, List, Tuple

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - streamlit not installed in tests
    st = None

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

from app.services.overpass_client import query_overpass

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def _overpass(query):
    r = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
    r.raise_for_status()
    return r.json().get("elements", [])

def fetch_pois(lat, lon, radius_m=1200):
    q = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity~"^cafe|restaurant|bar|pub$"];
  node(around:{radius_m},{lat},{lon})[tourism~"^museum|attraction$"];
  node(around:{radius_m},{lat},{lon})[leisure=park];
);
out center 60;
"""
    els = _overpass(q)
    pois = []
    for el in els:
        name = el.get("tags", {}).get("name")
        if not name: continue
        cat = el.get("tags", {}).get("amenity") or el.get("tags", {}).get("tourism") or el.get("tags", {}).get("leisure") or "poi"
        d = _haversine(lat, lon, el.get("lat"), el.get("lon"))
        pois.append({"name": name, "category": cat, "distance_m": d})
    pois.sort(key=lambda x: x["distance_m"])
    return pois[:50]

def _cache_if_available(ttl: int = 300):
    def decorator(func):
        if st is not None and hasattr(st, "cache_data"):
            return st.cache_data(ttl=ttl)(func)
        return func

    return decorator


def _extract_coords(element: Dict[str, Any]) -> Tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    center = element.get("center")
    if isinstance(center, dict):
        c_lat = center.get("lat")
        c_lon = center.get("lon")
        if c_lat is not None and c_lon is not None:
            return float(c_lat), float(c_lon)
    return None, None


def _should_retry_radius(items: Iterable[Any], debug: Dict[str, Any], attempt: int) -> bool:
    if attempt > 0:
        return False
    if debug.get("status") == "timeout":
        return True
    try:
        empty = len(items) == 0  # type: ignore[arg-type]
    except TypeError:
        empty = len(list(items)) == 0
    return empty and debug.get("status") in {"ok", "timeout"}


def _dedupe_key(lat: float | None, lon: float | None, name: str | None) -> Tuple[float | None, float | None, str | None]:
    if lat is not None:
        lat = round(lat, 7)
    if lon is not None:
        lon = round(lon, 7)
    return lat, lon, name or ""


@_cache_if_available(ttl=300)
def _fetch_transports_cached(_: str, lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return _fetch_transports_uncached(lat, lon, radius_m)


def _fetch_transports_uncached(lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    radius = max(int(radius_m), 100)
    attempt = 0
    debug: Dict[str, Any] = {}
    items: List[Dict[str, Any]] = []
    while True:
        query = (
            f"[out:json][timeout:25];\n"
            f"nwr(around:{radius},{lat},{lon})[amenity=taxi];\n"
            "out center 50;"
        )
        elements, query_debug = query_overpass(query, f"taxi_r{radius}")
        debug = {**query_debug, "radius": radius}
        seen = set()
        taxis: List[Dict[str, Any]] = []
        for element in elements:
            tags = element.get("tags") or {}
            if tags.get("amenity") != "taxi":
                continue
            name = tags.get("name") or "Station de taxi"
            lat2, lon2 = _extract_coords(element)
            if lat2 is None or lon2 is None:
                continue
            key = _dedupe_key(lat2, lon2, name)
            if key in seen:
                continue
            seen.add(key)
            distance = int(_haversine(lat, lon, lat2, lon2))
            taxis.append(
                {
                    "name": name,
                    "distance_m": distance,
                    "lat": lat2,
                    "lon": lon2,
                }
            )
        taxis.sort(key=lambda item: item["distance_m"])
        items = taxis[:5]
        debug["items"] = len(items)
        if not _should_retry_radius(items, debug, attempt):
            break
        new_radius = max(int(radius / 1.5), 80)
        if new_radius >= radius:
            break
        debug["radius_reduced"] = True
        radius = new_radius
        attempt += 1
    return items, debug


def fetch_transports(lat: float, lon: float, radius_m: int = 1500) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lat_key = round(float(lat), 5)
    lon_key = round(float(lon), 5)
    radius_key = int(radius_m)
    items, debug = _fetch_transports_cached("fetch_transports", lat_key, lon_key, radius_key)
    debug = {**debug, "items": len(items)}
    return items, debug

def suggest_places(lat, lon, radius_m=1500):
    q = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity~"^restaurant|cafe|bakery$"];
  node(around:{radius_m},{lat},{lon})[leisure~"^park|swimming_pool$"];
  node(around:{radius_m},{lat},{lon})[tourism~"^attraction|museum$"];
);
out center 200;
"""
    els = _overpass(q)
    restos, spots, visites = [], [], []
    for el in els:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name: continue
        d = _haversine(lat, lon, el.get("lat"), el.get("lon"))
        if tags.get("amenity") in ("restaurant","cafe","bakery"):
            restos.append((name, d))
        elif tags.get("leisure") in ("park","swimming_pool"):
            spots.append((name, d))
        elif tags.get("tourism") in ("attraction","museum"):
            visites.append((name, d))
    restos.sort(key=lambda x: x[1]); spots.sort(key=lambda x: x[1]); visites.sort(key=lambda x: x[1])
    return {
        "incontournables": [r[0] for r in restos[:3]],
        "spots": [s[0] for s in spots[:2]],
        "visites": [v[0] for v in visites[:2]],
    }


def _list_generic(lat: float, lon: float, radius_m: int, tag_expr: str, limit: int) -> list[str]:
    q = f"""
[out:json][timeout:25];
node(around:{radius_m},{lat},{lon})[{tag_expr}];
out center;
"""
    els = _overpass(q)
    cand = {}
    for el in els:
        name = el.get("tags", {}).get("name")
        if not name:
            continue
        d = _haversine(lat, lon, el.get("lat"), el.get("lon"))
        cur = cand.get(name)
        if cur is None or d < cur:
            cand[name] = d
    return [name for name, _ in sorted(cand.items(), key=lambda x: x[1])][:limit]


def list_incontournables(lat: float, lon: float, radius_m: int = 1200, limit: int = 15) -> list[str]:
    return _list_generic(lat, lon, radius_m, 'amenity~"^(restaurant|cafe|bakery)$"', limit)


def list_spots(lat: float, lon: float, radius_m: int = 1200, limit: int = 10) -> list[str]:
    return _list_generic(lat, lon, radius_m, 'leisure~"^(park|swimming_pool)$"', limit)


def list_visites(lat: float, lon: float, radius_m: int = 1200, limit: int = 10) -> list[str]:
    return _list_generic(lat, lon, radius_m, 'tourism~"^(attraction|museum)$"', limit)


@_cache_if_available(ttl=300)
def _list_metro_lines_cached(_: str, lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return _list_metro_lines_uncached(lat, lon, radius_m)


def _list_metro_lines_uncached(lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    radius = max(int(radius_m), 150)
    r1 = min(radius, 1200)
    attempt = 0
    debug: Dict[str, Any] = {}
    items: List[Dict[str, Any]] = []
    while True:
        query = (
            f"[out:json][timeout:25];\n"
            f"nwr(around:{r1},{lat},{lon})[railway=station];\n"
            f"nwr(around:{r1},{lat},{lon})[railway=stop];\n"
            f"nwr(around:{r1},{lat},{lon})[railway=tram_stop];\n"
            "out center 120;"
        )
        elements, query_debug = query_overpass(query, f"metro_r{r1}")
        debug = {**query_debug, "radius": r1}
        seen_points = set()
        line_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for element in elements:
            tags = element.get("tags") or {}
            name = tags.get("name")
            lat2, lon2 = _extract_coords(element)
            if lat2 is None or lon2 is None:
                continue
            point_key = _dedupe_key(lat2, lon2, name)
            if point_key in seen_points:
                continue
            seen_points.add(point_key)
            distance = int(_haversine(lat, lon, lat2, lon2))
            ref_pairs: List[Tuple[str, str]] = [(value, "ref") for value in _split_refs(tags.get("ref"))]
            if not ref_pairs and tags.get("name"):
                ref_pairs.append((tags["name"], "name"))
            if not ref_pairs and tags.get("network"):
                ref_pairs.append((tags["network"], "network"))
            for ref_value, origin in ref_pairs:
                key = (ref_value.lower(), origin)
                line = line_map.get(key)
                label = tags.get("name") or (f"Ligne {ref_value}" if ref_value else "Métro")
                if line is None or distance < line["distance_m"]:
                    line_map[key] = {
                        "ref": ref_value if origin == "ref" else None,
                        "name": label,
                        "distance_m": distance,
                    }
        items = sorted(line_map.values(), key=lambda item: item["distance_m"])
        debug["items"] = len(items)
        if not _should_retry_radius(items, debug, attempt):
            break
        new_radius = max(int(r1 / 1.5), 120)
        if new_radius >= r1:
            break
        debug["radius_reduced"] = True
        r1 = new_radius
        attempt += 1
    return items, debug


def _split_refs(raw: str | None) -> List[str]:
    if not raw:
        return []
    refs: List[str] = []
    for token in raw.replace("/", ";").split(";"):
        cleaned = token.strip()
        if cleaned:
            refs.append(cleaned)
    return refs


def list_metro_lines(
    lat: float,
    lon: float,
    radius_m: int = 1200,
    limit: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lat_key = round(float(lat), 5)
    lon_key = round(float(lon), 5)
    radius_key = int(radius_m)
    items, debug = _list_metro_lines_cached("list_metro_lines", lat_key, lon_key, radius_key)
    limited = items[:limit]
    debug = {**debug, "items": len(limited)}
    return limited, debug


@_cache_if_available(ttl=300)
def _list_bus_lines_cached(_: str, lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return _list_bus_lines_uncached(lat, lon, radius_m)


def _list_bus_lines_uncached(lat: float, lon: float, radius_m: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    radius = max(int(radius_m), 150)
    r1 = min(radius, 1500)
    attempt = 0
    debug: Dict[str, Any] = {}
    items: List[Dict[str, Any]] = []
    while True:
        query = (
            f"[out:json][timeout:25];\n"
            f"nwr(around:{r1},{lat},{lon})[highway=bus_stop];\n"
            "out center 200;"
        )
        elements, query_debug = query_overpass(query, f"bus_r{r1}")
        debug = {**query_debug, "radius": r1}
        seen_points = set()
        line_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for element in elements:
            tags = element.get("tags") or {}
            lat2, lon2 = _extract_coords(element)
            if lat2 is None or lon2 is None:
                continue
            name = tags.get("name") or "Arrêt de bus"
            point_key = _dedupe_key(lat2, lon2, name)
            if point_key in seen_points:
                continue
            seen_points.add(point_key)
            distance = int(_haversine(lat, lon, lat2, lon2))
            ref_pairs: List[Tuple[str, str]] = [(value, "ref") for value in _split_refs(tags.get("ref"))]
            if not ref_pairs and name:
                ref_pairs.append((name, "name"))
            for ref_value, origin in ref_pairs:
                key = (ref_value.lower(), origin)
                label = name if origin != "ref" else f"Bus {ref_value}" if ref_value else name
                line = line_map.get(key)
                if line is None or distance < line["distance_m"]:
                    line_map[key] = {
                        "ref": ref_value if origin == "ref" else None,
                        "name": label,
                        "distance_m": distance,
                    }
        items = sorted(line_map.values(), key=lambda item: item["distance_m"])
        debug["items"] = len(items)
        if not _should_retry_radius(items, debug, attempt):
            break
        new_radius = max(int(r1 / 1.5), 120)
        if new_radius >= r1:
            break
        debug["radius_reduced"] = True
        r1 = new_radius
        attempt += 1
    return items, debug


def list_bus_lines(
    lat: float,
    lon: float,
    radius_m: int = 1200,
    limit: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lat_key = round(float(lat), 5)
    lon_key = round(float(lon), 5)
    radius_key = int(radius_m)
    items, debug = _list_bus_lines_cached("list_bus_lines", lat_key, lon_key, radius_key)
    limited = items[:limit]
    debug = {**debug, "items": len(limited)}
    return limited, debug
