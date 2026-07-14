from app.services.transport_cache import TransportCache, _cache_file, _key


def test_cache_filename_has_no_illegal_windows_char(tmp_path):
    # La clé contient des `:` (lat:lon:radius:providers) — illégaux dans un nom de
    # fichier Windows. Le nom de fichier produit ne doit contenir AUCUN caractère
    # illégal, sinon OSError [Errno 22] à l'écriture (régression du bug corrigé).
    key = _key(48.8566, 2.3522, 1200, ("gtfs", "osm"), rounding=4)
    assert ":" in key  # la clé brute contient bien le séparateur problématique
    path = _cache_file(key, tmp_path)
    illegal = set('<>:"/\\|?*')
    assert not (set(path.name) & illegal), f"nom de fichier illégal sous Windows: {path.name}"


def test_cache_roundtrip_with_illegal_key_chars(tmp_path):
    # Round-trip complet avec une clé contenant `:` -> écriture + relecture OK.
    cache = TransportCache(base_dir=tmp_path, ttl_seconds=1000, rounding=4)
    payload = {"metro_lines": ["2", "12"], "bus_lines": ["30"], "taxis": [], "provider_used": {}}
    cache.set(48.8566, 2.3522, 300, ("gtfs", "osm", "google"), payload)
    assert cache.get(48.8566, 2.3522, 300, ("gtfs", "osm", "google")) == payload


def test_transport_cache_hit(tmp_path):
    cache = TransportCache(base_dir=tmp_path, ttl_seconds=1000, rounding=4)
    payload = {"metro_lines": ["A"], "bus_lines": ["1"], "taxis": ["Foo"], "provider_used": {"metro": "gtfs"}}
    cache.set(48.0, 2.0, 1200, ("gtfs", "osm"), payload)
    cached = cache.get(48.0, 2.0, 1200, ("gtfs", "osm"))
    assert cached == payload


def test_transport_cache_expired(tmp_path, monkeypatch):
    cache = TransportCache(base_dir=tmp_path, ttl_seconds=10, rounding=4)
    payload = {"metro_lines": ["B"], "bus_lines": [], "taxis": [], "provider_used": {}}
    monkeypatch.setattr("app.services.transport_cache.time.time", lambda: 0)
    cache.set(10.0, 20.0, 500, ("gtfs",), payload)
    monkeypatch.setattr("app.services.transport_cache.time.time", lambda: 20)
    assert cache.get(10.0, 20.0, 500, ("gtfs",)) is None
