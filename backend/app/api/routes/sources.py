import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.api.serializers import source_out, story_out
from app.api.utils import kick
from app.db.models import ChannelSource, ChannelStory, FeedItem, Source, Story, User
from app.db.session import get_session
from app.domain.enums import ChannelStatus, ChannelType, InjectionStatus, SourceStatus, StoryStatus
from app.security import injection
from app.services import feeds, jobs
from app.services.embeddings import EmbeddingError, embed_one
from app.tools import pages

router = APIRouter(tags=["sources"])


class UrlIn(BaseModel):
    url: str


@router.post("/sources/validate")
async def validate(body: UrlIn, user: User = Depends(current_user)) -> dict:
    return await feeds.validate_feed(body.url.strip())


@router.post("/sources/discover")
async def discover(body: UrlIn, user: User = Depends(current_user)) -> dict:
    found = await feeds.discover(body.url.strip())
    checks = [await feeds.validate_feed(u) for u in found[:5]]
    return {"feeds": [c for c in checks if c.get("ok")]}


@router.get("/channels/{channel_id}/sources")
async def list_sources(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    rows = (await session.execute(select(Source).join(ChannelSource, ChannelSource.source_id == Source.id).where(ChannelSource.channel_id == ch.id).order_by(Source.title))).scalars().all()
    out = []
    for src in rows:
        used = (
            await session.execute(
                select(func.count())
                .select_from(ChannelStory)
                .join(FeedItem, FeedItem.story_id == ChannelStory.story_id)
                .where(ChannelStory.channel_id == ch.id, ChannelStory.status == StoryStatus.published, FeedItem.source_id == src.id)
            )
        ).scalar_one()
        stale = src.last_item_at is None or (datetime.now(UTC) - src.last_item_at).days >= 7
        recent = (await session.execute(select(FeedItem.text != "").where(FeedItem.source_id == src.id).order_by(FeedItem.fetched_at.desc()).limit(20))).scalars().all()
        out.append({**source_out(src), "used_in_posts": used, "stale": stale and src.items_total > 0, "recent_items": len(recent), "recent_full_text": sum(recent)})
    return out


@router.post("/channels/{channel_id}/sources")
async def add_source(channel_id: int, body: UrlIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    check = await feeds.validate_feed(body.url.strip())
    if not check.get("ok"):
        raise HTTPException(400, check.get("error") or "Лента не прошла проверку")
    url = check["url"]
    src = (await session.execute(select(Source).where(Source.url == url))).scalar_one_or_none()
    if src is None:
        src = Source(url=url, title=check.get("title", "")[:300], site_url=check.get("site_url"), status=SourceStatus.new)
        session.add(src)
        await session.flush()
    link = await session.get(ChannelSource, (ch.id, src.id))
    if link is None:
        session.add(ChannelSource(channel_id=ch.id, source_id=src.id))
    await session.commit()
    return {**source_out(src), "preview": check.get("items", []), "full_text": await feeds.full_text_available(check.get("items", []))}


@router.delete("/channels/{channel_id}/sources/{source_id}")
async def remove_source(channel_id: int, source_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    link = await session.get(ChannelSource, (ch.id, source_id))
    if link:
        await session.delete(link)
        await session.commit()
    return {"ok": True}


@router.post("/channels/{channel_id}/sources/refresh")
async def refresh_sources(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    from app.worker.tasks import fetch_feed

    ch = await owned_channel(channel_id, user, session)
    ids = (await session.execute(select(ChannelSource.source_id).where(ChannelSource.channel_id == ch.id))).scalars().all()
    for sid in ids:
        await fetch_feed.kiq(sid)
    return {"queued": len(ids)}


@router.get("/channels/{channel_id}/stories")
async def list_stories(channel_id: int, status: str | None = None, limit: int = 100, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    q = select(ChannelStory, Story).join(Story, Story.id == ChannelStory.story_id).where(ChannelStory.channel_id == ch.id)
    if status:
        q = q.where(ChannelStory.status == status)
    rows = (await session.execute(q.order_by(Story.last_item_at.desc()).limit(min(limit, 300)))).all()
    out = []
    for cs, st in rows:
        items = (await session.execute(select(FeedItem).where(FeedItem.story_id == st.id).order_by(FeedItem.published_at.desc()).limit(6))).scalars().all()
        out.append(
            story_out(
                cs,
                st,
                [
                    {
                        "title": i.title,
                        "url": i.url,
                        "published_at": i.published_at.isoformat() if i.published_at else None,
                        "full_text": bool(i.text),
                        "injection": i.injection_status,
                        "injection_reason": i.injection_reason,
                    }
                    for i in items
                ],
            )
        )
    return out


class StoryPatch(BaseModel):
    priority: bool | None = None
    hidden: bool | None = None


@router.patch("/stories/{story_link_id}")
async def patch_story(story_link_id: int, body: StoryPatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    cs = await session.get(ChannelStory, story_link_id)
    if cs is None:
        raise HTTPException(404, "Сюжет не найден")
    await owned_channel(cs.channel_id, user, session)
    if body.priority is not None:
        cs.priority = body.priority
        if body.priority and cs.status in (StoryStatus.rejected, StoryStatus.hidden):
            cs.status, cs.reason = StoryStatus.new, None
    if body.hidden is not None:
        cs.status = StoryStatus.hidden if body.hidden else StoryStatus.new
        cs.reason = "Скрыт владельцем" if body.hidden else None
    await session.commit()
    return {"ok": True, "status": cs.status, "priority": cs.priority}


WRITABLE_STORY = {StoryStatus.new, StoryStatus.rejected, StoryStatus.expired, StoryStatus.hidden}


class WriteNowIn(BaseModel):
    story_ids: list[int] = Field(min_length=1, max_length=10)


@router.post("/channels/{channel_id}/stories/write-now")
async def write_now(channel_id: int, body: WriteNowIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    if ch.type != ChannelType.news or ch.status != ChannelStatus.active:
        raise HTTPException(409, "Писать по сюжетам можно только в запущенном новостном канале")
    statuses = dict((await session.execute(select(ChannelStory.story_id, ChannelStory.status).where(ChannelStory.channel_id == ch.id, ChannelStory.story_id.in_(body.story_ids)))).all())
    busy = [sid for sid in body.story_ids if statuses.get(sid) not in WRITABLE_STORY]
    if busy:
        raise HTTPException(409, f"Сюжеты уже в работе или опубликованы: {len(busy)}")
    run_ids = await jobs.write_stories_now(ch.id, body.story_ids)
    for run_id in run_ids:
        await kick(run_id)
    return {"run_ids": run_ids}


@router.post("/channels/{channel_id}/stories/manual")
async def manual_story(channel_id: int, body: UrlIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    try:
        page = await pages.read_page(body.url.strip())
    except pages.PageError as exc:
        raise HTTPException(400, f"Не удалось прочитать страницу: {exc}") from exc
    verdict = await injection.check(page.text[:8000], source=page.url)
    if verdict.injection:
        raise HTTPException(400, f"Страница отклонена: попытка prompt injection ({verdict.reason})")
    try:
        vector = await embed_one(f"{page.title}\n{page.text[:600]}")
    except EmbeddingError as exc:
        raise HTTPException(503, str(exc)) from exc
    manual_url = f"manual://channel/{ch.id}"
    src = (await session.execute(select(Source).where(Source.url == manual_url))).scalar_one_or_none()
    if src is None:
        src = Source(url=manual_url, title="Добавлено вручную", status=SourceStatus.ok)
        session.add(src)
        await session.flush()
    uh = feeds.url_hash(page.url)
    existing = (await session.execute(select(FeedItem).where(FeedItem.url_hash == uh))).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing and existing.story_id:
        story = await session.get(Story, existing.story_id)
    else:
        story = Story(title=page.title or page.url, embedding=vector, last_item_at=now)
        session.add(story)
        await session.flush()
        session.add(
            FeedItem(
                source_id=src.id,
                url=page.url,
                url_hash=uh,
                title_hash=feeds.title_hash(page.title or page.url),
                title=(page.title or page.url)[:1000],
                summary=page.text[:500],
                text=page.text[:20000],
                text_hash=hashlib.sha256(page.text.encode()).hexdigest(),
                published_at=now,
                embedding=vector,
                injection_status=InjectionStatus.clean,
                story_id=story.id,
            )
        )
    story.last_item_at = now
    cs = (await session.execute(select(ChannelStory).where(ChannelStory.channel_id == ch.id, ChannelStory.story_id == story.id))).scalar_one_or_none()
    if cs is None:
        cs = ChannelStory(channel_id=ch.id, story_id=story.id)
        session.add(cs)
    cs.status, cs.priority, cs.reason = StoryStatus.new, True, "Добавлен владельцем"
    await session.commit()
    return story_out(cs, story)
