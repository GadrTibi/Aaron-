"""Fetch images for POI cards using Unsplash, Pexels and Wikimedia."""

from __future__ import annotations

import io
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from mimetypes import guess_extension
from pathlib import Path
from typing import List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "images_debug.log"

_logger = logging.getLogger("app.services.image_fetcher")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

HEADERS = {
    "User-Agent": "MFYLocalApp/1.0 (+contact@yourdomain)",
    "Accept": "application/json, image/*",
}
TIMEOUT = 8
RETRY_STATUS = {429} | set(range(500, 600))
RETRY_DELAYS = (0.6, 1.2)
MIN_WIDTH = 800
MIN_FILE_SIZE = 5 * 1024

OUTPUT_DIR = Path("out/images/poi")
PLACEHOLDER_PATH = Path("assets/no_image.png")

_LAST_RESULT: Optional["ProviderAttempt"] = None


@dataclass
class ProviderAttempt:
    provider: str
    request_url: str
    status: str
    duration_ms: float
    image_url: Optional[str] = None
    width: Optional[int] = None
    message: str = ""
    local_path: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.local_path is not None


def _log(level: int, provider: str, poi: str, city: Optional[str], country: Optional[str], status: str, message: str) -> None:
    extra = f"provider={provider} | poi={poi} | city={city or ''} | country={country or ''} | status={status} | {message}"
    _logger.log(level, extra)


def _sleep(duration: float) -> None:
    time.sleep(duration)


def _prepare_url(url: str, params: Optional[dict]) -> str:
    req = requests.Request("GET", url, params=params)
    return req.prepare().url


def _send_request(
    url: str,
    *,
    provider: str,
    poi: str,
    city: Optional[str],
    country: Optional[str],
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> Tuple[Optional[requests.Response], str, float]:
    merged_headers = dict(HEADERS)
    if headers:
        merged_headers.update(headers)
    start = time.monotonic()
    response: Optional[requests.Response] = None
    status_repr = "ERR"
    attempts = len(RETRY_DELAYS) + 1
    for attempt_index in range(attempts):
        if attempt_index:
            _sleep(RETRY_DELAYS[attempt_index - 1])
        try:
            response = requests.request(
                "GET",
                url,
                params=params,
                headers=merged_headers,
                timeout=TIMEOUT,
                allow_redirects=True,
                proxies={"http": None, "https": None},
            )
            status_repr = str(response.status_code)
        except requests.RequestException as exc:
            status_repr = f"ERR:{type(exc).__name__}"
            _log(logging.WARNING if attempt_index < attempts - 1 else logging.ERROR, provider, poi, city, country, status_repr, str(exc))
            response = None
        else:
            if response.status_code in RETRY_STATUS and attempt_index < attempts - 1:
                _log(logging.WARNING, provider, poi, city, country, status_repr, "retrying")
                continue
            break
    duration_ms = (time.monotonic() - start) * 1000
    return response, status_repr, duration_ms


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s_-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-") or "image"


def _ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _ensure_placeholder() -> str:
    if PLACEHOLDER_PATH.exists():
        return str(PLACEHOLDER_PATH)
    PLACEHOLDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (900, 600), "#FBF8E4")
    draw = ImageDraw.Draw(img)
    text = "Image non disponible"
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((900 - tw) / 2, (600 - th) / 2), text, fill="#033E41", font=font)
    img.save(PLACEHOLDER_PATH, "PNG")
    return str(PLACEHOLDER_PATH)


