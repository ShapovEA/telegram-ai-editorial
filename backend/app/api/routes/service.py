import contextlib
import random
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import Date, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.api.serializers import report_out
from app.api.utils import kick
from app.config import get_settings
from app.db.models import AnalyticsReport, LlmCall, MediaFile, Post, Run, User
from app.db.session import get_session
from app.domain.enums import ChannelType, PostStatus, RunKind, RunStatus
from app.domain.schemas import RoleModel, Strategy
from app.graphs.runner import create_run
from app.observability import tracing
from app.services import telegram
from app.services.service_settings import ServiceConfig, get_service_config, save_service_config

router = APIRouter(tags=["service"])


@router.get("/settings")
async def get_settings_(user: User = Depends(current_user)) -> dict:
    cfg = await get_service_config(force=True)
    s = get_settings()
    bot_username = ""
    if s.telegram_bot_token:
        with contextlib.suppress(telegram.TelegramError, httpx.HTTPError):
            bot_username = await telegram.bot_username()
    return {
        **cfg.model_dump(),
        "langfuse_configured": bool(s.langfuse_public_key and s.langfuse_secret_key),
        "langfuse_host": s.langfuse_host,
        "openrouter_configured": bool(s.openrouter_api_key),
        "telegram_configured": bool(bot_username),
        "telegram_bot_username": bot_username,
        "pexels_configured": bool(s.pexels_api_key),
    }


class SettingsIn(BaseModel):
    langfuse_enabled: bool | None = None
    default_models: dict[str, RoleModel] | None = None
    extra_stamps: list[str] | None = None
    latin_whitelist: list[str] | None = None


@router.put("/settings")
async def put_settings(body: SettingsIn, user: User = Depends(current_user)) -> dict:
    cfg = await get_service_config(force=True)
    data = cfg.model_dump()
    for k, v in body.model_dump(exclude_unset=True).items():
        data[k] = v
    saved = await save_service_config(ServiceConfig.model_validate(data))
    tracing.set_enabled(saved.langfuse_enabled)
    return await get_settings_(user)


@router.get("/settings/overhead")
async def overhead(days: int = 30, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    day = cast(LlmCall.created_at, Date)
    rows = (await session.execute(select(day, LlmCall.role, func.sum(LlmCall.cost_usd), func.count()).where(LlmCall.channel_id.is_(None), LlmCall.created_at >= since).group_by(day, LlmCall.role).order_by(day))).all()
    return {"total": float(sum(r[2] or 0 for r in rows)), "series": [{"date": d.isoformat(), "role": r, "cost": float(c or 0), "calls": n} for d, r, c, n in rows]}


@router.get("/media/{media_id}")
async def media(media_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    mf = await session.get(MediaFile, media_id)
    if mf is None:
        raise HTTPException(404, "Файл не найден")
    return Response(content=mf.data, media_type=mf.content_type, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/channels/{channel_id}/analytics")
async def reports(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    rows = (await session.execute(select(AnalyticsReport).where(AnalyticsReport.channel_id == ch.id).order_by(AnalyticsReport.created_at.desc()).limit(24))).scalars().all()
    return [report_out(r) for r in rows]


class AnalyticsRun(BaseModel):
    days: int = Field(default=30, ge=7, le=120)


@router.post("/channels/{channel_id}/analytics/run")
async def run_analytics(channel_id: int, body: AnalyticsRun, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    if ch.type != ChannelType.smm:
        raise HTTPException(400, "Аналитика стратегии доступна для SMM-канала")
    run_id = await create_run(RunKind.analytics, ch.id, title=f"Отчёт за {body.days} дней", input={"channel_id": ch.id, "days": body.days})
    await kick(run_id)
    return {"run_id": run_id}


class ProposalDecision(BaseModel):
    action: Literal["approve", "reject"]
    strategy: Strategy | None = None


@router.post("/analytics/{report_id}/decision")
async def proposal_decision(report_id: int, body: ProposalDecision, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    rep = await session.get(AnalyticsReport, report_id)
    if rep is None:
        raise HTTPException(404, "Отчёт не найден")
    await owned_channel(rep.channel_id, user, session)
    run = await session.get(Run, rep.run_id) if rep.run_id else None
    if run is None or run.status != RunStatus.waiting:
        raise HTTPException(409, "Предложение уже обработано")
    resume = {"action": body.action}
    if body.strategy:
        resume["strategy"] = body.strategy.model_dump()
    await kick(run.id, resume)
    return {"run_id": run.id}


class DemoIn(BaseModel):
    weeks: int = Field(default=6, ge=2, le=12)


@router.post("/channels/{channel_id}/demo-history")
async def demo_history(channel_id: int, body: DemoIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    if ch.type != ChannelType.smm or not ch.strategy:
        raise HTTPException(400, "Демо-история нужна SMM-каналу со стратегией")
    strategy = Strategy.model_validate(ch.strategy)
    await session.execute(delete(Post).where(Post.channel_id == ch.id, Post.synthetic.is_(True)))
    rng = random.Random(ch.id)
    rubrics = strategy.rubrics or []
    weights = [max(r.share, 1) for r in rubrics]
    appeal = {r.name: rng.uniform(0.6, 1.8) for r in rubrics}
    now = datetime.now(UTC)
    created = 0
    for week in range(body.weeks, 0, -1):
        for day in sorted(rng.sample(range(7), k=min(5, 7))):
            rubric = rng.choices(rubrics, weights=weights)[0] if rubrics else None
            published = (now - timedelta(days=week * 7) + timedelta(days=day)).replace(hour=rng.choice([9, 12, 18, 20]), minute=0, second=0, microsecond=0)
            if published > now:
                continue
            base = 25 * (appeal.get(rubric.name, 1.0) if rubric else 1.0) * (1.25 if published.hour >= 18 else 1.0)
            reactions = max(0, int(rng.gauss(base, base * 0.3)))
            fmt = rubric.format if rubric else "text"
            post = Post(
                channel_id=ch.id,
                format=fmt,
                rubric=rubric.name if rubric else None,
                title=f"Демо: {rubric.name if rubric else 'пост'} №{created + 1}",
                text="Синтетический пост для демонстрации аналитики.",
                status=PostStatus.published,
                publish_at=published,
                published_at=published,
                reactions={"👍": reactions},
                reactions_total=reactions,
                rating=rng.choice([None, None, 1, 1, -1]),
                synthetic=True,
                poll_results={"counts": {"Да": rng.randint(20, 90), "Нет": rng.randint(10, 60)}, "total": 0} if fmt == "poll" else {},
            )
            session.add(post)
            created += 1
    await session.commit()
    return {"created": created}
