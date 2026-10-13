import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import AnalyticsReport, Channel, ChannelDocVersion, MediaFile, Post
from app.db.session import session_scope
from app.domain.enums import PostStatus
from app.domain.schemas import Strategy
from app.graphs.common import block, join_blocks, node, output, system_prompt
from app.graphs.context import build_ctx
from app.llm.agent import ask, run_agent
from app.tools import agent_tools


class AnalystReport(BaseModel):
    summary: str
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    preliminary: bool = False
    rubric_stats: list[dict[str, Any]] = Field(default_factory=list, description="Среднее число реакций и число постов по рубрикам из расчёта")


class StrategyProposal(BaseModel):
    changes: list[str]
    strategy: Strategy


class AnalyticsState(TypedDict, total=False):
    run_id: str
    channel_id: int
    days: int
    ctx: dict[str, Any]
    posts: list[dict[str, Any]]
    report: dict[str, Any]
    report_id: int
    proposal: dict[str, Any] | None
    decision: dict[str, Any] | None
    result: dict[str, Any]


@node("collect_stats", "Сбор статистики постов")
async def collect_stats(state: AnalyticsState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    since = datetime.now(UTC) - timedelta(days=state.get("days") or 30)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Post).where(Post.channel_id == state["channel_id"], Post.status == PostStatus.published, Post.published_at >= since).order_by(Post.published_at)
            )
        ).scalars().all()
    posts = [
        {
            "id": p.id,
            "title": p.title or p.text[:60],
            "rubric": p.rubric or "без рубрики",
            "format": p.format,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "weekday": p.published_at.weekday() if p.published_at else None,
            "hour": p.published_at.hour if p.published_at else None,
            "reactions": p.reactions_total,
            "reactions_by_type": p.reactions,
            "poll": p.poll_results,
            "rating": p.rating,
            "synthetic": p.synthetic,
        }
        for p in rows
    ]
    await output("stats", {"posts": len(posts), "synthetic": sum(1 for p in posts if p["synthetic"])})
    return {"ctx": ctx, "posts": posts}


@node("analyst", "Аналитик считает статистику кодом")
async def analyst(state: AnalyticsState) -> dict:
    ctx = state["ctx"]
    posts = state["posts"]
    images: list[bytes] = []
    runs: list[dict] = []
    tool = agent_tools.analyst_python_tool({"posts.json": json.dumps(posts, ensure_ascii=False)}, images, runs)
    system = await system_prompt(ctx, "analyst")
    synthetic_note = "Часть данных синтетическая (демо-история): отметь это в summary." if any(p["synthetic"] for p in posts) else ""
    user = join_blocks(
        f"Период: последние {state.get('days') or 30} дней. Постов: {len(posts)}. {synthetic_note}",
        block("СТРАТЕГИЯ", Strategy.model_validate(ctx["strategy"] or {}).render()),
        "Посчитай метрики кодом и верни отчёт инструментом report.",
    )
    report = await run_agent("analyst", system, user, [tool], AnalystReport, final_name="report", max_steps=6, label="Отчёт за период")
    period_end = date.today()
    period_start = period_end - timedelta(days=state.get("days") or 30)
    async with session_scope() as s:
        media_ids = []
        for img in images[:4]:
            mf = MediaFile(channel_id=state["channel_id"], content_type="image/png", data=img, meta={"kind": "analytics"})
            s.add(mf)
            await s.flush()
            media_ids.append(mf.id)
        rep = AnalyticsReport(
            channel_id=state["channel_id"],
            period_start=period_start,
            period_end=period_end,
            report={**report.model_dump(), "charts": media_ids, "code_runs": runs},
            run_id=state["run_id"],
        )
        s.add(rep)
        await s.flush()
        report_id = rep.id
    await output("report", {**report.model_dump(), "charts": media_ids})
    return {"report": report.model_dump(), "report_id": report_id}


@node("strategist_proposal", "Стратег предлагает изменения стратегии")
async def strategist_proposal(state: AnalyticsState) -> dict:
    ctx = state["ctx"]
    rep = state["report"]
    system = await system_prompt(ctx, "strategist", "proposal")
    user = join_blocks(
        block("ОТЧЁТ АНАЛИТИКА", json.dumps(rep, ensure_ascii=False, indent=1)),
    )
    proposal = await ask("strategist", system, user, StrategyProposal, label="Изменения стратегии")
    async with session_scope() as s:
        rep_row = await s.get(AnalyticsReport, state["report_id"])
        rep_row.proposal = proposal.model_dump()
    await output("proposal", proposal.model_dump())
    return {"proposal": proposal.model_dump()}


@node("await_decision", "Ожидание решения по стратегии")
async def await_decision(state: AnalyticsState) -> dict:
    decision = interrupt({"type": "strategy_proposal", "report_id": state["report_id"]})
    return {"decision": decision if isinstance(decision, dict) else {"action": str(decision)}}


@node("apply_decision", "Применение решения")
async def apply_decision(state: AnalyticsState) -> dict:
    d = state.get("decision") or {}
    approved = d.get("action") == "approve"
    async with session_scope() as s:
        rep = await s.get(AnalyticsReport, state["report_id"])
        rep.status = "approved" if approved else "rejected"
        if approved and state.get("proposal"):
            ch = await s.get(Channel, state["channel_id"])
            ch.strategy = Strategy.model_validate(d.get("strategy") or state["proposal"]["strategy"]).model_dump()
            s.add(ChannelDocVersion(channel_id=ch.id, kind="strategy", data=ch.strategy, note="по отчёту аналитика"))
    return {"result": {"report_id": state["report_id"], "approved": approved}}


def route_after_analyst(state: AnalyticsState) -> str:
    return "strategist_proposal" if len(state.get("posts") or []) >= 3 else END


def build_analytics_graph(checkpointer=None):
    g = StateGraph(AnalyticsState)
    g.add_node("collect_stats", collect_stats)
    g.add_node("analyst", analyst)
    g.add_node("strategist_proposal", strategist_proposal)
    g.add_node("await_decision", await_decision)
    g.add_node("apply_decision", apply_decision)
    g.add_edge(START, "collect_stats")
    g.add_edge("collect_stats", "analyst")
    g.add_conditional_edges("analyst", route_after_analyst, ["strategist_proposal", END])
    g.add_edge("strategist_proposal", "await_decision")
    g.add_edge("await_decision", "apply_decision")
    g.add_edge("apply_decision", END)
    return g.compile(checkpointer=checkpointer)
