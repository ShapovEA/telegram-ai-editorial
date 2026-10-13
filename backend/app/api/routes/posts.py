from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.api.serializers import post_out
from app.api.utils import kick
from app.db.models import Channel, LlmCall, Post, PostEdit, Run, Slot, User
from app.db.session import get_session
from app.domain.enums import AWAITING_DECISION, PostStatus, RunStatus, SlotStatus
from app.domain.schemas import ChannelOptions, Styleguide, channel_schedule
from app.graphs.post import render
from app.quality.checks import safe_html
from app.quality.detector import detect
from app.services.posts_index import post_link

router = APIRouter(tags=["posts"])


async def _post(session: AsyncSession, post_id: int, user: User) -> tuple[Post, Channel]:
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "Пост не найден")
    ch = await owned_channel(post.channel_id, user, session)
    return post, ch


async def _cost(session: AsyncSession, post_id: int) -> float:
    return float((await session.execute(select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.post_id == post_id))).scalar_one())


@router.get("/channels/{channel_id}/posts")
async def list_posts(channel_id: int, status: str | None = None, limit: int = 50, offset: int = 0, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    q = select(Post).where(Post.channel_id == ch.id)
    if status:
        q = q.where(Post.status.in_(status.split(",")))
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await session.execute(q.order_by(func.coalesce(Post.published_at, Post.publish_at, Post.created_at).desc()).offset(offset).limit(min(limit, 200)))).scalars().all()
    costs = dict(
        (await session.execute(select(LlmCall.post_id, func.sum(LlmCall.cost_usd)).where(LlmCall.post_id.in_([p.id for p in rows] or [-1])).group_by(LlmCall.post_id))).all()
    )
    return {"total": total, "items": [post_out(p, cost=float(costs.get(p.id) or 0), link=post_link(ch, p)) for p in rows]}


