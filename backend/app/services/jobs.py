import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.db.models import Channel, ChannelStory, Plan, Post, PostEdit, Run, Slot, Story
from app.db.session import session_scope
from app.domain.enums import (
    AWAITING_DECISION,
    ChannelStatus,
    ChannelType,
    PostStatus,
    PublishMode,
    RunKind,
    RunStatus,
    SlotStatus,
    StoryStatus,
)
from app.domain.schemas import ChannelOptions, NewsSchedule, SmmSchedule, channel_schedule
from app.graphs.runner import create_run
from app.services.schedule import label, news_grid, next_week_start, smm_grid, to_local, week_start_for

log = logging.getLogger(__name__)

MISSED_AFTER = timedelta(minutes=30)


async def ensure_news_slots() -> int:
    now = datetime.now(UTC)
    created = 0
    async with session_scope() as s:
        channels = (await s.execute(select(Channel).where(Channel.type == ChannelType.news, Channel.status == ChannelStatus.active))).scalars().all()
        for ch in channels:
            sched = NewsSchedule.model_validate(ch.schedule or {})
            times = news_grid(sched, now, hours=36)
            existing = set(
                (await s.execute(select(Slot.publish_at).where(Slot.channel_id == ch.id, Slot.publish_at >= now))).scalars().all()
            )
            for t in times:
                if t in existing:
                    continue
                s.add(Slot(channel_id=ch.id, publish_at=t, format="text", status=SlotStatus.approved, topic=""))
                created += 1
    return created


async def ensure_plans() -> list[str]:
    now = datetime.now(UTC)
    today = now.date()
    run_ids = []
    async with session_scope() as s:
        channels = (await s.execute(select(Channel).where(Channel.type == ChannelType.smm, Channel.status == ChannelStatus.active))).scalars().all()
        targets = []
        for ch in channels:
            sched = SmmSchedule.model_validate(ch.schedule or {})
            current = week_start_for(today)
            weeks = []
            has_current = (await s.execute(select(Plan.id).where(Plan.channel_id == ch.id, Plan.week_start == current))).scalar_one_or_none()
            if not has_current and smm_grid(sched, current, not_before=now + timedelta(hours=6)):
                weeks.append(current)
            nxt = next_week_start(today)
            if (nxt - today).days <= 2:
                has_next = (await s.execute(select(Plan.id).where(Plan.channel_id == ch.id, Plan.week_start == nxt))).scalar_one_or_none()
                if not has_next:
                    weeks.append(nxt)
            for w in weeks:
                plan = Plan(channel_id=ch.id, week_start=w, status="draft")
                s.add(plan)
                await s.flush()
                targets.append((ch.id, plan.id, w))
    for ch_id, plan_id, w in targets:
        run_id = await create_run(RunKind.planning, ch_id, title=f"План на неделю с {w.strftime('%d.%m')}", input={"channel_id": ch_id, "plan_id": plan_id, "mode": "plan"}, plan_id=plan_id)
        async with session_scope() as s:
            plan = await s.get(Plan, plan_id)
            plan.run_id = run_id
        run_ids.append(run_id)
    return run_ids


def production_lead(ch: Channel) -> timedelta:
    opts = ChannelOptions.model_validate(ch.options or {})
    if ch.type == ChannelType.news:
        return timedelta(minutes=opts.news_lead_minutes + (opts.news_approval_window_minutes if ch.publish_mode == PublishMode.approval else 0))
    return timedelta(hours=opts.smm_approval_lead_hours if ch.publish_mode == PublishMode.approval else opts.smm_autopilot_lead_hours)


async def write_stories_now(channel_id: int, story_ids: list[int]) -> list[str]:
    async with session_scope() as s:
        ch = await s.get(Channel, channel_id)
        publish_at = datetime.now(UTC) + production_lead(ch)
        rows = (
            await s.execute(select(ChannelStory, Story).join(Story, Story.id == ChannelStory.story_id).where(ChannelStory.channel_id == channel_id, ChannelStory.story_id.in_(story_ids)))
        ).all()
        slots = []
        for cs, story in rows:
            cs.status, cs.priority, cs.reason = StoryStatus.in_work, True, "Взят владельцем в работу"
            slot = Slot(channel_id=channel_id, publish_at=publish_at, format="text", status=SlotStatus.in_production, topic=story.title, story_id=story.id)
            s.add(slot)
            slots.append(slot)
        await s.flush()
        planned = [(channel_id, slot.id, slot.topic) for slot in slots]
    return await _start_post_runs(planned)


async def _start_post_runs(planned: list[tuple[int, int, str]]) -> list[str]:
    run_ids = []
    for ch_id, slot_id, title in planned:
        run_id = await create_run(RunKind.post, ch_id, title=title, input={"channel_id": ch_id, "slot_id": slot_id}, slot_id=slot_id)
        async with session_scope() as s:
            (await s.get(Slot, slot_id)).run_id = run_id
        run_ids.append(run_id)
    return run_ids


