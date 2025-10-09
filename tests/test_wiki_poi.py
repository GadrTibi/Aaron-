from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
import requests

from services import image_service, poi_service, wiki_client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("Network access not allowed in tests")

    monkeypatch.setattr(wiki_client._session, "get", blocked)
    monkeypatch.setattr("requests.get", blocked)


@pytest.fixture
def mock_wiki(monkeypatch):
    def fake_geosearch(lat, lon, radius_m, lang="fr", limit=50):  # noqa: ARG001
        return {
            "query": {
                "geosearch": [
                    {"pageid": 1, "title": "Gare centrale", "lat": lat, "lon": lon, "dist": 100},
                    {"pageid": 2, "title": "Cathédrale", "lat": lat, "lon": lon, "dist": 200},
                    {"pageid": 3, "title": "Belvédère", "lat": lat, "lon": lon, "dist": 300},
                ]
            }
        }

    def fake_details(pageids, lang="fr"):
        pages: Dict[str, Dict[str, Any]] = {}
        for pid in pageids:
            if pid == 1:
                pages[str(pid)] = {
                    "title": "Gare centrale",
                    "categories": [{"title": "Category:Railway stations"}],
                    "coordinates": [{"lat": 1.0, "lon": 2.0}],
                    "pageprops": {"wikibase_item": "Q1"},
                }
            elif pid == 2:
                pages[str(pid)] = {
                    "title": "Cathédrale",
                    "categories": [{"title": "Category:Cathedrals in France"}],
                    "coordinates": [{"lat": 1.0, "lon": 2.0}],
                    "pageprops": {"wikibase_item": "Q2"},
                }
            elif pid == 3:
                pages[str(pid)] = {
                    "title": "Belvédère",
                    "categories": [{"title": "Category:Panoramic viewpoints"}],
                    "coordinates": [{"lat": 1.0, "lon": 2.0}],
                    "pageprops": {"wikibase_item": "Q3"},
                }
        return {"query": {"pages": pages}}

    def fake_entity(qid):  # noqa: ARG001
        return {"entities": {qid: {"claims": {}, "sitelinks": {}}}}

    monkeypatch.setattr(wiki_client, "geosearch", fake_geosearch)
    monkeypatch.setattr(wiki_client, "page_details", fake_details)
    monkeypatch.setattr(wiki_client, "wikidata_entity", fake_entity)
    monkeypatch.setattr(wiki_client, "commons_category_images", lambda category, limit=5: [])


def test_categorize_from_categories_matches():
    categories = [
        "Category:Railway stations",
        "Category:World Heritage Sites",
        "Category:Panoramic viewpoints",
    ]
    result = poi_service.categorize_from_categories(categories)
    assert {"transport", "incontournables", "spots"}.issubset(result)


def test_get_pois_filters_by_category(mock_wiki, monkeypatch):  # noqa: ARG001
    monkeypatch.setattr(poi_service, "reverse_geocode", lambda *args, **kwargs: "Paris")
    pois = poi_service.get_pois(1.0, 2.0, 500, "transport")
    assert all("transport" != poi["title"].lower() for poi in pois)
    assert pois
    assert all("Gare" in poi["title"] or "Gare" in poi["display"] for poi in pois)


def test_candidate_images_deduplicated(monkeypatch):
    def fake_page_details(pageids, lang="fr"):
        return {
            "query": {
                "pages": {
                    str(pageids[0]): {
                        "original": {"source": "https://upload.wikimedia.org/img1.jpg"},
                        "pageprops": {"wikibase_item": "Q1"},
                    }
                }
            }
        }

    def fake_entity(qid):  # noqa: ARG001
        return {
            "entities": {
                qid: {
                    "claims": {
                        "P18": [
                            {"mainsnak": {"datavalue": {"value": "File:Test.jpg"}}},
                            {"mainsnak": {"datavalue": {"value": "File:Test.jpg"}}},
                        ],
                        "P373": [
                            {"mainsnak": {"datavalue": {"value": "Paris"}}},
                        ],
                    },
                    "sitelinks": {},
                }
            }
        }

    def fake_commons(category, limit=5):  # noqa: ARG001
        return [
            {"url": "https://commons.wikimedia.org/thumb1.jpg"},
            {"url": "https://commons.wikimedia.org/thumb1.jpg"},
        ]

    monkeypatch.setattr(wiki_client, "page_details", fake_page_details)
    monkeypatch.setattr(wiki_client, "wikidata_entity", fake_entity)
    monkeypatch.setattr(wiki_client, "commons_category_images", fake_commons)

    images = image_service.candidate_images(1, "Q1")
    assert len(images) == 3
    providers = [img["provider"] for img in images]
    assert providers[0] == "wikipedia"
    assert "wikidata" in providers
    assert "commons" in providers


def test_reverse_geocode_uses_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(poi_service, "_CACHE_DIR", cache_dir)

    calls = {"count": 0}

    class DummyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"address": {"city": "Paris"}}

    def fake_get(url, params=None, headers=None, timeout=8):  # noqa: ARG001
        calls["count"] += 1
        return DummyResponse()

    monkeypatch.setattr(poi_service.requests, "get", fake_get)

    city1 = poi_service.reverse_geocode(1.0, 2.0)
    city2 = poi_service.reverse_geocode(1.0, 2.0)
    assert city1 == city2 == "Paris"
    assert calls["count"] == 1


def test_download_image_placeholder(monkeypatch):
    ensure_path = image_service.ensure_placeholder()

    class DummyResponse:
        content = b"123"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(image_service.requests, "get", lambda url, headers=None, timeout=8: DummyResponse())
    path = image_service.download_image("https://example.com/img.jpg", "slug")
    assert path == ensure_path
