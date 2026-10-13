import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.schemas import DRAFT_SCHEMAS
from app.db.models import Channel, ChannelDocVersion, Post, PostEdit
from app.db.session import session_scope
from app.domain.enums import PostStatus
from app.domain.schemas import BRIEF_TEXT_FIELDS, Brief, Styleguide, StyleRule
from app.graphs.common import block, calculations_text, facts_text, join_blocks, node, output, system_prompt
from app.graphs.context import build_ctx
from app.graphs.post import render
from app.llm.agent import ask, run_agent
from app.prompts import registry
from app.quality.detector import detect
from app.tools import agent_tools


class FieldQuestion(BaseModel):
    field: str = Field(description="Имя поля из брифа: about, audience, goal, voice, avoid, positions")
    question: str


class BriefCheck(BaseModel):
    ok: bool
    questions: list[FieldQuestion] = Field(default_factory=list)


class UtilityState(TypedDict, total=False):
    run_id: str
    channel_id: int
    role: str
    key: str
    text: str
    samples: int
    result: dict[str, Any]


CHANNEL_KINDS = {
    "news": "новостной: посты о свежих событиях из RSS-лент по сетке времени",
    "smm": "SMM: экспертный канал с недельным контент-планом и рубриками",
}


def brief_text(brief: Brief, channel_type: str) -> str:
    lines = [f"Тип канала: {CHANNEL_KINDS.get(channel_type, channel_type)}"]
    for name in Brief.fields_for(channel_type):
        required = ", обязательное" if Brief.is_required(channel_type, name) else ""
        lines.append(f"{name} ({BRIEF_TEXT_FIELDS[name]}{required}): {getattr(brief, name).strip() or '—'}")
    return "\n".join(lines)


