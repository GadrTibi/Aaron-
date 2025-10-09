"""Settings for Wikimedia-based services."""
from __future__ import annotations

from typing import Dict

USER_AGENT: str = "MFYLocalApp/1.0 (+contact@yourdomain)"
WIKI_LANG_DEFAULT: str = "fr"
CACHE_DIR: str = "out/cache/wiki"
IMAGES_DIR: str = "out/images/visits"
CACHE_TTL_SEC: int = 60 * 60 * 24 * 2
HTTP_TIMEOUT: int = 10
RETRIES: int = 2
RETRY_BASE_DELAY: float = 0.6
RETRY_JITTER: float = 0.2


def default_headers() -> Dict[str, str]:
    """Return default HTTP headers for Wikimedia APIs."""
    return {"User-Agent": USER_AGENT}


__all__ = [
    "USER_AGENT",
    "WIKI_LANG_DEFAULT",
    "CACHE_DIR",
    "IMAGES_DIR",
    "CACHE_TTL_SEC",
    "HTTP_TIMEOUT",
    "RETRIES",
    "RETRY_BASE_DELAY",
    "RETRY_JITTER",
    "default_headers",
]
