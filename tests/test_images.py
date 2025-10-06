from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Iterator

import pytest
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import image_fetcher


class DummyResponse:
    def __init__(self, status_code: int = 200, json_data=None, content: bytes | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content or b""
        self.headers = headers or {}

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def _image_bytes(width: int = 900, height: int = 600, color: str = "white") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(image_fetcher, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(image_fetcher, "PLACEHOLDER_PATH", tmp_path / "placeholder.png")
    monkeypatch.setattr(image_fetcher, "_sleep", lambda _: None)


def _sequence_responses(responses: Iterator[DummyResponse]):
    def _fake_request(*_args, **_kwargs):
        return next(responses)

    return _fake_request


def test_get_poi_image_unsplash_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "token")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    responses = iter(
        [
            DummyResponse(200, json_data={"results": [{"width": 1200, "urls": {"regular": "https://img/test.jpg"}}]}),
            DummyResponse(200, content=_image_bytes(), headers={"Content-Type": "image/jpeg"}),
        ]
    )
    monkeypatch.setattr(image_fetcher.requests, "request", _sequence_responses(responses))

    path = image_fetcher.get_poi_image("Tour Eiffel", city="Paris", country="France")
    assert Path(path).exists()
    last = image_fetcher.get_last_result()
    assert last is not None
    assert last.provider == "Unsplash"


def test_cascade_to_pexels(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "token")
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-token")

    responses = iter(
        [
            DummyResponse(401, json_data={"errors": ["Unauthorized"]}),
            DummyResponse(200, json_data={"photos": [{"width": 1024, "src": {"large": "https://img/pexels.jpg"}}]}),
            DummyResponse(200, content=_image_bytes(), headers={"Content-Type": "image/jpeg"}),
        ]
    )
    monkeypatch.setattr(image_fetcher.requests, "request", _sequence_responses(responses))

    path = image_fetcher.get_poi_image("Cathédrale Notre-Dame", city="Paris")
    assert Path(path).exists()
    last = image_fetcher.get_last_result()
    assert last is not None
    assert last.provider == "Pexels"


def test_cascade_to_wikimedia(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    responses = iter(
        [
            DummyResponse(
                200,
                json_data={
                    "query": {
                        "pages": {
                            "1": {
                                "imageinfo": [{"url": "https://img/wiki.jpg", "width": 1200}],
                            }
                        }
                    }
                },
            ),
            DummyResponse(200, content=_image_bytes(), headers={"Content-Type": "image/jpeg"}),
        ]
    )
    monkeypatch.setattr(image_fetcher.requests, "request", _sequence_responses(responses))

    path = image_fetcher.get_poi_image("Mont Saint-Michel", country="France")
    assert Path(path).exists()
    last = image_fetcher.get_last_result()
    assert last is not None
    assert last.provider == "Wikimedia"


def test_placeholder_when_all_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "token")
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-token")

    small = _image_bytes(width=200, height=150)
    responses = iter(
        [
            DummyResponse(200, json_data={"results": [{"width": 900, "urls": {"regular": "https://img/u.jpg"}}]}),
            DummyResponse(200, content=small, headers={"Content-Type": "image/jpeg"}),
            DummyResponse(200, json_data={"photos": [{"width": 1024, "src": {"large": "https://img/p.jpg"}}]}),
            DummyResponse(200, content=b"nope", headers={"Content-Type": "text/plain"}),
            DummyResponse(
                200,
                json_data={
                    "query": {
                        "pages": {
                            "1": {"imageinfo": [{"url": "https://img/w.jpg", "width": 1024}]}
                        }
                    }
                },
            ),
            DummyResponse(200, content=b"tiny", headers={"Content-Type": "image/jpeg"}),
        ]
    )
    monkeypatch.setattr(image_fetcher.requests, "request", _sequence_responses(responses))

    path = image_fetcher.get_poi_image("Lieu imaginaire", city="Paris")
    placeholder = Path(image_fetcher.PLACEHOLDER_PATH)
    assert path == str(placeholder)
    assert placeholder.exists()
    last = image_fetcher.get_last_result()
    assert last is not None
    assert last.provider == "placeholder"


def test_retry_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_request(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return DummyResponse(429)
        return DummyResponse(200)

    monkeypatch.setattr(image_fetcher.requests, "request", fake_request)
    monkeypatch.setattr(image_fetcher, "_sleep", lambda _: None)

    response, status, _ = image_fetcher._send_request(
        "https://api.test/", provider="Test", poi="POI", city=None, country=None
    )
    assert status == "200"
    assert response is not None
    assert len(calls) == 2


def test_slugify_handles_accents() -> None:
    slug = image_fetcher._slugify("Église Saint-Étienne")
    assert slug == "eglise-saint-etienne"
