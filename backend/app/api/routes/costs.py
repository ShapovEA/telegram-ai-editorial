from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.db.models import Channel, LlmCall, ModelInfo, Post, Run, User
from app.db.session import get_session
from app.domain.enums import PostStatus
from app.graphs.runner import role_models_for
from app.llm import catalog

router = APIRouter(tags=["costs"])

ROLE_TITLES = {
    "scout": "Скаут",
    "chief": "Шеф-редактор",
    "factchecker": "Фактчекер",
    "researcher": "Расследователь",
    "writer": "Писатель",
    "editor": "Редактор",
    "publisher": "Издатель",
    "guard": "Проверка на инъекции",
    "novelty": "Проверка новизны",
    "strategist": "Стратег",
    "account_manager": "Аккаунт-менеджер",
    "designer": "Оформитель",
    "analyst": "Аналитик",
}


def _period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/channels/{channel_id}/costs")
async def channel_costs(channel_id: int, period: Literal["day", "week", "month"] = "month", user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    start = _period_start(period)
    base = select(LlmCall).where(LlmCall.channel_id == ch.id, LlmCall.created_at >= start).subquery()
    total = (await session.execute(select(func.coalesce(func.sum(base.c.cost_usd), 0), func.count(), func.coalesce(func.sum(base.c.prompt_tokens), 0), func.coalesce(func.sum(base.c.completion_tokens), 0)))).one()
    by_role = (await session.execute(select(base.c.role, func.sum(base.c.cost_usd), func.count()).group_by(base.c.role).order_by(func.sum(base.c.cost_usd).desc()))).all()
    by_kind = (
        await session.execute(
            select(Run.kind, func.sum(LlmCall.cost_usd)).join(Run, Run.id == LlmCall.run_id).where(LlmCall.channel_id == ch.id, LlmCall.created_at >= start).group_by(Run.kind)
        )
    ).all()
    overhead = (await session.execute(select(func.coalesce(func.sum(base.c.cost_usd), 0)).where(base.c.post_id.is_(None)))).scalar_one()
    posts_cost = (
        await session.execute(
            select(func.count(distinct(LlmCall.post_id)), func.coalesce(func.sum(LlmCall.cost_usd), 0))
            .join(Post, Post.id == LlmCall.post_id)
            .where(LlmCall.channel_id == ch.id, LlmCall.created_at >= start, Post.status == PostStatus.published)
        )
    ).one()
    day = cast(LlmCall.created_at, Date)
    series = (
        await session.execute(
            select(day, LlmCall.role, func.sum(LlmCall.cost_usd))
            .where(LlmCall.channel_id == ch.id, LlmCall.created_at >= datetime.now(UTC) - timedelta(days=30))
            .group_by(day, LlmCall.role)
            .order_by(day)
        )
    ).all()
    budget = float(ch.budget_month_usd) if ch.budget_month_usd else None
    month_spent = float((await session.execute(select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.channel_id == ch.id, LlmCall.created_at >= _period_start("month")))).scalar_one())
    return {
        "period": period,
        "total": float(total[0]),
        "calls": total[1],
        "prompt_tokens": int(total[2]),
        "completion_tokens": int(total[3]),
        "overhead": float(overhead),
        "published_posts": posts_cost[0],
        "avg_post_cost": float(posts_cost[1]) / posts_cost[0] if posts_cost[0] else None,
        "by_role": [{"role": r, "title": ROLE_TITLES.get(r, r), "cost": float(c or 0), "calls": n} for r, c, n in by_role],
        "by_kind": [{"kind": k, "cost": float(c or 0)} for k, c in by_kind],
        "series": [{"date": d.isoformat(), "role": r, "cost": float(c or 0)} for d, r, c in series],
        "budget": budget,
        "month_spent": month_spent,
    }


@router.get("/costs/summary")
async def costs_summary(period: Literal["day", "week", "month"] = "month", user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    start = _period_start(period)
    rows = (
        await session.execute(
            select(Channel.id, Channel.title, func.coalesce(func.sum(LlmCall.cost_usd), 0))
            .join(LlmCall, LlmCall.channel_id == Channel.id, isouter=True)
            .where(Channel.owner_id == user.id)
            .where((LlmCall.created_at >= start) | (LlmCall.id.is_(None)))
            .group_by(Channel.id, Channel.title)
        )
    ).all()
    return {"period": period, "channels": [{"id": i, "title": t, "cost": float(c)} for i, t, c in rows], "total": float(sum(c for _, _, c in rows))}


def _model_out(m: ModelInfo | dict) -> dict:
    d = m if isinstance(m, dict) else {"id": m.id, "name": m.name, "context_length": m.context_length, "prompt_price": float(m.prompt_price), "completion_price": float(m.completion_price), "supports_tools": m.supports_tools, "reasoning": m.reasoning}
    r = d.get("reasoning") or {}
    return {
        "id": d["id"],
        "name": d["name"],
        "context_length": d["context_length"],
        "input_per_million": round(d["prompt_price"] * 1e6, 4),
        "output_per_million": round(d["completion_price"] * 1e6, 4),
        "supports_tools": d["supports_tools"],
        "reasoning": bool(r),
        "reasoning_mandatory": bool(r.get("mandatory")),
        "reasoning_efforts": r.get("supported_efforts") or [],
    }


@router.get("/models")
async def list_models(q: str = "", tools_only: bool = True, limit: int = 60, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    query = select(ModelInfo).where(~ModelInfo.id.endswith(":batch"))
    if tools_only:
        query = query.where(ModelInfo.supports_tools.is_(True))
    if q:
        query = query.where(ModelInfo.id.ilike(f"%{q}%") | ModelInfo.name.ilike(f"%{q}%"))
    rows = (await session.execute(query.order_by(ModelInfo.id).limit(min(limit, 500)))).scalars().all()
    synced = (await session.execute(select(func.max(ModelInfo.updated_at)))).scalar_one()
    return {"items": [_model_out(m) for m in rows], "synced_at": synced.isoformat() if synced else None}


@router.post("/models/sync")
async def sync_models(user: User = Depends(current_user)) -> dict:
    return {"synced": await catalog.sync_catalog()}


@router.get("/channels/{channel_id}/models")
async def channel_models(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    models = await role_models_for(ch)
    cat = await catalog.get_catalog()
    roles = []
    for role, rm in models.items():
        info = cat.get(rm.model)
        roles.append(
            {
                "role": role,
                "title": ROLE_TITLES.get(role, role),
                "config": rm.model_dump(),
                "overridden": role in (ch.models or {}),
                "model": _model_out(info) if info else None,
                "missing": info is None,
            }
        )
    order = list(ROLE_TITLES)
    roles.sort(key=lambda r: order.index(r["role"]) if r["role"] in order else 99)
    return {"roles": roles}
