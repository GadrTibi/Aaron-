"""Client helpers for Wikimedia APIs with local caching."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS: Dict[str, str] = {
    "User-Agent": "MFYLocalApp/1.0 (+contact@yourdomain)",
    "Accept": "application/json",
}

CACHE_TTL_SECONDS = 30 * 24 * 3600
REQUEST_TIMEOUT = 8
RETRY_TOTAL = 2
RETRY_BACKOFF = 0.6

_CACHE_ROOT = Path("out/cache/wiki")
_LOG_PATH = Path("logs/wiki_debug.log")

for directory in (_CACHE_ROOT, _LOG_PATH.parent):
    directory.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger("services.wiki_client")
if not _logger.handlers:
    handler = logging.FileHandler(_LOG_PATH)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)

_session = requests.Session()
retry = Retry(
    total=RETRY_TOTAL,
    backoff_factor=RETRY_BACKOFF,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=retry)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def _sha1_from_items(items: Iterable[tuple[str, Any]]) -> str:
    encoded = json.dumps(sorted(items), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _cached_get(url: str, params: Dict[str, Any], cache_key: str) -> Dict[str, Any]:
    cache_dir = _CACHE_ROOT / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _sha1_from_items(params.items())
    cache_file = cache_dir / f"{key}.json"

    now = time.time()
    if cache_file.exists():
        try:
            mtime = cache_file.stat().st_mtime
            if now - mtime < CACHE_TTL_SECONDS:
                with cache_file.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except (OSError, json.JSONDecodeError):
            cache_file.unlink(missing_ok=True)

    start = time.perf_counter()
    response: Response | None = None
    try:
        response = _session.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        with cache_file.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        elapsed = (time.perf_counter() - start) * 1000
        count = 0
        if isinstance(payload, dict):
            if "query" in payload and isinstance(payload["query"], dict):
                if "geosearch" in payload["query"]:
                    count = len(payload["query"].get("geosearch", []))
                elif "pages" in payload["query"]:
                    count = len(payload["query"].get("pages", {}))
        _logger.info("GET %s | %s | %.0f ms | %s", url, cache_key, elapsed, count)
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Request failed for %s with params %s: %s", url, params, exc)
        if cache_file.exists():
            try:
                with cache_file.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                pass
        raise
    finally:
        if response is not None:
            response.close()


def geosearch(lat: float, lon: float, radius_m: int, lang: str = "fr", limit: int = 50) -> Dict[str, Any]:
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": radius_m,
        "gslimit": limit,
        "format": "json",
    }
    url = WIKI_API.format(lang=lang)
    return _cached_get(url, params, cache_key="geosearch")


def page_details(pageids: List[int], lang: str = "fr") -> Dict[str, Any]:
    ids_str = "|".join(str(pid) for pid in pageids)
    params = {
        "action": "query",
        "prop": "pageimages|coordinates|categories|pageprops|info|description",
        "pageids": ids_str,
        "piprop": "original",
        "pilicense": "any",
        "cllimit": "max",
        "format": "json",
        "inprop": "url",
    }
    url = WIKI_API.format(lang=lang)
    return _cached_get(url, params, cache_key="page_details")


def wikidata_entity(qid: str) -> Dict[str, Any]:
    url = WIKIDATA_ENTITY.format(qid=qid)
    params = {"format": "json"}
    return _cached_get(url, params, cache_key="wikidata_entity")


def commons_category_images(category: str, limit: int = 5) -> List[Dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtype": "file",
        "gcmtitle": f"Category:{category}",
        "gcmlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1600,
        "format": "json",
    }
    data = _cached_get(COMMONS_API, params, cache_key="commons_category_images")
    results: List[Dict[str, Any]] = []
    query = data.get("query") if isinstance(data, dict) else None
    pages = query.get("pages", {}) if isinstance(query, dict) else {}
    for page in pages.values():
        image_info = page.get("imageinfo") if isinstance(page, dict) else None
        if not image_info:
            continue
        info = image_info[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        results.append({
            "title": page.get("title"),
            "url": url,
            "descriptionurl": info.get("descriptionurl"),
        })
        if len(results) >= limit:
            break
    return results
