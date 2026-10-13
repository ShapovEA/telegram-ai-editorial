from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, owned_channel
from app.api.serializers import channel_out, run_out
from app.api.utils import kick, run_inline
from app.db.models import Channel, ChannelDocVersion, ChannelPromptVersion, LlmCall, Post, Run, User
from app.db.session import get_session
from app.domain.enums import AWAITING_DECISION, ChannelStatus, ChannelType, PostStatus, RunKind, RunStatus
from app.domain.schemas import BRIEF_TEXT_FIELDS, Brief, ChannelOptions, RoleModel, Strategy, Styleguide, channel_schedule
from app.graphs.runner import create_run
from app.llm.agent import ask
from app.prompts import registry
from app.runtime.context import RunContext, reset_run, set_run
from app.services import telegram
from app.services.schedule import move_to_timezone

router = APIRouter(prefix="/channels", tags=["channels"])


class TelegramChannel(BaseModel):
    username: str = Field(min_length=1, max_length=200)


class ChannelCreate(TelegramChannel):
    type: Literal["news", "smm"]


class ChannelPatch(BaseModel):
    brief: Brief | None = None
    styleguide: Styleguide | None = None
    strategy: Strategy | None = None
    schedule: dict[str, Any] | None = None
    options: ChannelOptions | None = None
    publish_mode: Literal["autopilot", "approval"] | None = None
    budget_month_usd: float | None = None
    models: dict[str, RoleModel] | None = None
    status: Literal["active", "paused"] | None = None


@router.get("")
async def list_channels(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    channels = (await session.execute(select(Channel).where(Channel.owner_id == user.id).order_by(Channel.created_at))).scalars().all()
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    for ch in channels:
        cost = (await session.execute(select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.channel_id == ch.id, LlmCall.created_at >= month_start))).scalar_one()
        published = (await session.execute(select(func.count()).where(Post.channel_id == ch.id, Post.status == PostStatus.published))).scalar_one()
        waiting = (await session.execute(select(func.count()).where(Post.channel_id == ch.id, Post.status.in_(AWAITING_DECISION)))).scalar_one()
        active_runs = (await session.execute(select(func.count()).where(Run.channel_id == ch.id, Run.status.in_([RunStatus.running, RunStatus.queued])))).scalar_one()
        out.append({**channel_out(ch), "stats": {"cost_month": float(cost), "published": published, "attention": waiting, "active_runs": active_runs}})
    return out


async def verified_chat(username: str, user: User, session: AsyncSession, *, channel_id: int | None = None) -> dict:
    username = username.strip().replace("https://t.me/", "").lstrip("@")
    if not user.telegram_user_id:
        raise HTTPException(400, "Сначала привяжите свой Telegram-аккаунт к кабинету")
    try:
        chat = await telegram.get_chat(f"@{username}")
        admins = await telegram.get_admins(chat["id"])
        me = await telegram.get_me()
    except telegram.TelegramError as exc:
        raise HTTPException(400, f"Не удалось проверить канал: {exc}. Добавьте бота администратором канала.") from exc
    bot_admin = next((a for a in admins if a["user"]["id"] == me["id"]), None)
    if bot_admin is None or not bot_admin.get("can_post_messages", bot_admin.get("status") == "creator"):
        raise HTTPException(400, "Бот не администратор канала или не может публиковать сообщения")
    if not any(a["user"]["id"] == user.telegram_user_id for a in admins):
        raise HTTPException(403, "Ваш Telegram-аккаунт не администратор этого канала")
    taken = (await session.execute(select(Channel).where(Channel.telegram_chat_id == chat["id"], Channel.id != channel_id))).scalar_one_or_none()
    if taken:
        raise HTTPException(409, "Этот Telegram-канал уже подключён в сервисе")
    return {"id": chat["id"], "username": chat.get("username") or username, "title": chat["title"]}


