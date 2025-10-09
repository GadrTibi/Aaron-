"""Point of interest discovery via Wikimedia services."""
from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import requests

from config import wiki_settings
from services.cache_utils import read_cache_json, write_cache_json

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class POI:
    """Simple data container representing a point of interest."""

    title: str
    name_display: str
    name_full: str
    distance_m: float
    lat: float
    lon: float
    pageid: int
    qid: str | None
    category: str
    importance: float


class WikiPOIService:
    """Service aggregating Wikipedia and Wikidata for POI discovery."""

    _SLEEP_SECONDS = 0.12

    _INCONTOURNABLE_QIDS = {
        "Q11707",  # restaurant
        "Q177882",  # cafe
        "Q2745434",  # brasserie
        "Q270524",  # bakery
        "Q2000353",  # pâtisserie
        "Q245117",  # fast food restaurant
        "Q2590683",  # tea house
        "Q222131",  # department store
        "Q213441",  # shopping mall
        "Q4234424",  # retail store
    }

    _SPOTS_QIDS = {
        "Q207694",  # viewpoint
        "Q125191",  # park
        "Q160091",  # garden
        "Q185113",  # nature reserve
        "Q40080",  # beach
        "Q8502",  # mountain
        "Q83620",  # cliff
        "Q2004003",  # natural monument
        "Q3356847",  # promenade
        "Q49084",  # observation deck
        "Q188211",  # protected area
    }

    _VISITS_QIDS = {
        "Q33506",  # museum
        "Q180788",  # art museum
        "Q125191",  # park
        "Q17350442",  # landmark
        "Q190943",  # theatre
        "Q1329623",  # opera house
        "Q9143",  # palace
        "Q23413",  # castle
        "Q24398318",  # historical monument
        "Q2977",  # cathedral
        "Q16970",  # church building
        "Q1107656",  # botanical garden
        "Q43501",  # zoo
        "Q12280",  # amusement park
        "Q4989906",  # art gallery
    }

    _INCONTOURNABLE_KEYWORDS = (
        "restaurant",
        "bistrot",
        "bistro",
        "café",
        "cafe",
        "brasserie",
        "pâtisserie",
        "patisserie",
        "boulangerie",
        "bakery",
        "magasin",
        "store",
        "shop",
        "mall",
        "center",
        "centre commercial",
    )

    _SPOTS_KEYWORDS = (
        "belvédère",
        "belvedere",
        "view",
        "panorama",
        "overlook",
        "park",
        "parc",
        "jardin",
        "garden",
        "nature",
        "rooftop",
        "promenade",
        "beach",
        "plage",
        "sommet",
        "peak",
    )

    _VISITS_KEYWORDS = (
        "musée",
        "museum",
        "monument",
        "palais",
        "palace",
        "castle",
        "château",
        "chateau",
        "cathédrale",
        "cathedral",
        "église",
        "eglise",
        "galerie",
        "gallery",
        "opera",
        "opéra",
        "théâtre",
        "theatre",
        "zoo",
        "parc à thème",
        "theme park",
        "jardin botanique",
        "botanical garden",
    )

    def __init__(self, lang: str = wiki_settings.WIKI_LANG_DEFAULT) -> None:
        self.lang = lang
        self.session = requests.Session()
        self.session.headers.update(wiki_settings.default_headers())

    def list_by_category(self, lat: float, lon: float, radius_m: int) -> Dict[str, List[POI]]:
        """Return POIs grouped by category."""
        geosearch = self._geosearch(lat, lon, radius_m)
        pageids = [item["pageid"] for item in geosearch]
        qid_map = self._pageprops_to_qids(pageids)
        qids = [qid for qid in qid_map.values() if qid]
        wd_data = self._wikidata_enrich(qids)

        categories: Dict[str, List[Tuple[float, POI]]] = {
            "incontournables": [],
            "spots": [],
            "visits": [],
        }
        for item in geosearch:
            pageid = item["pageid"]
            title = item["title"]
            qid = qid_map.get(pageid)
            info = wd_data.get(qid) if qid else None
            category, strength = self._classify_with_strength(title, info)
            if category is None:
                continue
            importance = info["importance"] if info else 0.2
            distance_m = float(item.get("dist", 0.0))
            score = self._score(distance_m, importance, strength)
            poi = POI(
                title=title,
                name_display=title,
                name_full=title,
                distance_m=distance_m,
                lat=float(item.get("lat", 0.0)),
                lon=float(item.get("lon", 0.0)),
                pageid=pageid,
                qid=qid,
                category=category,
                importance=importance,
            )
            categories[category].append((score, poi))

        limits = {"incontournables": 15, "spots": 10, "visits": 10}
        sorted_results: Dict[str, List[POI]] = {}
        for key, entries in categories.items():
            ordered = sorted(entries, key=lambda x: x[0], reverse=True)
            sorted_results[key] = [poi for _, poi in ordered[: limits[key]]]
        return sorted_results

    # --- Internal helpers -------------------------------------------------

    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        backoff = wiki_settings.RETRY_BASE_DELAY
        last_exc: Exception | None = None
        for attempt in range(wiki_settings.RETRIES + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=wiki_settings.HTTP_TIMEOUT,
                )
                response.raise_for_status()
                self._throttle()
                return response.json()
            except Exception as exc:  # pragma: no cover - exercised in failure cases
                last_exc = exc
                if attempt >= wiki_settings.RETRIES:
                    raise
                delay = backoff * (2 ** attempt) + random.uniform(0, wiki_settings.RETRY_JITTER)
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _throttle(self) -> None:
        time.sleep(self._SLEEP_SECONDS)

    def _geosearch(self, lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
        key = f"geo:{self.lang}:{lat:.5f}:{lon:.5f}:{radius_m}"
        cached = read_cache_json(key, wiki_settings.CACHE_TTL_SEC)
        if cached:
            logger.info("WikiPOI geosearch cache hit")
            return cached.get("items", [])
        url = f"https://{self.lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius_m,
            "gslimit": 50,
            "format": "json",
        }
        data = self._request_json(url, params)
        items = data.get("query", {}).get("geosearch", [])
        write_cache_json(key, {"items": items})
        return items

    def _pageprops_to_qids(self, pageids: Iterable[int]) -> Dict[int, str | None]:
        result: Dict[int, str | None] = {}
        pageid_list = list(pageids)
        batches = [pageid_list[i : i + 50] for i in range(0, len(pageid_list), 50)]
        for batch in batches:
            if not batch:
                continue
            key = f"pageprops:{self.lang}:{','.join(map(str, batch))}"
            cached = read_cache_json(key, wiki_settings.CACHE_TTL_SEC)
            if cached:
                result.update({int(k): v for k, v in cached.get("items", {}).items()})
                continue
            params = {
                "action": "query",
                "prop": "pageprops",
                "pageids": "|".join(str(pid) for pid in batch),
                "format": "json",
            }
            url = f"https://{self.lang}.wikipedia.org/w/api.php"
            data = self._request_json(url, params)
            pages = data.get("query", {}).get("pages", {})
            mapping: Dict[str, str | None] = {}
            for pid, info in pages.items():
                props = info.get("pageprops", {})
                mapping[str(pid)] = props.get("wikibase_item")
                result[int(pid)] = mapping[str(pid)]
            write_cache_json(key, {"items": mapping})
        return result

    def _wikidata_enrich(self, qids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        qid_list = list(dict.fromkeys(qids))
        info_map: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(qid_list), 50):
            batch = qid_list[i : i + 50]
            key = f"wikidata:{','.join(batch)}"
            cached = read_cache_json(key, wiki_settings.CACHE_TTL_SEC)
            if cached:
                info_map.update(cached.get("items", {}))
                continue
            params = {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "format": "json",
                "props": "claims|sitelinks|labels",
                "languages": "fr|en",
            }
            url = "https://www.wikidata.org/w/api.php"
            data = self._request_json(url, params)
            entities = data.get("entities", {})
            batch_result: Dict[str, Dict[str, Any]] = {}
            for qid, entity in entities.items():
                claims = entity.get("claims", {})
                instances = self._extract_claim_ids(claims.get("P31", []))
                subclasses = self._extract_claim_ids(claims.get("P279", []))
                sitelinks = len(entity.get("sitelinks", {}))
                labels = entity.get("labels", {})
                importance = min(1.0, math.log1p(sitelinks) / math.log1p(200)) if sitelinks else 0.2
                batch_result[qid] = {
                    "instances": instances,
                    "subclasses": subclasses,
                    "labels": {k: v.get("value") for k, v in labels.items()},
                    "importance": importance,
                }
            write_cache_json(key, {"items": batch_result})
            info_map.update(batch_result)
        return info_map

    @staticmethod
    def _extract_claim_ids(claims: Iterable[Dict[str, Any]]) -> List[str]:
        result: List[str] = []
        for claim in claims:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {})
            value = datavalue.get("value")
            if isinstance(value, dict):
                qid = value.get("id")
                if isinstance(qid, str):
                    result.append(qid)
        return result

    def _classify(self, title: str, wd_info: Dict[str, Any] | None) -> str | None:
        category, _ = self._classify_with_strength(title, wd_info)
        return category

    def _classify_with_strength(
        self, title: str, wd_info: Dict[str, Any] | None
    ) -> Tuple[str | None, str]:
        text = title.lower()
        labels = ""
        instances: Iterable[str] = []
        subclasses: Iterable[str] = []
        if wd_info:
            labels = " ".join(wd_info.get("labels", {}).values()).lower()
            instances = wd_info.get("instances", [])
            subclasses = wd_info.get("subclasses", [])
        combined = f"{text} {labels}".strip()
        all_qids = set(instances) | set(subclasses)

        # Priority to explicit restaurants/commercial via P31
        if any(qid in self._INCONTOURNABLE_QIDS for qid in instances):
            return "incontournables", "instance"

        visit_match = any(qid in self._VISITS_QIDS for qid in all_qids)
        spot_match = any(qid in self._SPOTS_QIDS for qid in all_qids)
        resto_match = any(qid in self._INCONTOURNABLE_QIDS for qid in all_qids)

        if visit_match:
            return "visits", "instance"
        if spot_match:
            return "spots", "instance"
        if resto_match:
            return "incontournables", "instance"

        if any(keyword in combined for keyword in self._VISITS_KEYWORDS):
            return "visits", "keyword"
        if any(keyword in combined for keyword in self._SPOTS_KEYWORDS):
            return "spots", "keyword"
        if any(keyword in combined for keyword in self._INCONTOURNABLE_KEYWORDS):
            return "incontournables", "keyword"
        return None, "none"

    @staticmethod
    def _score(distance_m: float, importance: float, strength: str) -> float:
        distance_score = 1.0 / (1.0 + distance_m / 500.0)
        base = 0.6 * distance_score + 0.4 * importance
        bonus = 0.1 if strength == "instance" else 0.05 if strength == "keyword" else 0.0
        return base + bonus


__all__ = ["POI", "WikiPOIService"]