@node("brief_check", "Аккаунт-менеджер проверяет бриф")
async def brief_check(state: UtilityState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    brief = Brief.model_validate(ctx["brief"])
    missing = brief.required_missing(ctx["type"])
    system = await system_prompt(ctx, "account_manager", "brief_check")
    answer = await ask("account_manager", system, block("БРИФ", brief_text(brief, ctx["type"])), BriefCheck, label="Проверка брифа")
    fields = Brief.fields_for(ctx["type"])
    questions = [q.model_dump() for q in answer.questions if q.field in fields]
    for name in missing:
        if not any(q["field"] == name for q in questions):
            questions.append({"field": name, "question": f"Заполни поле «{BRIEF_TEXT_FIELDS[name]}»."})
    ok = answer.ok and not missing
    await output("brief_check", {"ok": ok, "questions": questions})
    return {"result": {"ok": ok, "questions": questions}}


class RulesAnswer(BaseModel):
    rules: list[str] = Field(default_factory=list)


@node("channel_rules", "Стратег выводит правила канала из правок владельца")
async def channel_rules(state: UtilityState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    async with session_scope() as s:
        edits = (
            await s.execute(select(PostEdit).where(PostEdit.channel_id == state["channel_id"], PostEdit.processed.is_(False)).order_by(PostEdit.created_at).limit(20))
        ).scalars().all()
        pairs = "\n\n".join(f"БЫЛО:\n{e.before[:1500]}\nСТАЛО:\n{e.after[:1500]}" for e in edits)
        edit_ids = [e.id for e in edits]
    if not edit_ids:
        return {"result": {"rules": []}}
    sg = Styleguide.model_validate(ctx["styleguide"])
    system = await system_prompt(ctx, "strategist", "rules")
    answer = await ask("strategist", system, join_blocks(block("ПРАВКИ", pairs), block("СТАЙЛГАЙД", sg.render())), RulesAnswer, label="Правила из правок")
    new_rules = [StyleRule(id=uuid.uuid4().hex[:8], text=r, origin="edits") for r in answer.rules[:5] if r.strip()]
    async with session_scope() as s:
        ch = await s.get(Channel, state["channel_id"])
        sg = Styleguide.model_validate(ch.styleguide or {})
        sg.rules = [*sg.rules, *new_rules]
        ch.styleguide = sg.model_dump()
        s.add(ChannelDocVersion(channel_id=ch.id, kind="styleguide", data=ch.styleguide, note="правила из правок владельца"))
        for e in (await s.execute(select(PostEdit).where(PostEdit.id.in_(edit_ids)))).scalars():
            e.processed = True
    await output("rules", {"rules": [r.text for r in new_rules]})
    return {"result": {"rules": [r.text for r in new_rules]}}


async def _writer_sample(ctx: dict, content: dict, editable: str) -> dict:
    brief = content.get("brief") or {}
    fmt = brief.get("format", "text")
    system = registry.compose(editable, "writer", "main", ctx["type"], {**_vars(ctx)}, fmt)
    user = join_blocks(
        f"Сегодня {ctx['today']}.",
        block("ЗАДАНИЕ", f"Тема: {brief.get('topic', '')}\nЦель для читателя: {brief.get('reader_goal', '')}\nКлючевая мысль: {brief.get('key_idea', '')}"),
        block("ИНФОПОВОД", f"{brief.get('topic', '')}\nИсточник: {(brief.get('source') or {}).get('url', '')}") if brief.get("source") else "",
        block("ФАКТЫ ОТ РАССЛЕДОВАТЕЛЯ", facts_text(content.get("facts") or [])),
        block("ВЫЧИСЛЕНИЯ", calculations_text(content.get("calculations") or [])),
        "Фактов больше не будет: напиши лучший пост по тому, что есть, без need_facts.",
    )
    session = agent_tools.ResearchSession(channel_id=ctx["channel_id"])
    draft = await run_agent("writer", system, user, [agent_tools.calculate_tool(session)], DRAFT_SCHEMAS[fmt], final_name="answer", max_steps=3, live_field="text", label="Пробный текст")
    d = draft.model_dump()
    title, text = render.draft_title_text(d, fmt)
    issues = [i for i in detect(text, title=title, fmt=fmt) if i.critical]
    return {"title": title, "text": text, "stamps": len(issues), "issues": [i.message for i in issues]}


def _vars(ctx: dict) -> dict:
    from app.graphs.common import ctx_vars

    return ctx_vars(ctx)


@node("prompt_test", "Пробный прогон промпта")
async def prompt_test(state: UtilityState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    async with session_scope() as s:
        posts = (
            await s.execute(
                select(Post)
                .where(Post.channel_id == state["channel_id"], Post.status.in_([PostStatus.published, PostStatus.scheduled, PostStatus.awaiting_approval]), Post.synthetic.is_(False))
                .order_by(Post.created_at.desc())
                .limit(state.get("samples") or 2)
            )
        ).scalars().all()
        contents = [p.content for p in posts if (p.content or {}).get("brief")]
    if not contents:
        return {"result": {"error": "Нет постов с сохранённым заданием: пробный прогон возможен после первых постов канала."}}
    pairs = []
    for content in contents:
        candidate = await _writer_sample(ctx, content, state["text"])
        baseline = await _writer_sample(ctx, content, registry.default_text("writer", "main"))
        pairs.append({"topic": (content.get("brief") or {}).get("topic", ""), "candidate": candidate, "default": baseline})
    summary = {
        "candidate_stamps": sum(p["candidate"]["stamps"] for p in pairs),
        "default_stamps": sum(p["default"]["stamps"] for p in pairs),
    }
    await output("prompt_test", {"pairs": pairs, **summary})
    return {"result": {"pairs": pairs, **summary}}


def build_brief_check_graph(checkpointer=None):
    g = StateGraph(UtilityState)
    g.add_node("brief_check", brief_check)
    g.add_edge(START, "brief_check")
    g.add_edge("brief_check", END)
    return g.compile(checkpointer=checkpointer)


def build_rules_graph(checkpointer=None):
    g = StateGraph(UtilityState)
    g.add_node("channel_rules", channel_rules)
    g.add_edge(START, "channel_rules")
    g.add_edge("channel_rules", END)
    return g.compile(checkpointer=checkpointer)


def build_prompt_test_graph(checkpointer=None):
    g = StateGraph(UtilityState)
    g.add_node("prompt_test", prompt_test)
    g.add_edge(START, "prompt_test")
    g.add_edge("prompt_test", END)
    return g.compile(checkpointer=checkpointer)
