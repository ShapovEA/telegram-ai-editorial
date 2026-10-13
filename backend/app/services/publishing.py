import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.db.models import Channel, ChannelStory, Idea, MediaFile, Post, Slot
from app.db.session import session_scope
from app.domain.enums import IdeaStatus, PostStatus, SlotStatus, StoryStatus
from app.runtime.events import notify_channel
from app.runtime.redis import get_redis
from app.services import notify, telegram

log = logging.getLogger(__name__)


async def due_posts() -> list[int]:
    async with session_scope() as s:
        return list((await s.execute(select(Post.id).where(Post.status == PostStatus.scheduled, Post.publish_at <= datetime.now(UTC)))).scalars().all())


async def publish_post(post_id: int) -> str:
    lock = f"publish:lock:{post_id}"
    redis = get_redis()
    if not await redis.set(lock, "1", nx=True, ex=300):
        return "locked"
    try:
        return await _publish(post_id)
    finally:
        await redis.delete(lock)


async def _publish(post_id: int) -> str:
    async with session_scope() as s:
        post = await s.get(Post, post_id)
        if post is None or post.status != PostStatus.scheduled:
            return "skip"
        channel = await s.get(Channel, post.channel_id)
        chat = channel.telegram_chat_id or (f"@{channel.telegram_username.lstrip('@')}" if channel.telegram_username else None)
        media_bytes = None
        if post.media.get("kind") == "chart" and post.media.get("media_id"):
            mf = await s.get(MediaFile, post.media["media_id"])
            media_bytes = mf.data if mf else None
        html = post.body_html or post.text
        fmt = post.format
        poll = (post.content or {}).get("poll") or {}
        media = dict(post.media or {})
    if not chat:
        await _fail(post_id, "Канал не подключён к Telegram")
        return "failed"
    message_ids: list[int] = []
    poll_id = None
    try:
        if fmt == "poll":
            if html.strip():
                m = await telegram.send_message(chat, html)
                message_ids.append(m["message_id"])
            m = await telegram.send_poll(chat, poll.get("question", ""), poll.get("options", []), multiple=bool(poll.get("multiple")))
            message_ids.append(m["message_id"])
            poll_id = (m.get("poll") or {}).get("id")
        elif media.get("kind") in ("chart", "stock") and (media_bytes or media.get("url")):
            if len(html) <= telegram.CAPTION_LIMIT:
                m = await telegram.send_photo(chat, url=media.get("url"), data=media_bytes, caption=html)
                message_ids.append(m["message_id"])
            else:
                m = await telegram.send_photo(chat, url=media.get("url"), data=media_bytes)
                message_ids.append(m["message_id"])
                m = await telegram.send_message(chat, html)
                message_ids.append(m["message_id"])
        else:
            m = await telegram.send_message(chat, html)
            message_ids.append(m["message_id"])
    except telegram.TelegramError as exc:
        if exc.retry_after and not exc.permanent:
            async with session_scope() as s:
                await s.execute(update(Post).where(Post.id == post_id).values(publish_at=datetime.now(UTC) + timedelta(seconds=exc.retry_after + 1)))
            return "retry"
        await _fail(post_id, str(exc))
        return "failed"
    now = datetime.now(UTC)
    async with session_scope() as s:
        post = await s.get(Post, post_id)
        post.status = PostStatus.published
        post.published_at = now
        post.telegram_message_ids = message_ids
        post.telegram_poll_id = poll_id
        if post.slot_id:
            slot = await s.get(Slot, post.slot_id)
            if slot:
                slot.status = SlotStatus.published
                if slot.story_id:
                    await s.execute(update(ChannelStory).where(ChannelStory.channel_id == post.channel_id, ChannelStory.story_id == slot.story_id).values(status=StoryStatus.published))
                if slot.idea_id:
                    await s.execute(update(Idea).where(Idea.id == slot.idea_id).values(status=IdeaStatus.used))
        brief = (post.content or {}).get("brief") or {}
        if brief.get("idea_id"):
            await s.execute(update(Idea).where(Idea.id == brief["idea_id"]).values(status=IdeaStatus.used))
        channel_id = post.channel_id
    await notify_channel(channel_id, {"type": "post_published", "post_id": post_id})
    return "published"


async def _fail(post_id: int, reason: str) -> None:
    async with session_scope() as s:
        post = await s.get(Post, post_id)
        post.status = PostStatus.failed
        if post.slot_id:
            slot = await s.get(Slot, post.slot_id)
            if slot:
                slot.status = SlotStatus.failed
                slot.warnings = [*(slot.warnings or []), {"code": "publish", "message": reason[:500]}]
        channel_id = post.channel_id
    await notify.notify_owner(channel_id, f"Не удалось опубликовать пост: {reason[:300]}")
