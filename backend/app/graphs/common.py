import functools
import logging
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.errors import GraphInterrupt

from app.db.session import session_scope
from app.domain.schemas import Brief, Strategy, Styleguide
from app.observability import tracing
from app.prompts import registry
from app.runtime.context import current_run, reset_node, set_node
from app.runtime.events import emit, set_run_progress
from app.runtime.redis import get_redis

log = logging.getLogger(__name__)


class RunCancelled(Exception):
    pass


def cancel_key(run_id: str) -> str:
    return f"run:cancel:{run_id}"


async def _check_cancel() -> None:
    ctx = current_run()
    if not ctx.run_id:
        return
    try:
        if await get_redis().get(cancel_key(ctx.run_id)):
            raise RunCancelled("Запуск остановлен пользователем")
    except RunCancelled:
        raise
    except Exception:
        return


NODE_LABELS: dict[str, dict[str | None, str]] = {}


def node_label(name: str, channel_type: str | None) -> str:
    labels = NODE_LABELS.get(name, {})
    return labels.get(channel_type) or labels.get(None, name)


def node(name: str, label: str, **by_type: str):
    if name in NODE_LABELS:
        raise ValueError(f"Узел {name} уже объявлен")
    NODE_LABELS[name] = {None: label, **by_type}

    def deco(fn: Callable[[dict], Awaitable[dict]]):
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            await _check_cancel()
            token = set_node(name)
            text = node_label(name, current_run().channel_type)
            started = time.monotonic()
            try:
                await set_run_progress(name, text)
                await emit("node_start", {"label": text})
                with tracing.observe(name, as_type="chain"):
                    update = await fn(state)
                await emit("node_end", {"label": text, "duration_ms": int((time.monotonic() - started) * 1000)})
                return update or {}
            except GraphInterrupt:
                await emit("node_wait", {"label": text})
                raise
            except Exception as exc:
                await emit("node_error", {"label": text, "error": f"{type(exc).__name__}: {exc}"[:1000]})
                raise
            finally:
                reset_node(token)

        wrapper.__name__ = name
        return wrapper

    return deco


def block(name: str, content: str) -> str:
    content = (content or "").strip()
    if not content:
        return ""
    return f"{name}:\n<data>\n{content}\n</data>"


def join_blocks(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p and p.strip())


def ctx_vars(ctx: dict) -> dict[str, str]:
    brief = Brief.model_validate(ctx.get("brief") or {})
    sg = Styleguide.model_validate(ctx.get("styleguide") or {})
    strategy = Strategy.model_validate(ctx.get("strategy") or {}) if ctx.get("strategy") else None
    return {
        "channel_title": ctx.get("title", ""),
        "topics": brief.about,
        "style_guide": sg.render(),
        "audience": brief.audience,
        "strategy": strategy.render() if strategy else "",
    }


async def system_prompt(ctx: dict, role: str, key: str = "main", fmt: str = "text") -> str:
    async with session_scope() as s:
        text, version = await registry.editable_text(s, ctx.get("channel_id"), role, key)
    run = current_run()
    run.extra.setdefault("prompt_versions", {})[f"{role}.{key}"] = version or "default"
    return registry.compose(text, role, key, ctx.get("type", "smm"), ctx_vars(ctx), fmt)


_ws = re.compile(r"\s+")
_quotes = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'", "—": "-", "–": "-", " ": " "})


def norm(text: str) -> str:
    return _ws.sub(" ", (text or "").translate(_quotes)).strip().lower()


def quote_in(quote: str, haystacks: list[str]) -> bool:
    q = norm(quote)
    if len(q) < 8:
        return False
    hs = [norm(h) for h in haystacks]
    if any(q in h for h in hs):
        return True
    if len(q) > 60:
        head, tail = q[:40], q[-40:]
        return any(head in h and tail in h for h in hs)
    return False


def facts_text(facts: list[dict]) -> str:
    lines = []
    for i, f in enumerate(facts, 1):
        date = f" ({f['date']})" if f.get("date") else ""
        src = f.get("source_url") or ""
        lines.append(f"{i}. {f['claim']}{date}\n   Цитата: «{f.get('quote', '')}»\n   Источник: {src}")
    return "\n".join(lines)


def calculations_text(calcs: list[dict]) -> str:
    return "\n".join(f"- {c['description']}: {c['output']}" for c in calcs if c.get("ok"))


def materials(state: dict) -> list[str]:
    out = []
    brief = state.get("brief") or {}
    out += [brief.get("topic", ""), brief.get("reader_goal", ""), brief.get("key_idea", ""), brief.get("channel_position") or ""]
    for f in state.get("facts") or []:
        out += [f.get("claim", ""), f.get("quote", ""), f.get("date", "")]
    for c in state.get("calculations") or []:
        out += [c.get("output", ""), c.get("description", "")]
    for s in state.get("sources") or []:
        out.append(s.get("text", ""))
    for p in state.get("past_posts") or []:
        out.append(p.get("date", ""))
    out.append((state.get("ctx") or {}).get("today", ""))
    return [x for x in out if x]


def main_source_url(state: dict) -> str | None:
    brief = state.get("brief") or {}
    if brief.get("mode") != "news":
        return None
    if (brief.get("source") or {}).get("url"):
        return brief["source"]["url"]
    counts = Counter(f["source_url"] for f in state.get("facts") or [] if f.get("source_url", "").startswith("http"))
    return counts.most_common(1)[0][0] if counts else None


def allowed_urls(state: dict) -> set[str]:
    urls = {f.get("source_url") for f in state.get("facts") or [] if f.get("source_url", "").startswith("http")}
    urls |= {s.get("url") for s in state.get("sources") or [] if s.get("url")}
    urls |= {p.get("url") for p in state.get("past_posts") or [] if p.get("url")}
    brief = state.get("brief") or {}
    if (brief.get("source") or {}).get("url"):
        urls.add(brief["source"]["url"])
    return {u for u in urls if u}


async def output(kind: str, data: dict[str, Any]) -> None:
    await emit("output", {"kind": kind, **data})