def _download_image(
    image_url: str,
    *,
    provider: str,
    poi: str,
    city: Optional[str],
    country: Optional[str],
    slug: str,
) -> Tuple[Optional[str], str]:
    response, status, _ = _send_request(
        image_url,
        provider=provider,
        poi=poi,
        city=city,
        country=country,
        headers={"Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
    )
    if response is None:
        return None, status
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        _log(logging.WARNING, provider, poi, city, country, status, f"invalid mime {content_type}")
        return None, status
    data = response.content
    if len(data) < MIN_FILE_SIZE:
        _log(logging.WARNING, provider, poi, city, country, status, "file too small")
        return None, status
    try:
        image = Image.open(io.BytesIO(data))
        width, _height = image.size
    except Exception as exc:
        _log(logging.WARNING, provider, poi, city, country, status, f"PIL error {exc}")
        return None, status
    if width < MIN_WIDTH:
        _log(logging.WARNING, provider, poi, city, country, status, f"width {width} < {MIN_WIDTH}")
        return None, status
    ext = None
    if content_type:
        ext = guess_extension(content_type.split(";")[0].strip())
    if ext in {".jpe", ".jpeg"}:
        ext = ".jpg"
    if not ext:
        match = re.search(r"\.(jpg|jpeg|png|webp)$", image_url, re.IGNORECASE)
        if match:
            ext = ".jpg" if match.group(1).lower() == "jpeg" else f".{match.group(1).lower()}"
    if not ext:
        ext = ".jpg"
    out_dir = _ensure_output_dir()
    out_path = out_dir / f"{slug}{ext}"
    with open(out_path, "wb") as fh:
        fh.write(data)
    _log(logging.INFO, provider, poi, city, country, status, f"saved {out_path} ({len(data)} bytes, width={width})")
    return str(out_path), status


def _unsplash_attempt(query: str, *, poi: str, city: Optional[str], country: Optional[str]) -> ProviderAttempt:
    params = {"query": query, "per_page": 10}
    request_url = _prepare_url("https://api.unsplash.com/search/photos", params)
    key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not key:
        message = "UNSPLASH_ACCESS_KEY missing"
        _log(logging.WARNING, "Unsplash", poi, city, country, "0", message)
        return ProviderAttempt("Unsplash", request_url, "0", 0.0, message=message)
    response, status, duration = _send_request(
        "https://api.unsplash.com/search/photos",
        provider="Unsplash",
        poi=poi,
        city=city,
        country=country,
        params=params,
        headers={"Authorization": f"Client-ID {key}"},
    )
    attempt = ProviderAttempt("Unsplash", request_url, status, duration)
    if response is None:
        attempt.message = "no response"
        return attempt
    if response.status_code >= 400:
        attempt.message = f"HTTP {response.status_code}"
        _log(logging.WARNING, "Unsplash", poi, city, country, status, attempt.message)
        return attempt
    try:
        data = response.json()
    except ValueError as exc:
        attempt.message = f"json error {exc}"
        _log(logging.WARNING, "Unsplash", poi, city, country, status, attempt.message)
        return attempt
    for item in data.get("results", []):
        width = item.get("width")
        if width is not None and width < MIN_WIDTH:
            continue
        urls = item.get("urls", {})
        image_url = urls.get("regular") or urls.get("full") or urls.get("raw")
        if image_url:
            attempt.image_url = image_url
            attempt.width = width
            attempt.message = "candidate"
            _log(logging.INFO, "Unsplash", poi, city, country, status, f"candidate {image_url}")
            return attempt
    attempt.message = "no suitable image"
    _log(logging.WARNING, "Unsplash", poi, city, country, status, attempt.message)
    return attempt


def _pexels_attempt(query: str, *, poi: str, city: Optional[str], country: Optional[str]) -> ProviderAttempt:
    params = {"query": query, "per_page": 10}
    request_url = _prepare_url("https://api.pexels.com/v1/search", params)
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        message = "PEXELS_API_KEY missing"
        _log(logging.WARNING, "Pexels", poi, city, country, "0", message)
        return ProviderAttempt("Pexels", request_url, "0", 0.0, message=message)
    response, status, duration = _send_request(
        "https://api.pexels.com/v1/search",
        provider="Pexels",
        poi=poi,
        city=city,
        country=country,
        params=params,
        headers={"Authorization": key},
    )
    attempt = ProviderAttempt("Pexels", request_url, status, duration)
    if response is None:
        attempt.message = "no response"
        return attempt
    if response.status_code >= 400:
        attempt.message = f"HTTP {response.status_code}"
        _log(logging.WARNING, "Pexels", poi, city, country, status, attempt.message)
        return attempt
    try:
        data = response.json()
    except ValueError as exc:
        attempt.message = f"json error {exc}"
        _log(logging.WARNING, "Pexels", poi, city, country, status, attempt.message)
        return attempt
    for item in data.get("photos", []):
        width = item.get("width")
        if width is not None and width < MIN_WIDTH:
            continue
        src = item.get("src", {})
        image_url = src.get("large") or src.get("large2x") or src.get("original")
        if image_url:
            attempt.image_url = image_url
            attempt.width = width
            attempt.message = "candidate"
            _log(logging.INFO, "Pexels", poi, city, country, status, f"candidate {image_url}")
            return attempt
    attempt.message = "no suitable image"
    _log(logging.WARNING, "Pexels", poi, city, country, status, attempt.message)
    return attempt


def _wikimedia_attempt(query: str, *, poi: str, city: Optional[str], country: Optional[str]) -> ProviderAttempt:
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages|imageinfo",
        "piprop": "original",
        "generator": "search",
        "gsrlimit": 10,
        "gsrsearch": query,
    }
    request_url = _prepare_url("https://commons.wikimedia.org/w/api.php", params)
    response, status, duration = _send_request(
        "https://commons.wikimedia.org/w/api.php",
        provider="Wikimedia",
        poi=poi,
        city=city,
        country=country,
        params=params,
    )
    attempt = ProviderAttempt("Wikimedia", request_url, status, duration)
    if response is None:
        attempt.message = "no response"
        return attempt
    if response.status_code >= 400:
        attempt.message = f"HTTP {response.status_code}"
        _log(logging.WARNING, "Wikimedia", poi, city, country, status, attempt.message)
        return attempt
    try:
        data = response.json()
    except ValueError as exc:
        attempt.message = f"json error {exc}"
        _log(logging.WARNING, "Wikimedia", poi, city, country, status, attempt.message)
        return attempt
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        original = page.get("original")
        imageinfo = page.get("imageinfo") or []
        width = None
        image_url = None
        if original:
            image_url = original.get("source")
            width = original.get("width")
        if not image_url and imageinfo:
            image_url = imageinfo[0].get("url")
            width = imageinfo[0].get("width")
        if width is not None and width < MIN_WIDTH:
            continue
        if image_url:
            attempt.image_url = image_url
            attempt.width = width
            attempt.message = "candidate"
            _log(logging.INFO, "Wikimedia", poi, city, country, status, f"candidate {image_url}")
            return attempt
    attempt.message = "no suitable image"
    _log(logging.WARNING, "Wikimedia", poi, city, country, status, attempt.message)
    return attempt


