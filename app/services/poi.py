import math
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

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

def fetch_transports(lat, lon, radius_m=1500):
    q = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity=taxi];
  node(around:{radius_m},{lat},{lon})[railway=station][station=subway];
  node(around:{radius_m},{lat},{lon})[railway=subway_entrance];
  node(around:{radius_m},{lat},{lon})[highway=bus_stop];
);
out center 120;
"""
    els = _overpass(q)
    cand = {"taxi": [], "metro": [], "bus": []}
    for el in els:
        tags = el.get("tags", {})
        name = tags.get("name")
        lat2, lon2 = el.get("lat"), el.get("lon")
        d = _haversine(lat, lon, lat2, lon2)
        if tags.get("amenity") == "taxi":
            cand["taxi"].append((name or "Station de taxi", d))
        elif tags.get("railway") in ("station", "subway_entrance"):
            tname = name or tags.get("station") or "Métro"
            cand["metro"].append((tname, d))
        elif tags.get("highway") == "bus_stop":
            cand["bus"].append((name or "Arrêt de bus", d))
    for k in cand: cand[k].sort(key=lambda x: x[1])
    def fmt(item):
        nm, dist = item
        mins = int(round(dist / 80.0))
        return f"{nm} ({int(dist)} m – {mins} min)"
    out = {
        "taxi": fmt(cand["taxi"][0]) if cand["taxi"] else "",
        "metro": fmt(cand["metro"][0]) if cand["metro"] else "",
        "bus": fmt(cand["bus"][0]) if cand["bus"] else "",
    }
    return out

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


def list_metro_lines(lat: float, lon: float, radius_m: int = 1200, limit: int = 3) -> list[dict]:
    q = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[railway=subway_entrance];
  node(around:{radius_m},{lat},{lon})[public_transport~"^(platform|stop_position)$"][subway=yes];
)->.st;
rel(bn.st)[type=route][route=subway];
(._;>;);
out body;
"""
    els = _overpass(q)
    nodes = {el["id"]: (el.get("lat"), el.get("lon")) for el in els if el.get("type") == "node"}
    lines = {}
    for el in els:
        if el.get("type") != "relation":
            continue
        tags = el.get("tags", {})
        ref = tags.get("ref")
        if not ref:
            continue
        name = tags.get("name") or f"M{ref}"
        dist = None
        for mem in el.get("members", []):
            if mem.get("type") == "node" and mem.get("ref") in nodes:
                lat2, lon2 = nodes[mem["ref"]]
                d = _haversine(lat, lon, lat2, lon2)
                if dist is None or d < dist:
                    dist = d
        if dist is None:
            continue
        cur = lines.get(ref)
        if cur is None or dist < cur["distance_m"]:
            lines[ref] = {"ref": ref, "name": name, "distance_m": int(dist)}
    return sorted(lines.values(), key=lambda x: x["distance_m"])[:limit]


def list_bus_lines(lat: float, lon: float, radius_m: int = 1200, limit: int = 3) -> list[dict]:
    q = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[highway=bus_stop];
  node(around:{radius_m},{lat},{lon})[public_transport~"^(platform|stop_position)$"][bus=yes];
)->.st;
rel(bn.st)[type=route][route=bus];
(._;>;);
out body;
"""
    els = _overpass(q)
    nodes = {el["id"]: (el.get("lat"), el.get("lon")) for el in els if el.get("type") == "node"}
    lines = {}
    for el in els:
        if el.get("type") != "relation":
            continue
        tags = el.get("tags", {})
        ref = tags.get("ref")
        if not ref:
            continue
        name = tags.get("name") or f"Bus {ref}"
        dist = None
        for mem in el.get("members", []):
            if mem.get("type") == "node" and mem.get("ref") in nodes:
                lat2, lon2 = nodes[mem["ref"]]
                d = _haversine(lat, lon, lat2, lon2)
                if dist is None or d < dist:
                    dist = d
        if dist is None:
            continue
        cur = lines.get(ref)
        if cur is None or dist < cur["distance_m"]:
            lines[ref] = {"ref": ref, "name": name, "distance_m": int(dist)}
    return sorted(lines.values(), key=lambda x: x["distance_m"])[:limit]