async def start_due_slots() -> list[str]:
    now = datetime.now(UTC)
    to_start: list[tuple[int, int, str]] = []
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Slot, Channel)
                .join(Channel, Channel.id == Slot.channel_id)
                .where(Channel.status == ChannelStatus.active, Slot.status == SlotStatus.approved, Slot.run_id.is_(None))
                .order_by(Slot.publish_at)
            )
        ).all()
        for slot, ch in rows:
            if slot.publish_at <= now - MISSED_AFTER:
                slot.status = SlotStatus.skipped
                slot.warnings = [*(slot.warnings or []), {"code": "missed", "message": "Время выхода прошло раньше, чем пост взяли в работу"}]
            elif slot.publish_at - production_lead(ch) <= now:
                slot.status = SlotStatus.in_production
                title = slot.topic or f"Пост на {label(to_local(slot.publish_at, channel_schedule(ch.type, ch.schedule).timezone))}"
                to_start.append((ch.id, slot.id, title))
    return await _start_post_runs(to_start)


async def start_slot_now(slot_id: int) -> str:
    async with session_scope() as s:
        slot = await s.get(Slot, slot_id)
        if slot is None:
            raise ValueError("Слот не найден")
        if slot.status in (SlotStatus.in_production,) and slot.run_id:
            return slot.run_id
        slot.status = SlotStatus.in_production
        planned = (slot.channel_id, slot_id, slot.topic or "Пост")
    return (await _start_post_runs([planned]))[0]


async def plans_to_auto_approve() -> list[str]:
    now = datetime.now(UTC)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Plan.run_id).join(Run, Run.id == Plan.run_id).where(Plan.status == "draft", Plan.auto_approve_at <= now, Run.status == RunStatus.waiting)
            )
        ).scalars().all()
    return [r for r in rows if r]


async def approvals_to_expire() -> list[str]:
    now = datetime.now(UTC)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Post.run_id)
                .join(Run, Run.id == Post.run_id)
                .where(Post.status.in_(AWAITING_DECISION), Post.publish_at <= now, Run.status == RunStatus.waiting)
            )
        ).scalars().all()
    return [r for r in rows if r]


async def _requeue(s, run: Run) -> None:
    run.status, run.error, run.next_attempt_at, run.started_at, run.finished_at = RunStatus.queued, None, None, None, None
    if run.kind != RunKind.post or not run.slot_id:
        return
    slot = await s.get(Slot, run.slot_id)
    slot.status = SlotStatus.in_production
    if slot.story_id:
        await s.execute(
            update(ChannelStory)
            .where(ChannelStory.channel_id == slot.channel_id, ChannelStory.story_id == slot.story_id, ChannelStory.status == StoryStatus.new)
            .values(status=StoryStatus.in_work, reason=None)
        )


async def retry_run(run_id: str) -> None:
    async with session_scope() as s:
        await _requeue(s, await s.get(Run, run_id))


async def deferred_runs() -> list[str]:
    now = datetime.now(UTC)
    async with session_scope() as s:
        rows = (await s.execute(select(Run.id).where(Run.status == RunStatus.deferred, Run.next_attempt_at <= now))).scalars().all()
        for rid in rows:
            await _requeue(s, await s.get(Run, rid))
    return list(rows)


async def stale_queued_runs() -> list[str]:
    threshold = datetime.now(UTC) - timedelta(minutes=10)
    async with session_scope() as s:
        return list((await s.execute(select(Run.id).where(Run.status == RunStatus.queued, Run.created_at < threshold))).scalars().all())


async def channels_for_rules(min_edits: int = 3) -> list[str]:
    run_ids = []
    async with session_scope() as s:
        rows = (await s.execute(select(PostEdit.channel_id, func.count()).where(PostEdit.processed.is_(False)).group_by(PostEdit.channel_id))).all()
    for ch_id, cnt in rows:
        if cnt >= min_edits:
            run_ids.append(await create_run(RunKind.channel_rules, ch_id, title="Правила канала из правок владельца", input={"channel_id": ch_id}))
    return run_ids


async def channels_for_analytics() -> list[str]:
    since = datetime.now(UTC) - timedelta(days=30)
    run_ids = []
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Post.channel_id, func.count())
                .join(Channel, Channel.id == Post.channel_id)
                .where(Channel.type == ChannelType.smm, Channel.status == ChannelStatus.active, Post.status == PostStatus.published, Post.published_at >= since)
                .group_by(Post.channel_id)
            )
        ).all()
    for ch_id, cnt in rows:
        if cnt >= 3:
            run_ids.append(await create_run(RunKind.analytics, ch_id, title="Отчёт за месяц", input={"channel_id": ch_id, "days": 30}))
    return run_ids
