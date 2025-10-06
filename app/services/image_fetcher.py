"""Robust image fetching for points of interest (POI).

This module implements a cascading lookup across Unsplash, Pexels and
Wikimedia Commons to retrieve at least one image for a given place of
interest.  The returned path always points to a local file.  A neutral
placeholder image is generated on-demand and used whenever all providers
fail.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw
from unidecode import unidecode


LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "MFYLocalApp/1.0 (+contact@yourdomain)",
    "Accept": "application/json, image/*",
}

TIMEOUT = 8
RETRIES = 2
BACKOFF_DELAYS = (0.5, 1.0)

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "out" / "images" / "poi"


def _ensure_placeholder() -> Path:
    """Create the placeholder image if missing and return its path."""

    path = BASE_DIR / "assets" / "no_image.png"
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1200, 800
    background = (235, 237, 240)
    accent = (170, 174, 179)
    image = Image.new("RGB", (width, height), color=background)
    draw = ImageDraw.Draw(image)

    margin_x = int(width * 0.1)
    margin_y = int(height * 0.15)
    draw.rectangle(
        [(margin_x, margin_y), (width - margin_x, height - margin_y)],
        outline=accent,
        width=6,
    )
    draw.line(
        [(margin_x, margin_y), (width - margin_x, height - margin_y)],
        fill=accent,
        width=6,
    )
    draw.line(
        [(margin_x, height - margin_y), (width - margin_x, margin_y)],
        fill=accent,
        width=6,
    )

    image.save(path, format="PNG")
    return path


NO_IMAGE_PLACEHOLDER = str(_ensure_placeholder())

SESSION = requests.Session()


def _build_headers(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    if not extra:
        return dict(HEADERS)
    merged = dict(HEADERS)
    merged.update(extra)
    return merged


def _slugify(value: str) -> str:
    value = unidecode(value or "").lower()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9\-_]", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip("-_")
    return value or "poi"


def _perform_request(
    url: str,
    provider: str,
    *,
    params: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
    stream: bool = False,
):
    """Perform an HTTP request with retries and logging."""

    for attempt in range(RETRIES + 1):
        try:
            response = SESSION.get(
                url,
                params=params,
                headers=_build_headers(headers),
                timeout=TIMEOUT,
                stream=stream,
            )
            status = response.status_code
            if status >= 400:
                LOGGER.warning("%s request failed (status=%s)", provider, status)
                response.close()
                retryable = status in {401, 403, 429} or status >= 500
                if attempt < RETRIES and retryable:
                    time.sleep(BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)])
                    continue
                return None
            return response
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            LOGGER.warning("%s request failed (status=%s): %s", provider, status, exc)
            if exc.response is not None:
                exc.response.close()
            if attempt < RETRIES:
                time.sleep(BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)])
                continue
            return None

    return None


def _fetch_json(
    url: str,
    provider: str,
    *,
    params: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
):
    response = _perform_request(url, provider, params=params, headers=headers)
    if response is None:
        return None
    try:
        data = response.json()
    except ValueError as exc:
        LOGGER.warning("%s returned invalid JSON: %s", provider, exc)
        return None
    finally:
        response.close()
    return data


def _download_image(url: str, slug: str, provider: str) -> Optional[str]:
    if not url:
        return None

    response = _perform_request(url, provider, headers=None, stream=True)
    if response is None:
        return None

    try:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            LOGGER.warning("%s invalid content-type: %s", provider, content_type)
            return None

        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        extension = ext_map.get(content_type, ".jpg")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{slug}-{digest}{extension}"
        target = OUTPUT_DIR / filename

        size = 0
        with open(target, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                handle.write(chunk)
                size += len(chunk)

        if size <= 5 * 1024:
            LOGGER.warning("%s image too small (%s bytes)", provider, size)
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            return None

        return str(target)
    finally:
        response.close()


def _try_unsplash(query: str, slug: str) -> Optional[str]:
    if not UNSPLASH_ACCESS_KEY:
        return None

    data = _fetch_json(
        "https://api.unsplash.com/search/photos",
        "unsplash",
        params={"query": query, "per_page": "10"},
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
    )
    if not data:
        return None

    for item in data.get("results", []):
        try:
            width = int(item.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
        if width < 800:
            continue
        urls = item.get("urls", {})
        image_url = urls.get("regular") or urls.get("full")
        path = _download_image(image_url, slug, "unsplash")
        if path:
            return path
    return None


def _try_pexels(query: str, slug: str) -> Optional[str]:
    if not PEXELS_API_KEY:
        return None

    data = _fetch_json(
        "https://api.pexels.com/v1/search",
        "pexels",
        params={"query": query, "per_page": "10"},
        headers={"Authorization": PEXELS_API_KEY},
    )
    if not data:
        return None

    for item in data.get("photos", []):
        try:
            width = int(item.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
        if width < 800:
            continue
        src = item.get("src", {})
        image_url = src.get("large2x") or src.get("large") or src.get("original")
        path = _download_image(image_url, slug, "pexels")
        if path:
            return path
    return None


def _try_wikimedia(query: str, slug: str) -> Optional[str]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages|imageinfo",
        "piprop": "original",
        "generator": "search",
        "gsrlimit": "10",
        "gsrsearch": query,
    }
    data = _fetch_json(
        "https://commons.wikimedia.org/w/api.php",
        "wikimedia",
        params=params,
    )
    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        original = page.get("original") or {}
        image_url = original.get("source")
        width = original.get("width")
        if not image_url and page.get("imageinfo"):
            info = page["imageinfo"][0]
            image_url = info.get("url") or info.get("thumburl")
            width = info.get("width")

        try:
            width_val = int(width or 0)
        except (TypeError, ValueError):
            width_val = 0
        if width_val and width_val < 800:
            continue

        path = _download_image(image_url, slug, "wikimedia")
        if path:
            return path

    return None


def get_poi_image(poi_name: str, city: Optional[str], country: Optional[str]) -> str:
    """Return the local image path for the given POI.

    When all providers fail, the neutral placeholder image is returned.
    """

    if not poi_name:
        return NO_IMAGE_PLACEHOLDER

    parts = [part for part in [poi_name, city or "", country or ""] if part]
    query = " ".join(parts).strip()
    slug = _slugify(query or poi_name)

    for fetcher in (_try_unsplash, _try_pexels, _try_wikimedia):
        path = fetcher(query, slug)
        if path:
            return path

    return NO_IMAGE_PLACEHOLDER


__all__ = ["get_poi_image", "NO_IMAGE_PLACEHOLDER"]

