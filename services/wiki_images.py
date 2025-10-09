"""Image discovery helpers backed by Wikidata and Wikimedia Commons."""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests
from PIL import Image, ImageDraw, ImageFont

from config import wiki_settings
from services.cache_utils import read_cache_json, write_cache_json

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ImageCandidate:
    url: str
    thumb_url: str | None
    width: int | None
    height: int | None
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageCandidate":
        return cls(
            url=data.get("url", ""),
            thumb_url=data.get("thumb_url"),
            width=data.get("width"),
            height=data.get("height"),
            source=data.get("source", "unknown"),
        )


class WikiImageService:
    _SLEEP_SECONDS = 0.12

    def __init__(self, lang: str = wiki_settings.WIKI_LANG_DEFAULT) -> None:
        self.lang = lang
        self.session = requests.Session()
        self.session.headers.update(wiki_settings.default_headers())

    def candidates(
        self,
        qid: str | None,
        title: str,
        city: str | None,
        country: str | None,
        limit: int = 5,
    ) -> List[ImageCandidate]:
        key = f"imgcand:{qid}:{title}:{city}:{country}:{limit}"
        cached = read_cache_json(key, wiki_settings.CACHE_TTL_SEC)
        if cached:
            return [ImageCandidate.from_dict(item) for item in cached.get("items", [])]

        collected: List[ImageCandidate] = []
        seen: set[str] = set()
        if qid:
            collected.extend(self._from_wikidata_p18(qid, seen))
            collected.extend(self._from_commons_category(qid, seen))
        if len(collected) < limit:
            collected.extend(
                self._from_commons_search(title, city, country, limit - len(collected), seen)
            )

        deduped = collected[:limit]
        if not deduped:
            placeholder = self._placeholder_candidate(title, city, country)
            write_cache_json(key, {"items": [placeholder.to_dict()]})
            return [placeholder]
        write_cache_json(key, {"items": [c.to_dict() for c in deduped]})
        return deduped

    def download(self, url: str | None) -> str:
        if not url:
            return self._placeholder_path("placeholder")
        response = self.session.get(url, timeout=wiki_settings.HTTP_TIMEOUT, stream=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise ValueError("URL is not an image")
        content = response.content
        if len(content) < 5 * 1024:
            raise ValueError("Image too small to keep")
        images_dir = Path(wiki_settings.IMAGES_DIR)
        images_dir.mkdir(parents=True, exist_ok=True)
        extension = self._extension_from_content_type(content_type) or self._extension_from_url(url)
        if not extension:
            extension = "jpg"
        slug = self._slugify(url)
        filename = f"{slug}.{extension}"
        path = images_dir / filename
        with path.open("wb") as fh:
            fh.write(content)
        return str(path)

    # --- Internal helpers -------------------------------------------------

    def _throttle(self) -> None:
        time.sleep(self._SLEEP_SECONDS)

    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        backoff = wiki_settings.RETRY_BASE_DELAY
        for attempt in range(wiki_settings.RETRIES + 1):
            try:
                response = self.session.get(url, params=params, timeout=wiki_settings.HTTP_TIMEOUT)
                response.raise_for_status()
                self._throttle()
                return response.json()
            except Exception as exc:  # pragma: no cover - network failures are rare in tests
                if attempt >= wiki_settings.RETRIES:
                    raise
                delay = backoff * (2 ** attempt) + random.uniform(0, wiki_settings.RETRY_JITTER)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def _from_wikidata_p18(self, qid: str, seen: set[str]) -> List[ImageCandidate]:
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }
        url = "https://www.wikidata.org/w/api.php"
        data = self._request_json(url, params)
        entity = data.get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        images = claims.get("P18", [])
        if not images:
            return []
        filenames = []
        for claim in images:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {})
            value = datavalue.get("value")
            if isinstance(value, str):
                filenames.append(value)
        if not filenames:
            return []
        return self._commons_imageinfo(filenames, "wikidata_p18", seen)

    def _from_commons_category(self, qid: str, seen: set[str]) -> List[ImageCandidate]:
        category_title = f"Category:{qid}"
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmnamespace": 6,
            "cmtype": "file",
            "cmlimit": 10,
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php"
        data = self._request_json(url, params)
        members = data.get("query", {}).get("categorymembers", [])
        filenames = [member.get("title") for member in members if member.get("title")]
        if not filenames:
            return []
        return self._commons_imageinfo(filenames, "commons_qid", seen)

    def _from_commons_search(
        self,
        title: str,
        city: str | None,
        country: str | None,
        limit: int,
        seen: set[str],
    ) -> List[ImageCandidate]:
        if limit <= 0:
            return []
        search_terms = [title]
        if city:
            search_terms.append(city)
        if country:
            search_terms.append(country)
        query = " ".join(f'"{term}"' for term in search_terms if term)
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": max(5, limit * 2),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|thumbmime",
            "iiurlwidth": 1600,
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php"
        data = self._request_json(url, params)
        pages = data.get("query", {}).get("pages", {})
        filenames = [page.get("title") for page in pages.values() if page.get("title")]
        return self._commons_imageinfo(filenames[:limit], "commons_text", seen)

    def _commons_imageinfo(
        self, filenames: Iterable[str], source: str, seen: set[str]
    ) -> List[ImageCandidate]:
        titles = [name for name in filenames if name]
        if not titles:
            return []
        params = {
            "action": "query",
            "titles": "|".join(titles[:50]),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|thumbmime",
            "iiurlwidth": 1600,
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php"
        data = self._request_json(url, params)
        pages = data.get("query", {}).get("pages", {})
        results: List[ImageCandidate] = []
        for page in pages.values():
            infos = page.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            mime = info.get("mime") or ""
            if not mime.startswith("image/"):
                continue
            width = info.get("width")
            height = info.get("height")
            if isinstance(width, int) and width < 800:
                continue
            if isinstance(height, int) and height < 600:
                continue
            url_full = info.get("url")
            if not url_full or url_full in seen:
                continue
            seen.add(url_full)
            candidate = ImageCandidate(
                url=url_full,
                thumb_url=info.get("thumburl"),
                width=width,
                height=height,
                source="wikidata_p18" if source == "wikidata_p18" else source,
            )
            results.append(candidate)
        return results

    def _placeholder_candidate(
        self, title: str, city: str | None, country: str | None
    ) -> ImageCandidate:
        path = self._placeholder_path(f"{title}-{city}-{country}")
        return ImageCandidate(url=path, thumb_url=None, width=None, height=None, source="placeholder")

    def _placeholder_path(self, seed: str) -> str:
        images_dir = Path(wiki_settings.IMAGES_DIR)
        images_dir.mkdir(parents=True, exist_ok=True)
        digest = sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()
        path = images_dir / f"placeholder-{digest}.jpg"
        if path.exists():
            return str(path)
        image = Image.new("RGB", (800, 600), color=(240, 240, 240))
        draw = ImageDraw.Draw(image)
        text = "Image non disponible"
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            ((800 - text_width) / 2, (600 - text_height) / 2),
            text,
            fill=(60, 60, 60),
            font=font,
        )
        image.save(path, format="JPEG", quality=85)
        return str(path)

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
        if not slug:
            slug = sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        return slug[:80]

    @staticmethod
    def _extension_from_content_type(content_type: str) -> str | None:
        mapping = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        return mapping.get(content_type.lower())

    @staticmethod
    def _extension_from_url(url: str) -> str | None:
        match = re.search(r"\.([a-zA-Z0-9]{3,4})(?:\?|$)", url)
        if not match:
            return None
        return match.group(1).lower()


__all__ = ["ImageCandidate", "WikiImageService"]
