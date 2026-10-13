from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChannelPromptVersion
from app.prompts import closed

DEFAULTS_DIR = Path(__file__).parent / "defaults"

PLACEHOLDERS = ("channel_title", "topics", "style_guide", "today", "audience", "strategy")


@dataclass(frozen=True)
class PromptSpec:
    role: str
    key: str
    title: str
    description: str
    modes: tuple[str, ...] = ("news", "smm")


SPECS: list[PromptSpec] = [
    PromptSpec("scout", "main", "Скаут", "Оценивает значимость сюжетов из RSS", ("news",)),
    PromptSpec("chief", "main", "Шеф-редактор", "Выбирает сюжет и ставит задание Писателю", ("news",)),
    PromptSpec("chief", "fix", "Шеф-редактор: исправление", "Исправляет задание по отчёту Фактчекера", ("news",)),
    PromptSpec("factchecker", "main", "Фактчекер", "Проверяет задание по источникам до написания", ("news",)),
    PromptSpec("factchecker", "goal", "Фактчекер: задача слота", "Проверяет, подтверждают ли факты задачу SMM-поста", ("smm",)),
    PromptSpec("researcher", "main", "Расследователь", "Ищет фактуру в интернете и в прошлых постах"),
    PromptSpec("writer", "main", "Писатель", "Пишет пост"),
    PromptSpec("editor", "main", "Редактор", "Проверяет пост и возвращает на доработку"),
    PromptSpec("publisher", "main", "Издатель", "Оформляет пост для Telegram"),
    PromptSpec("designer", "styleguide", "Оформитель: стайлгайд", "Составляет стайлгайд канала"),
    PromptSpec("strategist", "strategy", "Стратег: стратегия", "Составляет SMM-стратегию", ("smm",)),
    PromptSpec("strategist", "plan", "Стратег: контент-план", "Строит план на неделю", ("smm",)),
    PromptSpec("strategist", "topics", "Стратег: темы", "Предлагает темы для слота и банка идей"),
    PromptSpec("strategist", "proposal", "Стратег: изменения стратегии", "Предлагает изменения по отчёту Аналитика", ("smm",)),
    PromptSpec("strategist", "rules", "Стратег: правила канала", "Выводит правила из ручных правок владельца"),
    PromptSpec("account_manager", "brief_check", "Аккаунт-менеджер: проверка брифа", "Проверяет, можно ли работать по брифу"),
    PromptSpec("account_manager", "assist", "Аккаунт-менеджер: помощь с брифом", "Помогает сформулировать поле брифа"),
    PromptSpec("analyst", "main", "Аналитик", "Считает статистику постов кодом", ("smm",)),
]

SPEC_BY_KEY = {(s.role, s.key): s for s in SPECS}


@lru_cache
def default_text(role: str, key: str) -> str:
    return (DEFAULTS_DIR / f"{role}.{key}.md").read_text(encoding="utf-8").strip()


def closed_part(role: str, key: str, mode: str, fmt: str = "text") -> str:
    match role, key:
        case "scout", _:
            return closed.SCOUT
        case "chief", _:
            return closed.CHIEF
        case "factchecker", "goal":
            return closed.FACTCHECKER_GOAL
        case "factchecker", _:
            return closed.FACTCHECKER
        case "researcher", _:
            return closed.RESEARCHER
        case "writer", _:
            return closed.writer(mode, fmt)
        case "editor", _:
            return closed.editor(mode)
        case "publisher", _:
            return closed.PUBLISHER
        case "designer", _:
            return closed.DESIGNER
        case "strategist", _:
            return closed.STRATEGIST
        case "account_manager", _:
            return closed.ACCOUNT_MANAGER
        case "analyst", _:
            return closed.ANALYST
    raise KeyError(f"no closed part for {role}.{key}")


def substitute(text: str, variables: dict[str, str]) -> str:
    for name in PLACEHOLDERS:
        token = "{" + name + "}"
        if token in text:
            text = text.replace(token, variables.get(name, ""))
    return text


async def current_override(session: AsyncSession, channel_id: int, role: str, key: str) -> ChannelPromptVersion | None:
    row = (
        await session.execute(
            select(ChannelPromptVersion)
            .where(
                ChannelPromptVersion.channel_id == channel_id,
                ChannelPromptVersion.role == role,
                ChannelPromptVersion.key == key,
            )
            .order_by(ChannelPromptVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def editable_text(session: AsyncSession, channel_id: int | None, role: str, key: str) -> tuple[str, int | None]:
    if channel_id is not None:
        row = await current_override(session, channel_id, role, key)
        if row is not None and row.text is not None:
            return row.text, row.version
    return default_text(role, key), None


def compose(editable: str, role: str, key: str, mode: str, variables: dict[str, str], fmt: str = "text") -> str:
    vars_full = {"today": date.today().isoformat(), **variables}
    return substitute(editable, vars_full).strip() + "\n\n" + closed_part(role, key, mode, fmt)
