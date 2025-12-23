from app.services.geocode_flow import should_use_session_cache


def test_session_cache_prevents_network(monkeypatch):
    call_count = {"geocode": 0}

    def _fake_geocode(address: str):
        call_count["geocode"] += 1
        return (1.0, 2.0)

    address = "15 rue du Test"
    session_address = "15 Rue du test"
    lat = 48.1
    lon = 2.3

    if not should_use_session_cache(address, session_address, lat, lon):
        _fake_geocode(address)

    assert call_count["geocode"] == 0

    # when address changes, a new call is required
    new_addr = "99 autre rue"
    if not should_use_session_cache(new_addr, session_address, lat, lon):
        _fake_geocode(new_addr)
    assert call_count["geocode"] == 1
