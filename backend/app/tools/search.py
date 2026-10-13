import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.runtime.redis import get_redis

log = logging.getLogger(__name__)


class SearchUnavailable(Exception):
    pass


async def _throttle(engine: str) -> None:
    s = get_settings()
    redis = get_redis()
    key = f"search:throttle:{engine}"
    for _ in range(40):
        try:
            ok = await redis.set(key, "1", nx=True, px=int(s.search_min_interval_seconds * 1000))
        except Exception:
            return
        if ok:
            return
        await asyncio.sleep(0.25)


async def _cache_get(key: str) -> list[dict[str, Any]] | None:
    try:
        raw = await get_redis().get(key)
    except Exception:
        return None
    return json.loads(raw) if raw else None


async def _cache_set(key: str, value: list[dict[str, Any]]) -> None:
    try:
        await get_redis().set(key, json.dumps(value, ensure_ascii=False), ex=get_settings().search_cache_ttl_seconds)
    except Exception:
        pass


async def searxng(query: str, *, category: str = "general", limit: int = 8, time_range: str | None = None) -> list[dict[str, Any]]:
    s = get_settings()
    if not s.searxng_url:
        raise SearchUnavailable("SearXNG не настроен")
    await _throttle("searxng")
    params = {"q": query, "format": "json", "language": "ru", "categories": category, "safesearch": 1}
    if time_range:
        params["time_range"] = time_range
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{s.searxng_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise SearchUnavailable(f"SearXNG: {exc}") from exc
    out = []
    for r in data.get("results", [])[:limit]:
        if not r.get("url"):
            continue
        out.append(
            {
                "title": (r.get("title") or "")[:300],
                "url": r["url"],
                "snippet": (r.get("content") or "")[:500],
                "date": r.get("publishedDate"),
                "engine": "searxng:" + ",".join(r.get("engines") or []),
            }
        )
    return out


async def duckduckgo(query: str, *, category: str = "general", limit: int = 8) -> list[dict[str, Any]]:
    await _throttle("ddg")

    def run() -> list[dict[str, Any]]:
        from ddgs import DDGS

        with DDGS() as d:
            if category == "news":
                rows = d.news(query, region="ru-ru", max_results=limit)
                return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("body", ""), "date": r.get("date"), "engine": "duckduckgo"} for r in rows]
            rows = d.text(query, region="ru-ru", max_results=limit)
            return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", ""), "date": None, "engine": "duckduckgo"} for r in rows]

    try:
        return [r for r in await asyncio.to_thread(run) if r["url"]]
    except Exception as exc:
        raise SearchUnavailable(f"DuckDuckGo: {exc}") from exc


async def wikipedia(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    await _throttle("wiki")
    params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": limit, "utf8": 1}
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "ai-smm-department/1.0"}) as client:
            resp = await client.get("https://ru.wikipedia.org/w/api.php", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise SearchUnavailable(f"Wikipedia: {exc}") from exc
    out = []
    for r in data.get("query", {}).get("search", []):
        title = r.get("title", "")
        snippet = r.get("snippet", "").replace('<span class="searchmatch">', "").replace("</span>", "")
        out.append({"title": title, "url": f"https://ru.wikipedia.org/wiki/{title.replace(' ', '_')}", "snippet": snippet, "date": None, "engine": "wikipedia"})
    return out


async def web_search(query: str, *, category: str = "general", limit: int = 8, time_range: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    key = "search:" + hashlib.sha1(f"{category}|{time_range}|{limit}|{query.strip().lower()}".encode()).hexdigest()
    cached = await _cache_get(key)
    if cached is not None:
        return cached, ["cache"]
    errors: list[str] = []
    chain = [
        lambda: searxng(query, category=category, limit=limit, time_range=time_range),
        lambda: duckduckgo(query, category=category, limit=limit),
    ]
    if category == "general":
        chain.append(lambda: wikipedia(query, limit=min(limit, 5)))
    for attempt in chain:
        try:
            results = await attempt()
        except SearchUnavailable as exc:
            errors.append(str(exc))
            continue
        if results:
            await _cache_set(key, results)
            return results, errors
        errors.append("пустой результат")
    return [], errors
