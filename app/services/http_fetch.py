import os, time, hashlib
import requests

DEFAULT_UA = os.getenv(
    "MFY_HTTP_USER_AGENT",
    "MFY-Estimator/1.0 (+contact: contact@mfy.local)"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    # Réduit les blocages sur certains CDNs
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

def download_binary(url: str, timeout: float = 20.0, retries: int = 2, backoff: float = 0.75) -> bytes:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
            else:
                raise last_exc

