import requests
WIKI_SEARCH = "https://{lang}.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
def _wiki_search(title: str, lang: str = "fr"):
    params = {"action": "query","list": "search","srsearch": title,"format": "json","srlimit": 5}
    r = requests.get(WIKI_SEARCH.format(lang=lang), params=params, timeout=20); r.raise_for_status()
    data = r.json(); return [hit["pageid"] for hit in data.get("query", {}).get("search", [])]
def _wiki_pageimage(pageid: int, lang: str = "fr", size: int = 1024):
    params = {"action": "query","pageids": pageid,"prop": "pageimages","piprop": "thumbnail|name","pithumbsize": size,"format": "json"}
    r = requests.get(WIKI_SEARCH.format(lang=lang), params=params, timeout=20); r.raise_for_status()
    data = r.json(); pages = data.get("query", {}).get("pages", {}); page = pages.get(str(pageid), {})
    thumb = page.get("thumbnail", {}); return thumb.get("source")
def _commons_search(title: str, limit: int = 6, size: int = 1024):
    params = {"action": "query","generator": "search","gsrsearch": title,"gsrlimit": limit,"prop": "imageinfo","iiprop": "url","iiurlwidth": size,"format": "json"}
    r = requests.get(COMMONS_API, params=params, timeout=20); r.raise_for_status()
    data = r.json(); pages = data.get("query", {}).get("pages", {}); urls = []
    for _, p in pages.items():
        info = p.get("imageinfo", [])
        if info: urls.append(info[0].get("thumburl") or info[0].get("url"))
    return urls
def find_place_image_urls(name: str, lang: str = "fr", limit: int = 5):
    urls = []
    try:
        pageids = _wiki_search(name, lang=lang)
        for pid in pageids[:limit]:
            url = _wiki_pageimage(pid, lang=lang); 
            if url: urls.append(url)
    except Exception: pass
    if len(urls) < 2:
        try: urls.extend(_commons_search(name, limit=limit))
        except Exception: pass
    seen, out = set(), []
    for u in urls:
        if u and u not in seen: seen.add(u); out.append(u)
    return out[:limit]