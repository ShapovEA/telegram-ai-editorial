from datetime import date
from typing import Any

from sqlalchemy import select

from app.db.models import Channel, Post
from app.db.session import session_scope
from app.domain.enums import PostStatus
from app.domain.schemas import ChannelOptions
from app.services.service_settings import get_service_config


async def build_ctx(channel_id: int) -> dict[str, Any]:
    cfg = await get_service_config()
    async with session_scope() as s:
        ch = await s.get(Channel, channel_id)
        if ch is None:
            raise ValueError(f"Канал {channel_id} не найден")
        recent = (
            await s.execute(
                select(Post)
                .where(Post.channel_id == channel_id, Post.status.in_([PostStatus.published, PostStatus.scheduled, PostStatus.awaiting_approval]))
                .order_by(Post.created_at.desc())
                .limit(25)
            )
        ).scalars().all()
    options = ChannelOptions.model_validate(ch.options or {})
    voice = [
        {"title": p.title, "text": p.text}
        for p in recent
        if p.status == PostStatus.published and not p.synthetic and p.writer_text and p.writer_text.strip() == p.text.strip() and (p.rating or 0) >= 0
    ][:3]
    reference = [{"title": "", "text": t} for t in (ch.options or {}).get("sample_posts", [])[: max(0, 4 - len(voice))]]
    return {
        "channel_id": ch.id,
        "title": ch.title,
        "type": ch.type,
        "publish_mode": ch.publish_mode,
        "telegram_username": ch.telegram_username,
        "brief": ch.brief or {},
        "styleguide": ch.styleguide or {},
        "strategy": ch.strategy or {},
        "options": options.model_dump(),
        "today": date.today().isoformat(),
        "voice_examples": voice + reference,
        "recent_posts": [
            {"id": p.id, "title": p.title, "date": (p.published_at or p.publish_at or p.created_at).date().isoformat(), "rubric": p.rubric, "reactions": p.reactions_total}
            for p in recent
        ],
        "extra_stamps": cfg.extra_stamps,
        "latin_whitelist": cfg.latin_whitelist,
    }