@router.get("/posts/{post_id}")
async def get_post(post_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, ch = await _post(session, post_id, user)
    rows = (
        await session.execute(
            select(LlmCall.role, func.count(), func.sum(LlmCall.cost_usd), func.sum(LlmCall.prompt_tokens), func.sum(LlmCall.completion_tokens), func.sum(LlmCall.latency_ms))
            .where(LlmCall.post_id == post.id)
            .group_by(LlmCall.role)
        )
    ).all()
    breakdown = [{"role": r, "calls": c, "cost": float(cost or 0), "prompt_tokens": int(pt or 0), "completion_tokens": int(ct or 0), "latency_ms": int(lat or 0)} for r, c, cost, pt, ct, lat in rows]
    run = await session.get(Run, post.run_id) if post.run_id else None
    options = ChannelOptions.model_validate(ch.options or {})
    revisions_left = None
    if run and run.status == RunStatus.waiting:
        from app.graphs.checkpointer import get_checkpointer

        tup = await (await get_checkpointer()).aget_tuple({"configurable": {"thread_id": run.id}})
        used = ((tup.checkpoint or {}).get("channel_values") or {}).get("owner_revisions", 0) if tup else 0
        revisions_left = max(0, options.max_owner_revisions - int(used or 0))
    stamps = [i.to_dict() for i in detect(post.text, title=post.title, fmt=post.format)] if post.format != "poll" else []
    return {
        **post_out(post, full=True, cost=sum(b["cost"] for b in breakdown), link=post_link(ch, post)),
        "cost_breakdown": breakdown,
        "run_status": run.status if run else None,
        "revisions_left": revisions_left,
        "quality": {"issues": stamps, "critical": sum(1 for i in stamps if i["critical"])},
        "channel": {"id": ch.id, "title": ch.title, "type": ch.type, "publish_mode": ch.publish_mode, "timezone": channel_schedule(ch.type, ch.schedule).timezone},
    }


async def _waiting_run(session: AsyncSession, post: Post) -> Run:
    run = await session.get(Run, post.run_id) if post.run_id else None
    if run is None or run.status != RunStatus.waiting or post.status not in AWAITING_DECISION:
        raise HTTPException(409, "Пост не ожидает решения")
    return run


@router.post("/posts/{post_id}/approve")
async def approve(post_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, _ = await _post(session, post_id, user)
    run = await _waiting_run(session, post)
    await kick(run.id, {"action": "approve"})
    return {"run_id": run.id}


class ReviseIn(BaseModel):
    comment: str = Field(min_length=3, max_length=3000)


@router.post("/posts/{post_id}/revise")
async def revise(post_id: int, body: ReviseIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, ch = await _post(session, post_id, user)
    run = await _waiting_run(session, post)
    from app.graphs.checkpointer import get_checkpointer

    tup = await (await get_checkpointer()).aget_tuple({"configurable": {"thread_id": run.id}})
    used = int((((tup.checkpoint or {}).get("channel_values") or {}).get("owner_revisions") or 0) if tup else 0)
    if used >= ChannelOptions.model_validate(ch.options or {}).max_owner_revisions:
        raise HTTPException(409, "Лимит доработок исчерпан: поправьте текст вручную")
    await kick(run.id, {"action": "revise", "comment": body.comment})
    return {"run_id": run.id}


@router.post("/posts/{post_id}/reject")
async def reject(post_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, _ = await _post(session, post_id, user)
    run = await session.get(Run, post.run_id) if post.run_id else None
    if run and run.status == RunStatus.waiting:
        await kick(run.id, {"action": "reject"})
        return {"run_id": run.id}
    if post.status in (PostStatus.scheduled, PostStatus.needs_attention, PostStatus.draft):
        post.status = PostStatus.rejected
        if post.slot_id:
            slot = await session.get(Slot, post.slot_id)
            if slot:
                slot.status = SlotStatus.skipped
        await session.commit()
        return {"ok": True}
    raise HTTPException(409, "Этот пост нельзя отклонить")


class EditIn(BaseModel):
    title: str = ""
    text: str = Field(min_length=10)


@router.put("/posts/{post_id}")
async def edit(post_id: int, body: EditIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, ch = await _post(session, post_id, user)
    if post.status not in (*AWAITING_DECISION, PostStatus.scheduled, PostStatus.draft):
        raise HTTPException(409, "Этот пост уже нельзя править")
    if post.format == "poll":
        raise HTTPException(400, "Опрос правится через доработку с комментарием")
    title, text = body.title.strip(), body.text.strip()
    if text != post.text.strip() or title != post.title.strip():
        session.add(PostEdit(post_id=post.id, channel_id=ch.id, before=f"{post.title}\n\n{post.text}", after=f"{title}\n\n{text}"))
        post.title, post.text = title, text
        post.body_html = render.compose_html(title, safe_html(text), Styleguide.model_validate(ch.styleguide or {}), post.source_url)
        post.content = {**(post.content or {}), "edited_by_owner": True}
    was_waiting = post.status in AWAITING_DECISION
    await session.commit()
    if was_waiting:
        run = await session.get(Run, post.run_id) if post.run_id else None
        if run and run.status == RunStatus.waiting:
            await kick(run.id, {"action": "edited"})
    return post_out(post, full=True)


class RateIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    comment: str = ""


@router.post("/posts/{post_id}/rate")
async def rate(post_id: int, body: RateIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, _ = await _post(session, post_id, user)
    post.rating = body.rating or None
    post.rating_comment = body.comment or None
    await session.commit()
    return {"ok": True}


@router.post("/posts/{post_id}/publish-now")
async def publish_now(post_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    post, _ = await _post(session, post_id, user)
    if post.status != PostStatus.scheduled:
        raise HTTPException(409, "Публиковать сейчас можно только запланированный пост")
    post.publish_at = datetime.now(UTC)
    await session.commit()
    from app.worker.tasks import publish_post

    await publish_post.kiq(post.id)
    return {"ok": True}
