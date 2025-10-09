"""Image helpers relying on Wikimedia sources."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

from . import wiki_client

HEADERS = wiki_client.HEADERS
_IMAGES_DIR = Path("out/images/poi")
_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
_PLACEHOLDER_PATH = Path("assets/no_image.png")


def ensure_placeholder() -> str:
    if _PLACEHOLDER_PATH.exists():
        return str(_PLACEHOLDER_PATH)
    _PLACEHOLDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (800, 600), color="#FBF8E4")
    draw = ImageDraw.Draw(img)
    text = "Image non disponible"
    font = ImageFont.load_default()
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        text_width, text_height = font.getsize(text)  # type: ignore[attr-defined]
    position = ((img.width - text_width) // 2, (img.height - text_height) // 2)
    draw.text(position, text, fill="#033E41", font=font)
    img.save(_PLACEHOLDER_PATH, format="PNG")
    return str(_PLACEHOLDER_PATH)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "image"


def _unique_append(container: List[Dict[str, str]], seen: set[str], candidate: Dict[str, str], max_items: int) -> None:
    url = candidate.get("url")
    if not url or url in seen or len(container) >= max_items:
        return
    seen.add(url)
    container.append(candidate)


def candidate_images(pageid: int, qid: Optional[str], lang: str = "fr", max_items: int = 5) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    seen: set[str] = set()

    details = wiki_client.page_details([pageid], lang=lang)
    pages = details.get("query", {}).get("pages", {})
    page_data = next(iter(pages.values()), {}) if pages else {}

    original = page_data.get("original") or {}
    original_url = original.get("source")
    if original_url:
        _unique_append(results, seen, {"url": original_url, "provider": "wikipedia"}, max_items)

    if not qid:
        pageprops = page_data.get("pageprops") or {}
        if isinstance(pageprops, dict):
            qid = pageprops.get("wikibase_item")

    commons_categories: List[str] = []
    if qid:
        entity = wiki_client.wikidata_entity(qid)
        entities = entity.get("entities", {}) if isinstance(entity, dict) else {}
        data = entities.get(qid, {})
        claims = data.get("claims", {}) if isinstance(data, dict) else {}
        p18 = claims.get("P18") or []
        for claim in p18:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {}) if isinstance(mainsnak, dict) else {}
            value = datavalue.get("value")
            if isinstance(value, str):
                commons_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{value.replace(' ', '_')}"
                _unique_append(results, seen, {"url": commons_url, "provider": "wikidata"}, max_items)
        p373 = claims.get("P373") or []
        for claim in p373:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {}) if isinstance(mainsnak, dict) else {}
            value = datavalue.get("value")
            if isinstance(value, str):
                commons_categories.append(value)
        sitelinks = data.get("sitelinks", {}) if isinstance(data, dict) else {}
        commons_site = sitelinks.get("commonswiki")
        if isinstance(commons_site, dict):
            title = commons_site.get("title")
            if isinstance(title, str) and title.startswith("Category:"):
                commons_categories.append(title.split(":", 1)[1])

    for category in commons_categories:
        images = wiki_client.commons_category_images(category, limit=max_items)
        for item in images:
            url = item.get("url")
            if not url:
                continue
            _unique_append(results, seen, {"url": url, "provider": "commons"}, max_items)
            if len(results) >= max_items:
                break
        if len(results) >= max_items:
            break

    return results[:max_items]


def _safe_extension(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path)
    if ext.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return ext.lower()
    return ".jpg"


def download_image(url: str, slug: str) -> str:
    ensure_placeholder()
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        response.raise_for_status()
    except Exception:  # noqa: BLE001
        return ensure_placeholder()

    ext = _safe_extension(url)
    slug = slugify(slug)
    path = _IMAGES_DIR / f"{slug}{ext}"
    counter = 1
    while path.exists():
        path = _IMAGES_DIR / f"{slug}-{counter}{ext}"
        counter += 1

    with open(path, "wb") as fh:
        fh.write(response.content)

    if path.stat().st_size < 5 * 1024:
        path.unlink(missing_ok=True)
        return ensure_placeholder()

    return str(path)
