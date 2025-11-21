"""Utilities for saving user-uploaded images."""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:  # Optional pillow resizing
    from PIL import Image
except Exception:  # pragma: no cover - pillow may be unavailable at runtime
    Image = None


_ALLOWED_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def _slugify(value: str) -> str:
    value = (value or "upload").lower()
    slug = re.sub(r"[^a-z0-9-_]+", "-", value)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "upload"


def _deduce_extension(file: Any) -> str:
    content_type = getattr(file, "type", "") or ""
    if not content_type.startswith("image/"):
        raise ValueError("Fichier invalide: type non image")
    if content_type in _ALLOWED_EXTENSIONS:
        return _ALLOWED_EXTENSIONS[content_type]
    subtype = content_type.split("/", 1)[-1]
    if subtype:
        return f".{subtype.split('+')[0]}"  # handle things like image/svg+xml
    return ".jpg"


def save_uploaded_image(file: Any, prefix: str, dest_dir: str = "out/images/visits") -> str:
    """
    Persist an uploaded image to the local filesystem.

    Args:
        file: The uploaded file object coming from Streamlit.
        prefix: Prefix for the generated filename.
        dest_dir: Destination directory for saved images.

    Returns:
        The path of the saved image.
    """

    extension = _deduce_extension(file)
    slug_prefix = _slugify(prefix)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{slug_prefix}-{timestamp}{extension}"

    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / filename

    with path.open("wb") as fh:
        fh.write(file.getbuffer())

    if Image is not None:
        try:
            with Image.open(path) as img:
                img.thumbnail((1600, 1600))
                img.save(path)
        except Exception:
            pass

    if not path.exists() or os.path.getsize(path) <= 5 * 1024:
        if path.exists():
            path.unlink()
        raise ValueError("Fichier trop petit ou invalide")

    return str(path)
