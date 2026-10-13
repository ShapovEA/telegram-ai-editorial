from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.api.serializers import idea_out, plan_out, slot_out
from app.api.utils import kick, run_inline
from app.db.models import Idea, Plan, Run, Slot, User
from app.db.session import get_session
from app.domain.enums import ChannelStatus, ChannelType, IdeaStatus, RunKind, RunStatus, SlotStatus
from app.graphs.runner import create_run
from app.services import jobs
from app.services.schedule import week_start_for

router = APIRouter(tags=["planning"])

EDITABLE = {SlotStatus.draft, SlotStatus.approved, SlotStatus.needs_attention, SlotStatus.failed, SlotStatus.skipped, SlotStatus.not_approved, SlotStatus.deferred}


async def _slot(session: AsyncSession, slot_id: int, user: User) -> Slot:
    slot = await session.get(Slot, slot_id)
    if slot is None:
        raise HTTPException(404, "Слот не найден")
    await owned_channel(slot.channel_id, user, session)
    return slot


@router.get("/channels/{channel_id}/plans")
async def get_plan(channel_id: int, week: date | None = None, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    week = week_start_for(week or datetime.now(UTC).date())
    plan = (await session.execute(select(Plan).where(Plan.channel_id == ch.id, Plan.week_start == week))).scalar_one_or_none()
    start = datetime.combine(week, datetime.min.time(), tzinfo=UTC) - timedelta(hours=14)
    end = start + timedelta(days=7, hours=28)
    slots = (await session.execute(select(Slot).where(Slot.channel_id == ch.id, Slot.publish_at >= start, Slot.publish_at < end))).scalars().all()
    if plan is None:
        return {"id": None, "week_start": week.isoformat(), "status": "none", "slots": [slot_out(s) for s in sorted(slots, key=lambda x: x.publish_at)], "summary": "", "run_id": None}
    return plan_out(plan, list(slots))


class PlanCreate(BaseModel):
    week_start: date
    comment: str = ""


@router.post("/channels/{channel_id}/plans")
async def create_plan(channel_id: int, body: PlanCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    if ch.type != ChannelType.smm:
        raise HTTPException(400, "Контент-план есть только у SMM-канала")
    if ch.status != ChannelStatus.active:
        raise HTTPException(400, "Канал не активен")
    week = week_start_for(body.week_start)
    plan = (await session.execute(select(Plan).where(Plan.channel_id == ch.id, Plan.week_start == week))).scalar_one_or_none()
    if plan is None:
        plan = Plan(channel_id=ch.id, week_start=week, comment=body.comment)
        session.add(plan)
        await session.flush()
    elif plan.run_id:
        run = await session.get(Run, plan.run_id)
        if run and run.status in (RunStatus.running, RunStatus.queued):
            raise HTTPException(409, "План уже составляется")
    plan.comment = body.comment
    await session.commit()
    run_id = await create_run(RunKind.planning, ch.id, title=f"План на неделю с {week.strftime('%d.%m')}", input={"channel_id": ch.id, "plan_id": plan.id, "mode": "plan", "comment": body.comment}, plan_id=plan.id)
    plan.run_id = run_id
    await session.commit()
    await kick(run_id)
    return {"run_id": run_id, "plan_id": plan.id}


async def _plan_run(session: AsyncSession, plan_id: int, user: User) -> tuple[Plan, Run | None]:
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "План не найден")
    await owned_channel(plan.channel_id, user, session)
    run = await session.get(Run, plan.run_id) if plan.run_id else None
    return plan, run


@router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    plan, run = await _plan_run(session, plan_id, user)
    if run and run.status == RunStatus.waiting:
        await kick(run.id, {"action": "approve"})
        return {"run_id": run.id}
    for s in (await session.execute(select(Slot).where(Slot.plan_id == plan.id, Slot.status == SlotStatus.draft))).scalars():
        s.status = SlotStatus.approved
    plan.status, plan.approved_at = "approved", datetime.now(UTC)
    await session.commit()
    return {"ok": True}


class Replan(BaseModel):
    comment: str = ""


@router.post("/plans/{plan_id}/replan")
async def replan(plan_id: int, body: Replan, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    plan, run = await _plan_run(session, plan_id, user)
    plan.comment = body.comment
    await session.commit()
    if run and run.status == RunStatus.waiting:
        await kick(run.id, {"action": "replan", "comment": body.comment})
        return {"run_id": run.id}
    run_id = await create_run(RunKind.planning, plan.channel_id, title="Перепланирование недели", input={"channel_id": plan.channel_id, "plan_id": plan.id, "mode": "plan", "comment": body.comment}, plan_id=plan.id)
    plan.run_id = run_id
    await session.commit()
    await kick(run_id)
    return {"run_id": run_id}


class SlotCreate(BaseModel):
    channel_id: int
    publish_at: datetime
    rubric: str | None = None
    topic: str = ""
    reader_goal: str = ""
    key_idea: str = ""


@router.post("/slots")
async def create_slot(body: SlotCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(body.channel_id, user, session)
    plan = None
    if ch.type == ChannelType.smm:
        week = week_start_for(body.publish_at.date())
        plan = (await session.execute(select(Plan).where(Plan.channel_id == ch.id, Plan.week_start == week))).scalar_one_or_none()
        if plan is None:
            plan = Plan(channel_id=ch.id, week_start=week, status="draft")
            session.add(plan)
            await session.flush()
    fmt = "text"
    if ch.strategy and body.rubric:
        fmt = next((r.get("format", "text") for r in ch.strategy.get("rubrics", []) if r.get("name") == body.rubric), "text")
    slot = Slot(
        channel_id=ch.id,
        plan_id=plan.id if plan else None,
        publish_at=body.publish_at,
        rubric=body.rubric,
        format=fmt,
        topic=body.topic,
        reader_goal=body.reader_goal,
        key_idea=body.key_idea,
        status=SlotStatus.approved if (plan and plan.status == "approved") or ch.type == ChannelType.news else SlotStatus.draft,
        locked=bool(body.topic),
    )
    session.add(slot)
    await session.commit()
    return slot_out(slot)


class SlotPatch(BaseModel):
    publish_at: datetime | None = None
    rubric: str | None = None
    topic: str | None = None
    reader_goal: str | None = None
    key_idea: str | None = None
    locked: bool | None = None
    comment: str | None = None
    status: Literal["approved", "draft", "skipped"] | None = None


@router.patch("/slots/{slot_id}")
async def patch_slot(slot_id: int, body: SlotPatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    slot = await _slot(session, slot_id, user)
    data = body.model_dump(exclude_unset=True)
    if slot.status not in EDITABLE and set(data) - {"comment"}:
        raise HTTPException(409, "Слот уже в работе или опубликован")
    content_changed = any(k in data for k in ("topic", "reader_goal", "key_idea", "rubric"))
    for k, v in data.items():
        setattr(slot, k, v)
    if content_changed:
        slot.embedding = None
        slot.warnings = [w for w in slot.warnings or [] if w.get("code") not in ("plan", "development")]
        if slot.status in (SlotStatus.needs_attention, SlotStatus.failed):
            slot.status = SlotStatus.approved
            slot.run_id = None
    if body.publish_at is not None and slot.status in (SlotStatus.failed, SlotStatus.skipped, SlotStatus.not_approved, SlotStatus.deferred):
        slot.status, slot.run_id = SlotStatus.approved, None
    await session.commit()
    if content_changed and slot.topic:
        from app.services.novelty import classify_topic

        try:
            verdict = await classify_topic(slot.channel_id, slot.topic)
            if verdict["verdict"] == "same":
                p = verdict["post"]
                slot.warnings = [*(slot.warnings or []), {"code": "plan", "message": f"Повтор поста от {p['date']} «{p['title']}»"}]
                await session.commit()
        except Exception:
            pass
    return slot_out(slot)


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    slot = await _slot(session, slot_id, user)
    if slot.status not in EDITABLE:
        raise HTTPException(409, "Слот уже в работе или опубликован")
    await session.delete(slot)
    await session.commit()
    return {"ok": True}


class Suggest(BaseModel):
    hint: str = ""
    rubric: str | None = None
    count: int = Field(default=4, ge=1, le=6)


@router.post("/slots/{slot_id}/replace")
async def replace_topic(slot_id: int, body: Suggest, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    slot = await _slot(session, slot_id, user)
    if slot.status not in EDITABLE:
        raise HTTPException(409, "Слот уже в работе или опубликован")
    run_id = await create_run(RunKind.planning, slot.channel_id, title="Замена темы", input={"channel_id": slot.channel_id, "mode": "replace_slot", "slot_id": slot.id, "hint": body.hint})
    run = await run_inline(run_id)
    if run.status != RunStatus.done:
        raise HTTPException(502, run.error or "Не удалось заменить тему")
    await session.refresh(slot)
    return slot_out(slot)


@router.post("/channels/{channel_id}/topics/suggest")
async def suggest(channel_id: int, body: Suggest, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    run_id = await create_run(RunKind.planning, ch.id, title="Варианты тем", input={"channel_id": ch.id, "mode": "suggest_topics", "hint": body.hint, "rubric": body.rubric or "", "count": body.count})
    run = await run_inline(run_id)
    if run.status != RunStatus.done:
        raise HTTPException(502, run.error or "Не удалось предложить темы")
    return (run.result or {}).get("result") or {"topics": []}


@router.post("/slots/{slot_id}/start")
async def start_slot(slot_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    slot = await _slot(session, slot_id, user)
    if slot.status not in EDITABLE:
        raise HTTPException(409, "Слот уже в работе или опубликован")
    if slot.status == SlotStatus.draft:
        slot.status = SlotStatus.approved
    slot.run_id = None
    await session.commit()
    run_id = await jobs.start_slot_now(slot.id)
    await kick(run_id)
    return {"run_id": run_id}


@router.get("/channels/{channel_id}/slots")
async def list_slots(channel_id: int, start: datetime, end: datetime, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    rows = (await session.execute(select(Slot).where(Slot.channel_id == ch.id, Slot.publish_at >= start, Slot.publish_at < end).order_by(Slot.publish_at))).scalars().all()
    return [slot_out(s) for s in rows]


@router.get("/channels/{channel_id}/ideas")
async def list_ideas(channel_id: int, status: str | None = None, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    q = select(Idea).where(Idea.channel_id == ch.id)
    if status:
        q = q.where(Idea.status == status)
    rows = (await session.execute(q.order_by(Idea.status, Idea.vote.desc(), Idea.created_at.desc()).limit(300))).scalars().all()
    return [idea_out(i) for i in rows]


class IdeaIn(BaseModel):
    topic: str = Field(min_length=3)
    rubric: str | None = None
    reader_goal: str = ""
    note: str = ""


@router.post("/channels/{channel_id}/ideas")
async def add_idea(channel_id: int, body: IdeaIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    idea = Idea(channel_id=ch.id, topic=body.topic, rubric=body.rubric, reader_goal=body.reader_goal, note=body.note, origin="user", vote=1)
    session.add(idea)
    await session.commit()
    return idea_out(idea)


class IdeaPatch(BaseModel):
    vote: int | None = Field(default=None, ge=-1, le=1)
    status: Literal["new", "rejected"] | None = None
    topic: str | None = None


@router.patch("/ideas/{idea_id}")
async def patch_idea(idea_id: int, body: IdeaPatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise HTTPException(404, "Идея не найдена")
    await owned_channel(idea.channel_id, user, session)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(idea, k, v)
    await session.commit()
    return idea_out(idea)


@router.delete("/ideas/{idea_id}")
async def delete_idea(idea_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise HTTPException(404, "Идея не найдена")
    await owned_channel(idea.channel_id, user, session)
    await session.delete(idea)
    await session.commit()
    return {"ok": True}


@router.post("/channels/{channel_id}/ideas/generate")
async def generate_ideas(channel_id: int, body: Suggest, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    run_id = await create_run(RunKind.planning, ch.id, title="Новые идеи", input={"channel_id": ch.id, "mode": "suggest_topics", "hint": body.hint, "rubric": body.rubric or "", "count": max(body.count, 4)})
    run = await run_inline(run_id)
    if run.status != RunStatus.done:
        raise HTTPException(502, run.error or "Не удалось придумать идеи")
    topics = ((run.result or {}).get("result") or {}).get("topics", [])
    created = []
    for t in topics:
        if t.get("novelty") == "same":
            continue
        idea = Idea(channel_id=ch.id, topic=t["topic"], rubric=t.get("rubric") or None, reader_goal=t.get("reader_goal", ""), note=t.get("key_idea", ""), origin="strategy", status=IdeaStatus.new)
        session.add(idea)
        created.append(idea)
    await session.commit()
    return [idea_out(i) for i in created]
