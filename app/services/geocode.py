import requests
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "MFY-Local-App/1.0 (contact: contact@example.com)"}
def geocode_address(q: str):
    if not q or not q.strip(): return (None, None)
    params = {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
    r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data: return (None, None)
    try:
        return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception:
        return (None, None)