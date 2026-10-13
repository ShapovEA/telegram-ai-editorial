from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from app.db.models import Channel, ChannelDocVersion, Idea
from app.db.session import session_scope
from app.domain.enums import ChannelStatus, ChannelType
from app.domain.schemas import Brief, Strategy, Styleguide, StyleStructured
from app.graphs.common import block, join_blocks, node, output, system_prompt
from app.graphs.context import build_ctx
from app.graphs.planning import TopicsAnswer
from app.llm.agent import ask
from app.services import feeds, samples
from app.services.embeddings import EmbeddingError, embed


class StyleguideAnswer(BaseModel):
    structured: StyleStructured
    text: str


class OnboardingState(TypedDict, total=False):
    run_id: str
    channel_id: int
    ctx: dict[str, Any]
    refs: dict[str, Any]
    styleguide: dict[str, Any]
    strategy: dict[str, Any] | None
    comment: str
    decision: dict[str, Any] | None
    result: dict[str, Any]


@node("read_samples", "Чтение образцов текстов и сайта")
async def read_samples(state: OnboardingState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    brief = Brief.model_validate(ctx["brief"])
    refs = await samples.collect(brief.samples, brief.site_url)
    async with session_scope() as s:
        ch = await s.get(Channel, state["channel_id"])
        ch.status = ChannelStatus.onboarding
        ch.options = {**(ch.options or {}), "sample_posts": [p["text"] for p in refs["samples"][:6]]}
    await output("samples", {"samples": len(refs["samples"]), "site": bool(refs["site"]), "rejected": refs["rejected"]})
    return {"ctx": ctx, "refs": refs, "comment": ""}


@node("designer_styleguide", "Оформитель составляет стайлгайд")
async def designer_styleguide(state: OnboardingState) -> dict:
    ctx = state["ctx"]
    brief = Brief.model_validate(ctx["brief"])
    refs = state.get("refs") or {}
    sample_texts = "\n\n---\n\n".join(f"[{p['source']}]\n{p['text']}" for p in refs.get("samples", [])[:8])
    system = await system_prompt(ctx, "designer", "styleguide")
    user = join_blocks(
        block("БРИФ", brief.render(ctx["type"])),
        block("ОБРАЗЦЫ ТЕКСТОВ", sample_texts),
        block("САЙТ", refs.get("site", "")),
        block("КОММЕНТАРИЙ ВЛАДЕЛЬЦА", state.get("comment") or ""),
    )
    answer = await ask("designer", system, user, StyleguideAnswer, label="Стайлгайд", live_field="text")
    existing = Styleguide.model_validate(ctx.get("styleguide") or {})
    sg = Styleguide(structured=answer.structured, text=answer.text, rules=existing.rules)
    await output("styleguide", sg.model_dump())
    return {"styleguide": sg.model_dump()}


def route_after_styleguide(state: OnboardingState) -> str:
    return "strategist_strategy" if state["ctx"]["type"] == ChannelType.smm else "await_approval"


@node("strategist_strategy", "Стратег составляет стратегию")
async def strategist_strategy(state: OnboardingState) -> dict:
    ctx = state["ctx"]
    brief = Brief.model_validate(ctx["brief"])
    system = await system_prompt(ctx, "strategist", "strategy")
    user = join_blocks(
        block("БРИФ", brief.render(ctx["type"])),
        block("САЙТ", (state.get("refs") or {}).get("site", "")),
        block("КОММЕНТАРИЙ ВЛАДЕЛЬЦА", state.get("comment") or ""),
    )
    strategy = await ask("strategist", system, user, Strategy, label="Стратегия")
    total = sum(r.share for r in strategy.rubrics) or 1
    if total != 100 and strategy.rubrics:
        for r in strategy.rubrics:
            r.share = round(r.share * 100 / total)
        strategy.rubrics[0].share += 100 - sum(r.share for r in strategy.rubrics)
    if not brief.positions.strip():
        for r in strategy.rubrics:
            r.opinion = False
    await output("strategy", strategy.model_dump())
    return {"strategy": strategy.model_dump()}


@node("await_approval", "Ожидание утверждения стайлгайда и стратегии")
async def await_approval(state: OnboardingState) -> dict:
    decision = interrupt({"type": "onboarding_approval", "styleguide": state["styleguide"], "strategy": state.get("strategy")})
    return {"decision": decision if isinstance(decision, dict) else {"action": str(decision)}}


def route_after_decision(state: OnboardingState) -> str:
    d = state.get("decision") or {}
    if d.get("action") == "regenerate":
        return "regenerate"
    return "save_documents"


@node("regenerate", "Переделка по комментарию владельца")
async def regenerate(state: OnboardingState) -> dict:
    d = state.get("decision") or {}
    return {"comment": d.get("comment", ""), "decision": None}


@node("save_documents", "Сохранение стайлгайда и стратегии")
async def save_documents(state: OnboardingState) -> dict:
    d = state.get("decision") or {}
    sg = Styleguide.model_validate(d.get("styleguide") or state["styleguide"])
    strategy = d.get("strategy") or state.get("strategy")
    async with session_scope() as s:
        ch = await s.get(Channel, state["channel_id"])
        ch.styleguide = sg.model_dump()
        s.add(ChannelDocVersion(channel_id=ch.id, kind="styleguide", data=ch.styleguide, note="онбординг"))
        if strategy:
            ch.strategy = Strategy.model_validate(strategy).model_dump()
            s.add(ChannelDocVersion(channel_id=ch.id, kind="strategy", data=ch.strategy, note="онбординг"))
        ch.status = ChannelStatus.active
    from app.worker.tasks import fetch_feed

    for source_id in await feeds.due_sources(channel_id=state["channel_id"]):
        await fetch_feed.kiq(source_id)
    return {"decision": None}


@node("seed_ideas", "Стратег наполняет банк идей")
async def seed_ideas(state: OnboardingState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    brief = Brief.model_validate(ctx["brief"])
    system = await system_prompt(ctx, "strategist", "topics")
    hint = (
        "Вечнозелёные темы для запасного банка идей новостного канала: частые ошибки, спорные и неочевидные случаи, практические разборы. Уровень — по аудитории из брифа, не пересказ основ из учебника."
        if ctx["type"] == ChannelType.news
        else "Темы для банка идей на ближайший месяц, по всем рубрикам стратегии."
    )
    user = join_blocks(f"Предложи 12 тем. {hint}", block("БРИФ", brief.render(ctx["type"])))
    answer = await ask("strategist", system, user, TopicsAnswer, label="Банк идей")
    topics = answer.topics[:15]
    try:
        vectors = await embed([t.topic for t in topics])
    except EmbeddingError:
        vectors = [None] * len(topics)
    async with session_scope() as s:
        for t, v in zip(topics, vectors, strict=False):
            s.add(Idea(channel_id=state["channel_id"], rubric=t.rubric or None, topic=t.topic, reader_goal=t.reader_goal, note=t.key_idea, origin="strategy", embedding=v))
    await output("ideas", {"count": len(topics)})
    return {"result": {"activated_at": datetime.now(UTC).isoformat(), "ideas": len(topics)}}


def build_onboarding_graph(checkpointer=None):
    g = StateGraph(OnboardingState)
    g.add_node("read_samples", read_samples)
    g.add_node("designer_styleguide", designer_styleguide)
    g.add_node("strategist_strategy", strategist_strategy)
    g.add_node("await_approval", await_approval)
    g.add_node("regenerate", regenerate)
    g.add_node("save_documents", save_documents)
    g.add_node("seed_ideas", seed_ideas)
    g.add_edge(START, "read_samples")
    g.add_edge("read_samples", "designer_styleguide")
    g.add_conditional_edges("designer_styleguide", route_after_styleguide, ["strategist_strategy", "await_approval"])
    g.add_edge("strategist_strategy", "await_approval")
    g.add_conditional_edges("await_approval", route_after_decision, ["regenerate", "save_documents"])
    g.add_edge("regenerate", "designer_styleguide")
    g.add_edge("save_documents", "seed_ideas")
    g.add_edge("seed_ideas", END)
    return g.compile(checkpointer=checkpointer)
