import os, hashlib, mimetypes
from app.services.http_fetch import download_binary

def save_url_to_cache(url: str, cache_dir: str) -> str:
    data = download_binary(url)
    os.makedirs(cache_dir, exist_ok=True)
    # Déduire extension simple par URL ou fallback .jpg
    ext = ".jpg"
    for cand in (".png", ".webp", ".jpg", ".jpeg"):
        if cand in url.lower():
            ext = cand if cand != ".jpeg" else ".jpg"
            break
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ext
    path = os.path.join(cache_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path

