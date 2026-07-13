"""Tests de la couche HTTP commune (retry/backoff sur erreurs transitoires)."""

import requests

from app.services import http_client


class _Resp:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def _seq_requests(monkeypatch, responses):
    """Fait renvoyer par requests.request les éléments de `responses` (Response
    ou Exception) l'un après l'autre. Retourne le compteur d'appels."""
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        item = responses[min(i, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(http_client.requests, "request", fake_request)
    return calls


def test_retries_on_503_then_succeeds(monkeypatch):
    calls = _seq_requests(monkeypatch, [_Resp(503), _Resp(200)])
    resp = http_client.request_with_retry("GET", "http://x", sleep=lambda _: None)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_retries_on_timeout_then_succeeds(monkeypatch):
    calls = _seq_requests(monkeypatch, [requests.Timeout("boom"), _Resp(200)])
    resp = http_client.request_with_retry("GET", "http://x", sleep=lambda _: None)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_no_retry_on_400(monkeypatch):
    calls = _seq_requests(monkeypatch, [_Resp(400), _Resp(200)])
    resp = http_client.request_with_retry("POST", "http://x", sleep=lambda _: None)
    assert resp.status_code == 400  # 400 n'est pas transitoire -> pas de retry
    assert calls["n"] == 1


def test_gives_up_after_max_retries(monkeypatch):
    calls = _seq_requests(monkeypatch, [_Resp(500), _Resp(500), _Resp(500), _Resp(500)])
    resp = http_client.request_with_retry("GET", "http://x", max_retries=2, sleep=lambda _: None)
    assert resp.status_code == 500
    assert calls["n"] == 3  # 1 + 2 retries


def test_reraises_last_exception_after_max_retries(monkeypatch):
    _seq_requests(monkeypatch, [requests.ConnectionError("x")])
    try:
        http_client.request_with_retry("GET", "http://x", max_retries=1, sleep=lambda _: None)
        assert False, "aurait dû lever ConnectionError"
    except requests.ConnectionError:
        pass


def test_respects_retry_after_header(monkeypatch):
    _seq_requests(monkeypatch, [_Resp(429, {"Retry-After": "2"}), _Resp(200)])
    slept = []
    http_client.request_with_retry("GET", "http://x", sleep=slept.append)
    assert slept == [2.0]  # a dormi la durée Retry-After, pas le backoff par défaut


def test_retry_after_is_capped(monkeypatch):
    # Un Retry-After abusif (3600 s) ne doit jamais figer l'UI : plafonné à MAX_SLEEP_S.
    _seq_requests(monkeypatch, [_Resp(503, {"Retry-After": "3600"}), _Resp(200)])
    slept = []
    http_client.request_with_retry("GET", "http://x", sleep=slept.append)
    assert slept == [http_client.MAX_SLEEP_S]


def test_no_retry_on_timeout_when_disabled(monkeypatch):
    # Requête non idempotente : un timeout ne doit PAS être rejoué (double effet).
    calls = _seq_requests(monkeypatch, [requests.Timeout("boom"), _Resp(200)])
    try:
        http_client.request_with_retry("POST", "http://x", retry_on_timeout=False, sleep=lambda _: None)
        assert False, "aurait dû lever Timeout sans réessayer"
    except requests.Timeout:
        pass
    assert calls["n"] == 1