def _provider_chain() -> List:
    return [_unsplash_attempt, _pexels_attempt, _wikimedia_attempt]


def _build_query(poi_name: str, city: Optional[str], country: Optional[str]) -> str:
    parts = [poi_name]
    if city:
        parts.append(city)
    if country:
        parts.append(country)
    return " ".join([p for p in parts if p]).strip()


def _cascade(poi_name: str, city: Optional[str], country: Optional[str]) -> Tuple[str, List[ProviderAttempt]]:
    query = _build_query(poi_name, city, country)
    slug = _slugify(query or poi_name)
    attempts: List[ProviderAttempt] = []
    for provider_fn in _provider_chain():
        attempt = provider_fn(query, poi=poi_name, city=city, country=country)
        if attempt.image_url:
            path, status = _download_image(
                attempt.image_url,
                provider=attempt.provider,
                poi=poi_name,
                city=city,
                country=country,
                slug=slug,
            )
            attempt.status = status
            if path:
                attempt.local_path = path
                attempts.append(attempt)
                return path, attempts
        attempts.append(attempt)
    placeholder = _ensure_placeholder()
    placeholder_attempt = ProviderAttempt(
        provider="placeholder",
        request_url="",
        status="0",
        duration_ms=0.0,
        message="fallback placeholder",
        local_path=placeholder,
    )
    attempts.append(placeholder_attempt)
    _log(logging.ERROR, "placeholder", poi_name, city, country, "0", "Using placeholder")
    return placeholder, attempts


def get_poi_image(poi_name: str, city: Optional[str] = None, country: Optional[str] = None) -> str:
    global _LAST_RESULT
    path, attempts = _cascade(poi_name, city, country)
    _LAST_RESULT = attempts[-1]
    return path


def debug_fetch_poi(poi_name: str, city: Optional[str] = None, country: Optional[str] = None) -> Tuple[str, List[ProviderAttempt]]:
    return _cascade(poi_name, city, country)


def get_last_result() -> Optional[ProviderAttempt]:
    return _LAST_RESULT


__all__ = ["get_poi_image", "debug_fetch_poi", "get_last_result", "ProviderAttempt"]
