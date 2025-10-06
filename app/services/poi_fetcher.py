"""Unified Point Of Interest (POI) fetching service.

This module centralises the logic required to retrieve nearby points of
interest for several categories.  It orchestrates calls to the Overpass API
with resilient mirror rotation, request backoff and optional query slimming,
and falls back to Wikipedia's GeoSearch when Overpass fails.  Results are
cached on disk for 24 hours in order to limit the amount of network calls
performed by the local application.

The module also exposes a light logging facility that writes detailed traces
of each fetch in ``logs/poi_debug.log``.  The log entries contain the
requested category, coordinates, radius, HTTP status, latency and provider
used, which greatly simplifies debugging of field issues.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "poi_debug.log"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("app.poi")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger


LOGGER = _build_logger()


# ---------------------------------------------------------------------------
# Dataclasses used to pass results/metadata between components
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FetchResult:
    items: List[Dict[str, Any]]
    provider: str
    endpoint: Optional[str] = None
    status: Optional[int] = None
    duration_ms: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class OverpassError(RuntimeError):
    """Raised when the Overpass client exhausts all endpoints without data."""

    def __init__(self, message: str, attempts: Iterable[Dict[str, Any]] | None = None):
        super().__init__(message)
        self.attempts = list(attempts or [])


# ---------------------------------------------------------------------------
# Overpass client
# ---------------------------------------------------------------------------


class OverpassClient:
    ENDPOINTS: List[str] = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.belgium.be/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]

    _BASE_HEADERS: Dict[str, str] = {
        "User-Agent": "MFYLocalApp/1.0 (+contact@yourdomain)",
        "Accept": "application/json",
    }

    _CATEGORY_QUERIES: Dict[str, List[str]] = {
        "transport": [
            "nwr(around:{radius},{lat},{lon})[public_transport];",
            "nwr(around:{radius},{lat},{lon})[highway=bus_stop];",
            "nwr(around:{radius},{lat},{lon})[railway=station];",
            "nwr(around:{radius},{lat},{lon})[railway=tram_stop];",
        ],
        "incontournables": [
            "nwr(around:{radius},{lat},{lon})[tourism~\"attraction|museum|gallery|viewpoint|theme_park|zoo\"];",
            "nwr(around:{radius},{lat},{lon})[historic];",
            "nwr(around:{radius},{lat},{lon})[amenity~\"place_of_worship|theatre\"];",
            "nwr(around:{radius},{lat},{lon})[leisure~\"park|garden\"];",
        ],
        "lieux_a_visiter": [
            "nwr(around:{radius},{lat},{lon})[tourism~\"attraction|museum|gallery|viewpoint|theme_park|zoo\"];",
            "nwr(around:{radius},{lat},{lon})[historic];",
            "nwr(around:{radius},{lat},{lon})[amenity~\"place_of_worship|theatre\"];",
            "nwr(around:{radius},{lat},{lon})[leisure~\"park|garden\"];",
        ],
        "spots": [
            "nwr(around:{radius},{lat},{lon})[tourism=viewpoint];",
            "nwr(around:{radius},{lat},{lon})[natural~\"cliff|peak|beach|sand_dune\"];",
            "nwr(around:{radius},{lat},{lon})[leisure~\"park|nature_reserve\"];",
        ],
    }

    _LIGHT_QUERIES: Dict[str, List[str]] = {
        "transport": [
            "nwr(around:{radius},{lat},{lon})[highway=bus_stop];",
            "nwr(around:{radius},{lat},{lon})[railway=station];",
        ],
        "incontournables": [
            "nwr(around:{radius},{lat},{lon})[tourism~\"attraction|museum\"];",
            "nwr(around:{radius},{lat},{lon})[historic];",
        ],
        "lieux_a_visiter": [
            "nwr(around:{radius},{lat},{lon})[tourism~\"attraction|museum\"];",
            "nwr(around:{radius},{lat},{lon})[historic];",
        ],
        "spots": [
            "nwr(around:{radius},{lat},{lon})[tourism=viewpoint];",
            "nwr(around:{radius},{lat},{lon})[natural~\"cliff|peak|beach\"];",
        ],
    }

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        logger: logging.Logger = LOGGER,
        timeout: int = 35,
        retries_per_endpoint: int = 2,
    ) -> None:
        self._session = session or requests.Session()
        self._logger = logger
        self._timeout = timeout
        self._retries_per_endpoint = retries_per_endpoint

    # ------------------------------ Public API ------------------------------

    def fetch(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        category: str,
        *,
        lang: str = "fr",
    ) -> FetchResult:
        if category not in self._CATEGORY_QUERIES:
            raise ValueError(f"Unknown category '{category}'")

        attempts: List[Dict[str, Any]] = []
        zero_result: Optional[FetchResult] = None

        for lighten_pass, light in enumerate((False, True), start=1):
            query = self._build_query(lat, lon, radius_m, category, light)
            endpoints = self.ENDPOINTS if not light else self.ENDPOINTS[:1]

            for endpoint in endpoints:
                if not self._endpoint_available(endpoint):
                    attempts.append({
                        "endpoint": endpoint,
                        "status": None,
                        "error": "skipped_status_check",
                        "light": light,
                    })
                    continue

                for retry_index in range(self._retries_per_endpoint + 1):
                    start = time.perf_counter()
                    status: Optional[int] = None
                    try:
                        response = self._session.post(
                            endpoint,
                            data={"data": query},
                            headers=self._BASE_HEADERS,
                            timeout=self._timeout,
                        )
                        status = response.status_code
                        duration_ms = (time.perf_counter() - start) * 1000.0

                        if status >= 400:
                            message = f"HTTP {status}"
                            attempts.append({
                                "endpoint": endpoint,
                                "status": status,
                                "duration_ms": duration_ms,
                                "light": light,
                                "error": message,
                            })
                            if status in (429, 504) or status >= 500:
                                if retry_index < self._retries_per_endpoint:
                                    self._sleep_with_backoff(retry_index)
                                    continue
                            break

                        data = response.json()
                        items = self._parse_elements(data.get("elements", []))
                        for item in items:
                            item.setdefault("source", "overpass")
                        attempts.append({
                            "endpoint": endpoint,
                            "status": status,
                            "duration_ms": duration_ms,
                            "light": light,
                            "items": len(items),
                        })

                        if items:
                            return FetchResult(
                                items=items,
                                provider="overpass",
                                endpoint=endpoint,
                                status=status,
                                duration_ms=duration_ms,
                                meta={"light": light, "attempts": attempts},
                            )

                        zero_result = FetchResult(
                            items=[],
                            provider="overpass",
                            endpoint=endpoint,
                            status=status,
                            duration_ms=duration_ms,
                            meta={"light": light, "attempts": attempts},
                        )
                        break
                    except requests.RequestException as exc:  # pragma: no cover - network error branch
                        duration_ms = (time.perf_counter() - start) * 1000.0
                        attempts.append({
                            "endpoint": endpoint,
                            "status": status,
                            "duration_ms": duration_ms,
                            "light": light,
                            "error": str(exc),
                        })
                        if retry_index < self._retries_per_endpoint:
                            self._sleep_with_backoff(retry_index)
                            continue
                        break

                # move to next endpoint

            if zero_result and not zero_result.items and not light:
                # Run light query pass if base query yielded nothing
                continue
            if zero_result and zero_result.items:
                return zero_result
            if zero_result and light:
                return zero_result

        raise OverpassError("Overpass query failed", attempts)

    # ----------------------------- Internal utils ---------------------------

    def _endpoint_available(self, endpoint: str) -> bool:
        status_url = endpoint.replace("/interpreter", "/status")
        try:
            response = self._session.get(status_url, headers=self._BASE_HEADERS, timeout=3)
            text = response.text.lower()
            if "available slots" in text and "0" in text:
                return False
        except requests.RequestException:
            return True
        return True

    def _sleep_with_backoff(self, retry_index: int) -> None:
        base = 0.6 * (2 ** retry_index)
        delay = base * random.uniform(0.8, 1.2)
        time.sleep(delay)

    def _build_query(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        category: str,
        light: bool,
    ) -> str:
        blocks = self._LIGHT_QUERIES[category] if light else self._CATEGORY_QUERIES[category]
        body = "\n  ".join(block.format(radius=radius_m, lat=lat, lon=lon) for block in blocks)
        return f"""[out:json][timeout:45];
