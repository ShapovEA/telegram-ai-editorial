from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db.models import Channel, Post
from app.db.session import session_scope
from app.domain.enums import PostStatus


def post_link(channel: Channel | None, post: Post) -> str | None:
    if channel and channel.telegram_username and post.telegram_message_ids:
        return f"https://t.me/{channel.telegram_username.lstrip('@')}/{post.telegram_message_ids[0]}"
    return None


def post_embedding_text(title: str, key_idea: str, text: str) -> str:
    return f"{title}\n{key_idea}\n{text[:1500]}"


async def similar_posts(channel_id: int, vector: list[float], *, limit: int = 5, days: int | None = None, statuses: tuple[str, ...] = (PostStatus.published, PostStatus.scheduled, PostStatus.awaiting_approval)) -> list[dict[str, Any]]:
    async with session_scope() as s:
        channel = await s.get(Channel, channel_id)
        distance = Post.embedding.cosine_distance(vector)
        q = (
            select(Post, distance.label("distance"))
            .where(Post.channel_id == channel_id, Post.embedding.is_not(None), Post.status.in_(statuses))
            .order_by(distance)
            .limit(limit)
        )
        if days:
            q = q.where(Post.created_at >= datetime.now(UTC) - timedelta(days=days))
        rows = (await s.execute(q)).all()
    out = []
    for post, dist in rows:
        out.append(
            {
                "id": post.id,
                "title": post.title,
                "key_idea": post.key_idea,
                "excerpt": post.text[:400],
                "date": (post.published_at or post.publish_at or post.created_at).date().isoformat(),
                "url": post_link(channel, post),
                "similarity": round(1 - float(dist), 3),
                "rubric": post.rubric,
                "reactions": post.reactions_total,
            }
        )
    return out
