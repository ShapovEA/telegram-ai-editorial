import asyncio
import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from time import mktime
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Channel, ChannelSource, ChannelStory, FeedItem, Source, Story
from app.db.session import session_scope
from app.domain.enums import ChannelStatus, SourceStatus, StoryStatus
from app.domain.schemas import Brief
from app.runtime.redis import get_redis, owned_lock
from app.services.embeddings import EmbeddingError, cosine, embed, embed_one
from app.services.novelty import POST_SAME, STORY_GRAY, STORY_SAME, same_event
from app.services.posts_index import similar_posts
from app.tools import pages

log = logging.getLogger(__name__)

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml")
COMMON_PATHS = ["/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml", "/feeds/all.rss", "/rss/all"]
RELEVANCE_MIN = 0.33
MAX_NEW_PER_FETCH = 30
MAX_TEXT = 20000


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def title_hash(title: str) -> str:
    norm = re.sub(r"[^\w]+", " ", title.lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


async def _get(url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent": pages.USER_AGENT, **(headers or {})}) as client:
        return await client.get(url)


def _parse(content: bytes) -> Any:
    return feedparser.parse(content)


async def validate_feed(url: str) -> dict[str, Any]:
    try:
        resp = await _get(url)
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось открыть: {exc}"}
    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    parsed = await asyncio.to_thread(_parse, resp.content)
    if not parsed.entries:
        return {"ok": False, "error": "Это не RSS/Atom или лента пустая"}
    items = []
    for e in parsed.entries[:5]:
        items.append(
            {
                "title": e.get("title", ""),
                "url": e.get("link", ""),
                "published": _entry_date(e).isoformat() if _entry_date(e) else None,
                "full_text": len(_entry_content(e)) >= pages.MIN_TEXT,
            }
        )
    return {"ok": True, "url": str(resp.url), "title": parsed.feed.get("title", "") or urlparse(url).netloc, "site_url": parsed.feed.get("link"), "items": items}


async def article_text(url: str, feed_content: str = "") -> str:
    try:
        page = (await pages.read_page(url)).text
    except pages.PageError:
        page = ""
    best = max(page, feed_content, key=len)
    return best[:MAX_TEXT] if len(best) >= pages.MIN_TEXT else ""


async def full_text_available(items: list[dict]) -> bool:
    if any(it.get("full_text") for it in items):
        return True
    links = [it["url"] for it in items[:2] if it.get("url")]
    return any(await asyncio.gather(*[article_text(u) for u in links]))


async def discover(site: str) -> list[str]:
    if not site.startswith("http"):
        site = "https://" + site
    found: list[str] = []
    try:
        resp = await _get(site)
        html = resp.text
        for m in re.finditer(r"<link[^>]+>", html, re.IGNORECASE):
            tag = m.group(0)
            if "alternate" in tag.lower() and any(t in tag.lower() for t in FEED_TYPES):
                href = re.search(r'href=["\']([^"\']+)["\']', tag)
                if href:
                    found.append(urljoin(str(resp.url), href.group(1)))
    except Exception as exc:
        log.info("discover %s: %s", site, exc)
    if not found:
        for path in COMMON_PATHS:
            candidate = urljoin(site, path)
            check = await validate_feed(candidate)
            if check.get("ok"):
                found.append(check["url"])
                break
    return list(dict.fromkeys(found))


def _entry_date(e: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            try:
                return datetime.fromtimestamp(mktime(t), tz=UTC)
            except (OverflowError, ValueError):
                continue
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _entry_content(e: Any) -> str:
    return _strip_html(e["content"][0].get("value", "")) if e.get("content") else ""


async def _channel_vectors(channel_ids: list[int]) -> dict[int, list[float]]:
    out = {}
    redis = get_redis()
    async with session_scope() as s:
        channels = (await s.execute(select(Channel).where(Channel.id.in_(channel_ids)))).scalars().all()
    for ch in channels:
        brief = Brief.model_validate(ch.brief or {})
        text = brief.about
        key = "topicvec:" + hashlib.sha1(f"{ch.id}|{text}".encode()).hexdigest()
        try:
            cached = await redis.get(key)
        except Exception:
            cached = None
        if cached:
            out[ch.id] = [float(x) for x in cached.split(",")]
            continue
        try:
            vec = await embed_one(text)
        except EmbeddingError:
            continue
        out[ch.id] = vec
        try:
            await redis.set(key, ",".join(f"{x:.6f}" for x in vec), ex=7 * 24 * 3600)
        except Exception:
            pass
    return out


async def _assign_story(item: FeedItem, vector: list[float], session) -> tuple[Story, bool]:
    since = datetime.now(UTC) - timedelta(hours=48)
    distance = Story.embedding.cosine_distance(vector)
    rows = (await session.execute(select(Story, distance.label("d")).where(Story.last_item_at >= since, Story.embedding.is_not(None)).order_by(distance).limit(3))).all()
    for story, d in rows:
        sim = 1 - float(d)
        if sim >= STORY_SAME or (sim >= STORY_GRAY and await same_event(story.title, f"{item.title}\n{item.summary}")):
            story.item_count += 1
            story.last_item_at = max(story.last_item_at, item.published_at or datetime.now(UTC))
            return story, False
        if sim < STORY_GRAY:
            break
    story = Story(title=item.title, embedding=vector, last_item_at=item.published_at or datetime.now(UTC))
    session.add(story)
    await session.flush()
    return story, True


async def fetch_source(source_id: int) -> dict[str, Any]:
    key = f"feed:lock:{source_id}"
    async with owned_lock(key) as acquired:
        if acquired:
            return await _fetch_source(source_id)
    redis = get_redis()
    while await redis.exists(key):
        await asyncio.sleep(2)
    return {"new": 0}


async def _fetch_source(source_id: int) -> dict[str, Any]:
    async with session_scope() as s:
        src = await s.get(Source, source_id)
        if src is None:
            return {"error": "нет источника"}
        url, etag, modified = src.url, src.etag, src.modified
        channel_ids = (await s.execute(select(ChannelSource.channel_id).join(Channel, Channel.id == ChannelSource.channel_id).where(ChannelSource.source_id == source_id, Channel.status == ChannelStatus.active))).scalars().all()
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    now = datetime.now(UTC)
    try:
        resp = await _get(url, headers)
    except Exception as exc:
        async with session_scope() as s:
            src = await s.get(Source, source_id)
            src.status, src.error, src.last_fetched_at = SourceStatus.error, str(exc)[:500], now
        return {"error": str(exc)}
    if resp.status_code == 304:
        async with session_scope() as s:
            src = await s.get(Source, source_id)
            src.last_fetched_at = now
            src.last_success_at = now
            src.status = SourceStatus.ok
        return {"new": 0}
    if resp.status_code >= 400:
        async with session_scope() as s:
            src = await s.get(Source, source_id)
            src.status, src.error, src.last_fetched_at = SourceStatus.error, f"HTTP {resp.status_code}", now
        return {"error": f"HTTP {resp.status_code}"}
    parsed = await asyncio.to_thread(_parse, resp.content)
    entries = parsed.entries[:60]
    fresh_since = now - timedelta(days=3)
    candidates = []
    async with session_scope() as s:
        for e in entries:
            link = e.get("link")
            title = _strip_html(e.get("title", ""))
            if not link or not title:
                continue
            published = _entry_date(e)
            if published and published < fresh_since:
                continue
            uh = url_hash(link)
            exists = (await s.execute(select(FeedItem.id).where(FeedItem.url_hash == uh))).scalar_one_or_none()
            if exists:
                continue
            th = title_hash(title)
            dup_title = (await s.execute(select(FeedItem.id).where(FeedItem.title_hash == th, FeedItem.fetched_at >= fresh_since).limit(1))).scalar_one_or_none()
            if dup_title:
                continue
            content = _entry_content(e)
            summary = _strip_html(e.get("summary", "")) or content
            candidates.append({"url": link, "title": title, "summary": summary[:2000], "content": content, "published": published, "uh": uh, "th": th})
    candidates = candidates[:MAX_NEW_PER_FETCH]

    texts = await asyncio.gather(*[article_text(c["url"], c["content"]) for c in candidates])
    try:
        vectors = await embed([f"{c['title']}\n{(t or c['summary'])[:600]}" for c, t in zip(candidates, texts, strict=True)]) if candidates else []
    except EmbeddingError as exc:
        log.warning("embeddings unavailable, feed %s postponed: %s", url, exc)
        return {"error": str(exc)}
    channel_vecs = await _channel_vectors(list(channel_ids)) if channel_ids else {}
    created = 0
    async with session_scope() as s:
        for c, text, vec in zip(candidates, texts, vectors, strict=True):
            item = FeedItem(
                source_id=source_id,
                url=c["url"],
                url_hash=c["uh"],
                title_hash=c["th"],
                title=c["title"][:1000],
                summary=c["summary"],
                text=text,
                text_hash=hashlib.sha256(text.encode()).hexdigest() if text else None,
                published_at=c["published"] or now,
                embedding=vec,
            )
            s.add(item)
            await s.flush()
            story, is_new = await _assign_story(item, vec, s)
            item.story_id = story.id
            created += 1
            for ch_id in channel_ids:
                existing = (await s.execute(select(ChannelStory).where(ChannelStory.channel_id == ch_id, ChannelStory.story_id == story.id))).scalar_one_or_none()
                if existing:
                    continue
                relevance = cosine(vec, channel_vecs[ch_id]) if ch_id in channel_vecs else None
                cs = ChannelStory(channel_id=ch_id, story_id=story.id, relevance=relevance)
                if relevance is not None and relevance < RELEVANCE_MIN:
                    cs.status, cs.reason = StoryStatus.rejected, f"Вне тематики канала (близость {relevance:.2f})"
                else:
                    similar = await similar_posts(ch_id, vec, limit=1, days=30)
                    if similar and similar[0]["similarity"] >= POST_SAME:
                        cs.status = StoryStatus.rejected
                        cs.reason = f"Повтор поста от {similar[0]['date']} «{similar[0]['title']}»"
                        cs.related_post_id = similar[0]["id"]
                s.add(cs)
        src = await s.get(Source, source_id)
        src.status = SourceStatus.ok
        src.error = None
        src.etag = resp.headers.get("etag")
        src.modified = resp.headers.get("last-modified")
        src.last_fetched_at = now
        src.last_success_at = now
        src.items_total = (src.items_total or 0) + created
        if created:
            src.last_item_at = now
        if not src.title:
            src.title = parsed.feed.get("title", "")[:300]
    return {"new": created}


async def due_sources(interval_minutes: int = 10, channel_id: int | None = None) -> list[int]:
    threshold = datetime.now(UTC) - timedelta(minutes=interval_minutes)
    q = (
        select(Source.id)
        .join(ChannelSource, ChannelSource.source_id == Source.id)
        .join(Channel, Channel.id == ChannelSource.channel_id)
        .where(Channel.status == ChannelStatus.active)
        .where((Source.last_fetched_at.is_(None)) | (Source.last_fetched_at < threshold))
    )
    if channel_id is not None:
        q = q.where(ChannelSource.channel_id == channel_id)
    async with session_scope() as s:
        rows = (await s.execute(q.distinct())).scalars().all()
    return list(rows)


def rsshub_url(route: str) -> str | None:
    base = get_settings().rsshub_url
    if not base:
        return None
    return base.rstrip("/") + "/" + route.lstrip("/")