(
  {body}
);
out center 200;
"""

    def _parse_elements(self, elements: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        parsed: List[Dict[str, Any]] = []
        for el in elements:
            tags = el.get("tags", {}) or {}
            name = tags.get("name", "")
            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                center = el.get("center") or {}
                lat = center.get("lat")
                lon = center.get("lon")
            if lat is None or lon is None:
                continue
            parsed.append(
                {
                    "id": el.get("id"),
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "tags": tags,
                }
            )
        return parsed


# ---------------------------------------------------------------------------
# Wikipedia fallback client
# ---------------------------------------------------------------------------


class WikipediaClient:
    _USER_AGENT = "MFYLocalApp/1.0 (+contact@yourdomain)"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()

    def fetch(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        *,
        lang: str = "fr",
    ) -> FetchResult:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius_m,
            "gslimit": 20,
            "format": "json",
        }
        response = self._session.get(
            url,
            params=params,
            headers={"User-Agent": self._USER_AGENT},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        items: List[Dict[str, Any]] = []
        for entry in data.get("query", {}).get("geosearch", []):
            items.append(
                {
                    "id": entry.get("pageid"),
                    "name": entry.get("title", ""),
                    "lat": entry.get("lat"),
                    "lon": entry.get("lon"),
                    "distance": entry.get("dist"),
                    "tags": {"source": "wikipedia"},
                    "source": "wikipedia",
                }
            )
        return FetchResult(
            items=items,
            provider="wikipedia",
            endpoint=url,
            status=response.status_code,
            duration_ms=None,
        )


# ---------------------------------------------------------------------------
# Disk cache utilities
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


# ---------------------------------------------------------------------------
# Main service exposed to the rest of the application
# ---------------------------------------------------------------------------


class POIService:
    CACHE_DIR = Path("out/cache/poi")
    CACHE_VERSION = "1"
    CACHE_TTL_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        *,
        overpass_client: Optional[OverpassClient] = None,
        wikipedia_client: Optional[WikipediaClient] = None,
        logger: logging.Logger = LOGGER,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._logger = logger
        self._overpass = overpass_client or OverpassClient(logger=logger)
        self._wikipedia = wikipedia_client or WikipediaClient()
        self._cache_dir = cache_dir or self.CACHE_DIR
        _ensure_dir(self._cache_dir)
        self._last_result: Optional[FetchResult] = None

    @property
    def last_result(self) -> Optional[FetchResult]:
        return self._last_result

    def get_pois(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        category: str,
        *,
        lang: str = "fr",
    ) -> List[Dict[str, Any]]:
        cache_key = self._cache_key(lat, lon, radius_m, category, lang)
        cached = self._read_cache(cache_key)
        if cached:
            items = cached.get("items", [])
            provider = cached.get("provider", "")
            self._last_result = FetchResult(items=items, provider=provider)
            self._logger.info(
                "cache_hit | category=%s | lat=%.6f | lon=%.6f | radius=%s | provider=%s | items=%s",
                category,
                lat,
                lon,
                radius_m,
                provider,
                len(items),
            )
            return items

        provider_result: Optional[FetchResult] = None
        overpass_attempts: List[Dict[str, Any]] = []
        try:
            provider_result = self._overpass.fetch(lat, lon, radius_m, category, lang=lang)
        except OverpassError as exc:
            overpass_attempts = exc.attempts
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.exception("unexpected overpass error: %s", exc)

        if provider_result and provider_result.items:
            items = self._with_distances(lat, lon, provider_result.items)
            provider_result.items = items
            self._write_cache(cache_key, provider_result)
            self._last_result = provider_result
            self._log_summary(provider_result, category, lat, lon, radius_m)
            return items

        try:
            wikipedia_result = self._wikipedia.fetch(lat, lon, radius_m, lang=lang)
        except requests.RequestException as exc:
            self._logger.warning(
                "wikipedia_error | category=%s | lat=%.6f | lon=%.6f | radius=%s | error=%s",
                category,
                lat,
                lon,
                radius_m,
                exc,
            )
            empty_result = FetchResult(items=[], provider="wikipedia")
            self._last_result = empty_result
            self._log_summary(
                empty_result,
                category,
                lat,
                lon,
                radius_m,
                extra_meta={"overpass_attempts": overpass_attempts, "error": str(exc)},
            )
            return []

        wikipedia_result.items = self._with_distances(lat, lon, wikipedia_result.items)
        self._write_cache(cache_key, wikipedia_result)
        self._last_result = wikipedia_result
        self._log_summary(
            wikipedia_result,
            category,
            lat,
            lon,
            radius_m,
            extra_meta={"overpass_attempts": overpass_attempts},
        )
        return wikipedia_result.items

    # -------------------------- Cache helpers ------------------------------

    def _cache_key(
        self, lat: float, lon: float, radius_m: int, category: str, lang: str
    ) -> str:
        raw = f"{lat:.6f}|{lon:.6f}|{radius_m}|{category}|{lang}|{self.CACHE_VERSION}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        ts = payload.get("ts")
        if not isinstance(ts, (int, float)):
            return None
        if time.time() - ts > self.CACHE_TTL_SECONDS:
            return None
        return payload

    def _write_cache(self, key: str, result: FetchResult) -> None:
        path = self._cache_path(key)
        payload = {
            "ts": time.time(),
            "provider": result.provider,
            "items": result.items,
        }
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except OSError:  # pragma: no cover - filesystem errors ignored
            self._logger.warning("cache_write_failed | path=%s", path)

    # --------------------------- Misc helpers ------------------------------

    def _with_distances(
        self, lat: float, lon: float, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        enriched = []
        for item in items:
            item_lat = item.get("lat")
            item_lon = item.get("lon")
            if item_lat is None or item_lon is None:
                distance = None
            else:
                distance = _haversine(lat, lon, float(item_lat), float(item_lon))
            enriched.append({**item, "distance": distance, "source": item.get("source") or result_source(item)})
        enriched.sort(key=lambda el: el.get("distance") or float("inf"))
        return enriched

    def _log_summary(
        self,
        result: FetchResult,
        category: str,
        lat: float,
        lon: float,
        radius_m: int,
        *,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        meta = {
            "endpoint": result.endpoint,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "items": len(result.items),
            "provider": result.provider,
        }
        if extra_meta:
            meta.update(extra_meta)
        self._logger.info(
            "fetch | category=%s | lat=%.6f | lon=%.6f | radius=%s | %s",
            category,
            lat,
            lon,
            radius_m,
            " | ".join(f"{k}={v}" for k, v in meta.items()),
        )


def result_source(item: Dict[str, Any]) -> str:
    source = item.get("source")
    if source:
        return str(source)
    tags = item.get("tags") or {}
    if isinstance(tags, dict) and tags.get("source"):
        return str(tags.get("source"))
    return "overpass"


__all__ = ["POIService", "OverpassClient", "WikipediaClient", "FetchResult", "OverpassError"]

