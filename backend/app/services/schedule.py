from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, Post, Slot
from app.domain.enums import AWAITING_DECISION, PostStatus, SlotStatus
from app.domain.schemas import NewsSchedule, SmmSchedule

PREFERRED_TIMES = ["09:00", "12:30", "18:30", "15:00", "20:00", "11:00", "19:30", "08:00", "21:00"]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def to_utc(local: datetime, tz_name: str) -> datetime:
    return local.replace(tzinfo=ZoneInfo(tz_name)).astimezone(UTC)


def rezone(dt: datetime, old_tz: str, new_tz: str) -> datetime:
    return to_utc(to_local(dt, old_tz), new_tz)


async def move_to_timezone(session: AsyncSession, channel_id: int, old_tz: str, new_tz: str) -> None:
    now = datetime.now(UTC)
    slots = (await session.execute(select(Slot).where(Slot.channel_id == channel_id, Slot.status != SlotStatus.published, Slot.publish_at > now))).scalars().all()
    posts = (
        await session.execute(select(Post).where(Post.channel_id == channel_id, Post.status.in_((PostStatus.draft, *AWAITING_DECISION, PostStatus.scheduled)), Post.publish_at > now))
    ).scalars().all()
    for row in [*slots, *posts]:
        row.publish_at = rezone(row.publish_at, old_tz, new_tz)
    for plan in (await session.execute(select(Plan).where(Plan.channel_id == channel_id, Plan.auto_approve_at > now))).scalars():
        plan.auto_approve_at = rezone(plan.auto_approve_at, old_tz, new_tz)


def week_start_for(d: date) -> date:
    return d - timedelta(days=d.weekday())


def next_week_start(today: date | None = None) -> date:
    today = today or datetime.now(UTC).date()
    return week_start_for(today) + timedelta(days=7)


def smm_grid(schedule: SmmSchedule, week_start: date, *, not_before: datetime | None = None) -> list[datetime]:
    days = sorted(set(schedule.days)) or [0, 1, 2, 3, 4]
    n = max(1, min(schedule.posts_per_week, 28))
    per_day = {d: 0 for d in days}
    for i in range(n):
        per_day[days[i % len(days)]] += 1
    windows = [(_t(w.start), _t(w.end)) for w in schedule.windows] or [(time(9), time(21))]
    allowed = [t for t in PREFERRED_TIMES if any(a <= _t(t) <= b for a, b in windows)]
    if not allowed:
        allowed = [windows[0][0].strftime("%H:%M")]
    out = []
    for d, count in per_day.items():
        day = week_start + timedelta(days=d)
        chosen = sorted(allowed[:count], key=_t) if count <= len(allowed) else sorted(allowed, key=_t)
        for t in chosen:
            utc = to_utc(datetime.combine(day, _t(t)), schedule.timezone)
            if not_before is None or utc > not_before:
                out.append(utc)
    return sorted(out)


def news_grid(schedule: NewsSchedule, start: datetime, hours: int = 48) -> list[datetime]:
    local_start = to_local(start, schedule.timezone)
    out = []
    for offset in range(0, hours // 24 + 2):
        day = (local_start + timedelta(days=offset)).date()
        if day.weekday() not in schedule.days:
            continue
        for t in schedule.times:
            utc = to_utc(datetime.combine(day, _t(t)), schedule.timezone)
            if start < utc <= start + timedelta(hours=hours):
                out.append(utc)
    return sorted(out)


def label(local: datetime) -> str:
    return f"{WEEKDAYS[local.weekday()]} {local.strftime('%d.%m %H:%M')}"
