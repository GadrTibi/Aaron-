from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from config import wiki_settings
from services import cache_utils
from services.wiki_images import ImageCandidate, WikiImageService
from services.wiki_poi import WikiPOIService


@pytest.fixture(autouse=True)
def patch_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_dir = tmp_path / "cache"
    images_dir = tmp_path / "images"
    monkeypatch.setattr(wiki_settings, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(wiki_settings, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(WikiPOIService, "_SLEEP_SECONDS", 0.0)
    monkeypatch.setattr(WikiImageService, "_SLEEP_SECONDS", 0.0)


def test_classification_rules() -> None:
    service = WikiPOIService()
    assert service._classify("Chez Mimi", {"instances": ["Q11707"], "subclasses": [], "labels": {}, "importance": 1.0}) == "incontournables"
    assert service._classify("Belvédère", {"instances": [], "subclasses": ["Q207694"], "labels": {}, "importance": 1.0}) == "spots"
    assert service._classify("Grand Musée", {"instances": ["Q33506"], "subclasses": [], "labels": {}, "importance": 1.0}) == "visits"


def test_list_by_category_limits_and_order(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WikiPOIService()

    geo_items: List[Dict[str, object]] = []
    pageprops: Dict[int, str] = {}
    wd_infos: Dict[str, Dict[str, object]] = {}

    # Generate restaurants
    for idx in range(20):
        pageid = 100 + idx
        geo_items.append({
            "pageid": pageid,
            "title": f"Restaurant {idx}",
            "lat": 0.0,
            "lon": 0.0,
            "dist": 100 + idx * 50,
        })
        pageprops[pageid] = "Q11707"
        wd_infos["Q11707"] = {"instances": ["Q11707"], "subclasses": [], "labels": {}, "importance": 0.5}

    # Generate spots
    for idx in range(12):
        pageid = 200 + idx
        geo_items.append({
            "pageid": pageid,
            "title": f"Viewpoint {idx}",
            "lat": 0.0,
            "lon": 0.0,
            "dist": 200 + idx * 80,
        })
        pageprops[pageid] = f"QSPOT{idx}"
        wd_infos[f"QSPOT{idx}"] = {"instances": ["Q207694"], "subclasses": [], "labels": {}, "importance": 0.4}

    # Generate visits
    for idx in range(12):
        pageid = 300 + idx
        geo_items.append({
            "pageid": pageid,
            "title": f"Museum {idx}",
            "lat": 0.0,
            "lon": 0.0,
            "dist": 150 + idx * 60,
        })
        pageprops[pageid] = f"QVIS{idx}"
        wd_infos[f"QVIS{idx}"] = {"instances": ["Q33506"], "subclasses": [], "labels": {}, "importance": 0.7}

    monkeypatch.setattr(service, "_geosearch", lambda lat, lon, radius: geo_items)
    monkeypatch.setattr(service, "_pageprops_to_qids", lambda ids: {pid: pageprops.get(pid) for pid in ids})
    monkeypatch.setattr(service, "_wikidata_enrich", lambda qids: {qid: wd_infos[qid] for qid in qids if qid in wd_infos})

    categories = service.list_by_category(0.0, 0.0, 1000)

    assert len(categories["incontournables"]) == 15
    assert len(categories["spots"]) == 10
    assert len(categories["visits"]) == 10
    assert categories["incontournables"][0].title == "Restaurant 0"
    assert categories["visits"][0].title == "Museum 0"


def test_incontournables_classification_excludes_museums(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WikiPOIService()

    geo_items = [
        {"pageid": 401, "title": "Chez Test", "lat": 0.0, "lon": 0.0, "dist": 120},
        {"pageid": 402, "title": "Musée d'Art", "lat": 0.0, "lon": 0.0, "dist": 150},
    ]
    pageprops = {401: "QRESTO", 402: "QMUSEE"}
    wd_infos = {
        "QRESTO": {"instances": ["Q11707"], "subclasses": [], "labels": {}, "importance": 0.6},
        "QMUSEE": {"instances": ["Q33506"], "subclasses": [], "labels": {}, "importance": 0.8},
    }

    monkeypatch.setattr(service, "_geosearch", lambda lat, lon, radius: geo_items)
    monkeypatch.setattr(service, "_pageprops_to_qids", lambda ids: {pid: pageprops.get(pid) for pid in ids})
    monkeypatch.setattr(service, "_wikidata_enrich", lambda qids: {qid: wd_infos[qid] for qid in qids if qid in wd_infos})

    categories = service.list_by_category(0.0, 0.0, 1000)

    names = [poi.title for poi in categories["incontournables"]]
    assert "Chez Test" in names
    assert "Musée d'Art" not in names
    assert categories["visits"][0].title == "Musée d'Art"


def test_incontournables_respect_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WikiPOIService()

    geo_items: List[Dict[str, object]] = []
    pageprops: Dict[int, str] = {}
    wd_infos: Dict[str, Dict[str, object]] = {}

    for idx in range(25):
        pageid = 500 + idx
        geo_items.append(
            {
                "pageid": pageid,
                "title": f"Restaurant {idx}",
                "lat": 0.0,
                "lon": 0.0,
                "dist": 80 + idx * 30,
            }
        )
        qid = f"QRESTO{idx}"
        pageprops[pageid] = qid
        wd_infos[qid] = {"instances": ["Q11707"], "subclasses": [], "labels": {}, "importance": 0.5}

    monkeypatch.setattr(service, "_geosearch", lambda lat, lon, radius: geo_items)
    monkeypatch.setattr(service, "_pageprops_to_qids", lambda ids: {pid: pageprops.get(pid) for pid in ids})
    monkeypatch.setattr(service, "_wikidata_enrich", lambda qids: {qid: wd_infos[qid] for qid in qids if qid in wd_infos})

    categories = service.list_by_category(0.0, 0.0, 1200)

    assert len(categories["incontournables"]) <= 15


def test_cache_utils_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "sample"
    data = {"items": [1, 2, 3]}
    monkeypatch.setattr(wiki_settings, "CACHE_DIR", str(tmp_path / "cache"))
    cache_utils.write_cache_json(key, data)
    loaded = cache_utils.read_cache_json(key, 10)
    assert loaded == data


def test_image_candidates_with_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WikiImageService()
    candidate_main = ImageCandidate(url="https://img/1.jpg", thumb_url=None, width=1200, height=900, source="wikidata_p18")
    candidate_category = ImageCandidate(url="https://img/2.jpg", thumb_url=None, width=1300, height=900, source="commons_qid")
    candidate_search = ImageCandidate(url="https://img/3.jpg", thumb_url=None, width=1100, height=800, source="commons_text")

    monkeypatch.setattr(service, "_from_wikidata_p18", lambda qid, seen: [candidate_main])
    monkeypatch.setattr(service, "_from_commons_category", lambda qid, seen: [candidate_category])
    monkeypatch.setattr(
        service,
        "_from_commons_search",
        lambda title, city, country, limit, seen: [candidate_search],
    )

    candidates = service.candidates("Q1", "Test Museum", "Paris", "France", limit=3)
    assert [c.url for c in candidates] == ["https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg"]


def test_image_candidates_placeholder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wiki_settings, "IMAGES_DIR", str(tmp_path / "images"))
    service = WikiImageService()
    monkeypatch.setattr(service, "_from_wikidata_p18", lambda qid, seen: [])
    monkeypatch.setattr(service, "_from_commons_category", lambda qid, seen: [])
    monkeypatch.setattr(
        service,
        "_from_commons_search",
        lambda title, city, country, limit, seen: [],
    )

    candidates = service.candidates(None, "Unknown Place", None, None, limit=2)
    assert len(candidates) == 1
    assert Path(candidates[0].url).exists()


def test_image_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wiki_settings, "IMAGES_DIR", str(tmp_path / "images"))
    service = WikiImageService()

    class FakeResponse:
        headers = {"Content-Type": "image/jpeg"}
        content = b"\xff\xd8" + b"0" * 6000

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(service.session, "get", lambda url, timeout, stream=True: FakeResponse())

    path = service.download("https://example.com/photo.jpg")
    assert Path(path).exists()

    placeholder_path = service.download(None)
    assert Path(placeholder_path).exists()