@router.post("")
async def create_channel(body: ChannelCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    chat = await verified_chat(body.username, user, session)
    schedule = channel_schedule(body.type, None)
    ch = Channel(
        owner_id=user.id,
        type=body.type,
        title=chat["title"],
        telegram_chat_id=chat["id"],
        telegram_username=chat["username"],
        status=ChannelStatus.draft,
        schedule=schedule.model_dump(),
        options=ChannelOptions().model_dump(),
        brief={},
        styleguide={},
        strategy={},
        models={},
    )
    session.add(ch)
    await session.commit()
    return channel_out(ch)


@router.get("/{channel_id}")
async def get_channel(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    return channel_out(await owned_channel(channel_id, user, session))


@router.patch("/{channel_id}")
async def patch_channel(channel_id: int, body: ChannelPatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    data = body.model_dump(exclude_unset=True)
    if body.brief is not None:
        ch.brief = body.brief.model_dump()
        session.add(ChannelDocVersion(channel_id=ch.id, kind="brief", data=ch.brief))
    if body.styleguide is not None:
        ch.styleguide = body.styleguide.model_dump()
        session.add(ChannelDocVersion(channel_id=ch.id, kind="styleguide", data=ch.styleguide, note="правка владельца"))
    if body.strategy is not None:
        total = sum(r.share for r in body.strategy.rubrics)
        if body.strategy.rubrics and total != 100:
            raise HTTPException(422, f"Сумма долей рубрик должна быть 100, сейчас {total}")
        ch.strategy = body.strategy.model_dump()
        session.add(ChannelDocVersion(channel_id=ch.id, kind="strategy", data=ch.strategy, note="правка владельца"))
    if body.schedule is not None:
        old, new = channel_schedule(ch.type, ch.schedule), channel_schedule(ch.type, body.schedule)
        if new.timezone != old.timezone:
            await move_to_timezone(session, ch.id, old.timezone, new.timezone)
        ch.schedule = new.model_dump()
    if body.options is not None:
        ch.options = {**(ch.options or {}), **body.options.model_dump()}
    if body.publish_mode is not None:
        ch.publish_mode = body.publish_mode
    if "budget_month_usd" in data:
        ch.budget_month_usd = Decimal(str(body.budget_month_usd)) if body.budget_month_usd else None
    if body.models is not None:
        ch.models = {k: v.model_dump() for k, v in body.models.items()}
    if body.status is not None:
        if body.status == "active" and ch.status not in (ChannelStatus.active, ChannelStatus.paused):
            raise HTTPException(400, "Канал ещё не прошёл онбординг")
        ch.status = body.status
    await session.commit()
    return channel_out(ch)


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    await session.delete(ch)
    await session.commit()
    return {"ok": True}


@router.post("/{channel_id}/telegram")
async def connect_telegram(channel_id: int, body: TelegramChannel, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    chat = await verified_chat(body.username, user, session, channel_id=ch.id)
    ch.telegram_chat_id = chat["id"]
    ch.telegram_username = chat["username"]
    ch.title = chat["title"]
    await session.commit()
    return channel_out(ch)


@router.post("/{channel_id}/brief/check")
async def brief_check(channel_id: int, body: Brief, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    run_id = await create_run(RunKind.brief_check, ch.id, title="Проверка брифа", input={"channel_id": ch.id, "brief": body.model_dump()})
    run = await run_inline(run_id)
    if run.status != RunStatus.done:
        raise HTTPException(502, run.error or "Проверка не удалась")
    return run.result.get("result") or {}


class AssistIn(BaseModel):
    field: Literal["about", "audience", "goal", "voice", "avoid", "positions"]
    draft: str = Field(min_length=3, max_length=4000)


class AssistOut(BaseModel):
    text: str
    hint: str = ""


@router.post("/{channel_id}/brief/assist")
async def brief_assist(channel_id: int, body: AssistIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    from app.graphs.runner import role_models_for

    ch = await owned_channel(channel_id, user, session)
    if body.field not in Brief.fields_for(ch.type):
        raise HTTPException(400, "В брифе этого канала нет такого поля")
    editable, _ = await registry.editable_text(session, ch.id, "account_manager", "assist")
    system = registry.compose(editable, "account_manager", "assist", ch.type, {"channel_title": ch.title})
    token = set_run(RunContext(channel_id=ch.id, channel_type=ch.type, kind="assist", role_models=await role_models_for(ch)))
    try:
        out = await ask("account_manager", system, f"Поле: {BRIEF_TEXT_FIELDS[body.field]}\nЧерновик владельца:\n<data>\n{body.draft}\n</data>", AssistOut, label="Помощь с брифом")
    finally:
        reset_run(token)
    return out.model_dump()


@router.post("/{channel_id}/onboarding")
async def start_onboarding(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    if not ch.telegram_chat_id:
        raise HTTPException(400, "Подключите Telegram-канал: отдел берёт из него название канала")
    missing = Brief.model_validate(ch.brief or {}).required_missing(ch.type)
    if missing:
        raise HTTPException(400, "Заполните обязательные поля брифа: " + ", ".join(missing))
    if ch.type == ChannelType.news:
        from app.db.models import ChannelSource

        count = (await session.execute(select(func.count()).where(ChannelSource.channel_id == ch.id))).scalar_one()
        if not count:
            raise HTTPException(400, "Для новостного канала добавьте хотя бы одну RSS-ленту")
    run_id = await create_run(RunKind.onboarding, ch.id, title="Стайлгайд и стратегия" if ch.type == ChannelType.smm else "Стайлгайд", input={"channel_id": ch.id})
    ch.status = ChannelStatus.onboarding
    await session.commit()
    await kick(run_id)
    return {"run_id": run_id}


class OnboardingDecision(BaseModel):
    action: Literal["approve", "regenerate"]
    comment: str = ""
    styleguide: Styleguide | None = None
    strategy: Strategy | None = None


@router.post("/{channel_id}/onboarding/decision")
async def onboarding_decision(channel_id: int, body: OnboardingDecision, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    run = (
        await session.execute(select(Run).where(Run.channel_id == ch.id, Run.kind == RunKind.onboarding, Run.status == RunStatus.waiting).order_by(Run.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Нет онбординга, ожидающего решения")
    if body.strategy is not None and body.strategy.rubrics and sum(r.share for r in body.strategy.rubrics) != 100:
        raise HTTPException(422, "Сумма долей рубрик должна быть 100")
    resume = {"action": body.action, "comment": body.comment}
    if body.styleguide:
        resume["styleguide"] = body.styleguide.model_dump()
    if body.strategy:
        resume["strategy"] = body.strategy.model_dump()
    await kick(run.id, resume)
    return {"run_id": run.id}


@router.get("/{channel_id}/onboarding")
async def onboarding_state(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    run = (await session.execute(select(Run).where(Run.channel_id == ch.id, Run.kind == RunKind.onboarding).order_by(Run.created_at.desc()).limit(1))).scalar_one_or_none()
    return {"run": run_out(run) if run else None}


@router.get("/{channel_id}/prompts")
async def list_prompts(channel_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    out = []
    for spec in registry.SPECS:
        if ch.type not in spec.modes:
            continue
        row = await registry.current_override(session, ch.id, spec.role, spec.key)
        overridden = row is not None and row.text is not None
        out.append(
            {
                "role": spec.role,
                "key": spec.key,
                "title": spec.title,
                "description": spec.description,
                "text": row.text if overridden else registry.default_text(spec.role, spec.key),
                "default_text": registry.default_text(spec.role, spec.key),
                "overridden": overridden,
                "version": row.version if row else 0,
                "closed": registry.closed_part(spec.role, spec.key, ch.type),
                "placeholders": [p for p in registry.PLACEHOLDERS if "{" + p + "}" in registry.default_text(spec.role, spec.key)],
                "testable": spec.role == "writer",
            }
        )
    return out


class PromptIn(BaseModel):
    text: str = Field(min_length=20, max_length=20000)


async def _next_version(session: AsyncSession, channel_id: int, role: str, key: str) -> int:
    current = (await session.execute(select(func.max(ChannelPromptVersion.version)).where(ChannelPromptVersion.channel_id == channel_id, ChannelPromptVersion.role == role, ChannelPromptVersion.key == key))).scalar_one()
    return (current or 0) + 1


def _check_spec(role: str, key: str) -> None:
    if (role, key) not in registry.SPEC_BY_KEY:
        raise HTTPException(404, "Такого промпта нет")


@router.put("/{channel_id}/prompts/{role}/{key}")
async def save_prompt(channel_id: int, role: str, key: str, body: PromptIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    _check_spec(role, key)
    ch = await owned_channel(channel_id, user, session)
    version = await _next_version(session, ch.id, role, key)
    session.add(ChannelPromptVersion(channel_id=ch.id, role=role, key=key, text=body.text, version=version))
    await session.commit()
    return {"version": version}


@router.post("/{channel_id}/prompts/{role}/{key}/reset")
async def reset_prompt(channel_id: int, role: str, key: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    _check_spec(role, key)
    ch = await owned_channel(channel_id, user, session)
    version = await _next_version(session, ch.id, role, key)
    session.add(ChannelPromptVersion(channel_id=ch.id, role=role, key=key, text=None, version=version))
    await session.commit()
    return {"version": version, "text": registry.default_text(role, key)}


@router.get("/{channel_id}/prompts/{role}/{key}/versions")
async def prompt_versions(channel_id: int, role: str, key: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    _check_spec(role, key)
    ch = await owned_channel(channel_id, user, session)
    rows = (
        await session.execute(
            select(ChannelPromptVersion).where(ChannelPromptVersion.channel_id == ch.id, ChannelPromptVersion.role == role, ChannelPromptVersion.key == key).order_by(ChannelPromptVersion.version.desc())
        )
    ).scalars().all()
    return [{"version": r.version, "text": r.text, "reset": r.text is None, "created_at": r.created_at.isoformat()} for r in rows]


class PromptTestIn(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    samples: int = Field(default=2, ge=1, le=3)


@router.post("/{channel_id}/prompts/writer/main/test")
async def test_prompt(channel_id: int, body: PromptTestIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ch = await owned_channel(channel_id, user, session)
    run_id = await create_run(RunKind.prompt_test, ch.id, title="Пробный прогон промпта Писателя", input={"channel_id": ch.id, "text": body.text, "samples": body.samples})
    await kick(run_id)
    return {"run_id": run_id}


@router.get("/{channel_id}/docs/{kind}")
async def doc_versions(channel_id: int, kind: Literal["brief", "styleguide", "strategy"], user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    rows = (await session.execute(select(ChannelDocVersion).where(ChannelDocVersion.channel_id == ch.id, ChannelDocVersion.kind == kind).order_by(ChannelDocVersion.created_at.desc()).limit(30))).scalars().all()
    return [{"id": r.id, "data": r.data, "note": r.note, "created_at": r.created_at.isoformat()} for r in rows]
