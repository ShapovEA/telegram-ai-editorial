import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app.db.models import ChannelStory, Idea, Plan, Post, Slot, Story
from app.db.session import session_scope
from app.domain.enums import IdeaStatus, PostStatus, SlotStatus, StoryStatus
from app.domain.schemas import Brief, SmmSchedule, Strategy
from app.graphs.common import block, join_blocks, node, output, system_prompt
from app.graphs.context import build_ctx
from app.llm.agent import ask
from app.services import notify
from app.services.embeddings import EmbeddingError, cosine, embed
from app.services.novelty import classify_topic
from app.services.schedule import label, smm_grid
from app.tools.search import web_search

log = logging.getLogger(__name__)

MAX_FIXES = 2


class PlannedSlot(BaseModel):
    position: int = Field(description="Номер позиции из блока СЕТКА")
    rubric: str
    topic: str
    reader_goal: str
    key_idea: str
    channel_position: str = ""
    idea_id: int | None = None


class PlanAnswer(BaseModel):
    summary: str
    slots: list[PlannedSlot]


class TopicOption(BaseModel):
    rubric: str
    topic: str
    reader_goal: str
    key_idea: str


class TopicsAnswer(BaseModel):
    topics: list[TopicOption]


class PlanState(TypedDict, total=False):
    run_id: str
    channel_id: int
    plan_id: int
    mode: str
    slot_id: int
    comment: str
    hint: str
    rubric: str
    count: int
    ctx: dict[str, Any]
    grid: list[dict[str, Any]]
    kept: list[dict[str, Any]]
    context_text: str
    draft: list[dict[str, Any]]
    summary: str
    issues: list[dict[str, Any]]
    fix_attempts: int
    decision: dict[str, Any] | None
    topics: list[dict[str, Any]]
    outcome: str
    result: dict[str, Any]


async def _history(channel_id: int) -> tuple[str, dict[str, int]]:
    since = datetime.now(UTC) - timedelta(days=60)
    async with session_scope() as s:
        posts = (
            await s.execute(
                select(Post)
                .where(Post.channel_id == channel_id, Post.status.in_([PostStatus.published, PostStatus.scheduled, PostStatus.awaiting_approval]), Post.created_at >= since)
                .order_by(Post.created_at.desc())
                .limit(40)
            )
        ).scalars().all()
    lines, rubrics = [], Counter()
    for p in posts:
        when = (p.published_at or p.publish_at or p.created_at).date().isoformat()
        extra = []
        if p.status == PostStatus.published:
            extra.append(f"реакций {p.reactions_total}")
        if p.rating:
            extra.append("владельцу понравилось" if p.rating > 0 else "владельцу не понравилось")
        if p.poll_results:
            total = sum(p.poll_results.get("counts", {}).values()) if isinstance(p.poll_results.get("counts"), dict) else 0
            if total:
                extra.append("опрос: " + ", ".join(f"{k} — {v}" for k, v in p.poll_results["counts"].items()))
        lines.append(f"- [{p.id}] {when} {p.rubric or 'без рубрики'}: «{p.title or p.text[:80]}» ({'; '.join(extra) or 'нет данных'})")
        if p.created_at >= datetime.now(UTC) - timedelta(days=28) and p.rubric:
            rubrics[p.rubric] += 1
    return "\n".join(lines), dict(rubrics)


async def _ideas(channel_id: int) -> str:
    async with session_scope() as s:
        ideas = (
            await s.execute(
                select(Idea).where(Idea.channel_id == channel_id, Idea.status == IdeaStatus.new).order_by(Idea.vote.desc(), Idea.created_at.desc()).limit(25)
            )
        ).scalars().all()
    out = []
    for i in ideas:
        mark = " (нравится)" if i.vote > 0 else " (не нравится)" if i.vote < 0 else ""
        out.append(f"- [{i.id}] {i.rubric or ''}: {i.topic}{mark}")
    return "\n".join(out)


async def _feed_stories(channel_id: int, limit: int = 10) -> list[str]:
    since = datetime.now(UTC) - timedelta(days=7)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Story.title)
                .join(ChannelStory, ChannelStory.story_id == Story.id)
                .where(ChannelStory.channel_id == channel_id, ChannelStory.status == StoryStatus.new, Story.last_item_at >= since)
                .order_by(ChannelStory.relevance.desc().nulls_last(), Story.last_item_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    return [f"- {t}" for t in rows]


async def _trends(channel_id: int, brief: Brief) -> str:
    lines = await _feed_stories(channel_id)
    if len(lines) < 5 and brief.about.strip():
        try:
            results, _ = await web_search(brief.about[:80], category="news", limit=5, time_range="week")
            lines += [f"- {r['title']}" for r in results[:5]]
        except Exception:
            log.warning("trend search failed", exc_info=True)
    return "\n".join(dict.fromkeys(lines))


@node("collect_context", "Сбор контекста для плана: прошлые посты, результаты, идеи")
async def collect_context(state: PlanState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    async with session_scope() as s:
        plan = await s.get(Plan, state["plan_id"])
        week_start = plan.week_start
        comment = state.get("comment") or plan.comment or ""
        kept_rows = (
            await s.execute(
                select(Slot).where(Slot.plan_id == plan.id, (Slot.locked.is_(True)) | (Slot.status != SlotStatus.draft))
            )
        ).scalars().all()
        kept = [{"id": k.id, "publish_at": k.publish_at.isoformat(), "rubric": k.rubric, "topic": k.topic} for k in kept_rows]
    schedule = SmmSchedule.model_validate((await _schedule(state["channel_id"])) or {})
    grid_times = smm_grid(schedule, week_start, not_before=datetime.now(UTC) + timedelta(hours=1))
    kept_times = {k["publish_at"] for k in kept}
    grid = [{"position": i + 1, "publish_at": t.isoformat(), "label": label(t, schedule.timezone)} for i, t in enumerate(t for t in grid_times if t.isoformat() not in kept_times)]
    history, rubric_counts = await _history(state["channel_id"])
    ideas = await _ideas(state["channel_id"])
    brief = Brief.model_validate(ctx["brief"])
    trends = await _trends(state["channel_id"], brief)
    stats = ", ".join(f"{k}: {v}" for k, v in rubric_counts.items()) or "нет данных"
    text = join_blocks(
        block("СЕТКА", "\n".join(f"[{g['position']}] {g['label']}" for g in grid)),
        block("УЖЕ В ПЛАНЕ (не трогать)", "\n".join(f"- {k['rubric']}: {k['topic']}" for k in kept)),
        block("ПРОШЛЫЕ ПОСТЫ И РЕЗУЛЬТАТЫ", history or "Канал новый, постов ещё нет."),
        block("РУБРИКИ ЗА ПОСЛЕДНИЕ 4 НЕДЕЛИ", stats),
        block("БАНК ИДЕЙ", ideas),
        block("ПОЗИЦИИ КАНАЛА", brief.positions),
        block("ЧТО ОБСУЖДАЮТ В НИШЕ НА ЭТОЙ НЕДЕЛЕ", trends),
        block("КОММЕНТАРИЙ ВЛАДЕЛЬЦА КАНАЛА", comment),
    )
    await output("plan_context", {"grid": grid, "kept": kept, "trends": trends.splitlines()[:10]})
    return {"ctx": ctx, "grid": grid, "kept": kept, "context_text": text, "fix_attempts": 0, "comment": comment}


async def _schedule(channel_id: int) -> dict:
    from app.db.models import Channel

    async with session_scope() as s:
        ch = await s.get(Channel, channel_id)
        return ch.schedule if ch else {}


@node("strategist_plan", "Стратег составляет план недели")
async def strategist_plan(state: PlanState) -> dict:
    if not state["grid"]:
        return {"draft": [], "summary": "Все позиции недели уже заняты."}
    ctx = state["ctx"]
    system = await system_prompt(ctx, "strategist", "plan")
    answer = await ask("strategist", system, state["context_text"], PlanAnswer, label="Контент-план недели")
    draft = _merge_grid(state["grid"], [s.model_dump() for s in answer.slots])
    await output("plan_draft", {"summary": answer.summary, "slots": draft})
    return {"draft": draft, "summary": answer.summary}


def _merge_grid(grid: list[dict], slots: list[dict]) -> list[dict]:
    by_pos = {}
    for s in slots:
        if any(g["position"] == s["position"] for g in grid) and s["position"] not in by_pos:
            by_pos[s["position"]] = s
    return [{**g, **by_pos.get(g["position"], {"rubric": "", "topic": "", "reader_goal": "", "key_idea": "", "channel_position": "", "idea_id": None})} for g in grid]


@node("plan_checks", "Проверка плана: рубрики, доли, повторы")
async def plan_checks(state: PlanState) -> dict:
    ctx = state["ctx"]
    strategy = Strategy.model_validate(ctx["strategy"] or {})
    rubrics = {r.name: r for r in strategy.rubrics}
    positions = Brief.model_validate(ctx["brief"]).positions.strip()
    issues = []
    draft = state["draft"]
    for s in draft:
        if not s.get("topic"):
            issues.append({"position": s["position"], "message": "Позиция не заполнена"})
            continue
        r = rubrics.get(s["rubric"])
        if r is None:
            issues.append({"position": s["position"], "message": f"Рубрики «{s['rubric']}» нет в стратегии"})
        elif r.opinion and not positions:
            issues.append({"position": s["position"], "message": "Рубрика-мнение недоступна: в брифе нет позиций канала"})
    for a, b in zip(draft, draft[1:], strict=False):
        if a.get("rubric") and a["rubric"] == b.get("rubric") and len(rubrics) > 2:
            issues.append({"position": b["position"], "message": "Две одинаковые рубрики подряд", "soft": True})
    topics = [s["topic"] for s in draft if s.get("topic")]
    try:
        vectors = await embed(topics) if topics else []
    except EmbeddingError:
        vectors = []
    if vectors:
        vec_by_pos = {}
        idx = 0
        for s in draft:
            if s.get("topic"):
                vec_by_pos[s["position"]] = vectors[idx]
                s["embedding"] = vectors[idx]
                idx += 1
        positions_list = list(vec_by_pos)
        for i, p1 in enumerate(positions_list):
            for p2 in positions_list[i + 1 :]:
                if cosine(vec_by_pos[p1], vec_by_pos[p2]) > 0.88:
                    issues.append({"position": p2, "message": f"Тема почти совпадает с темой позиции {p1}"})
        for s in draft:
            if s["position"] not in vec_by_pos:
                continue
            verdict = await classify_topic(ctx["channel_id"], s["topic"], vector=vec_by_pos[s["position"]], days=ctx["options"]["novelty_window_days"])
            if verdict["verdict"] == "same":
                p = verdict["post"]
                issues.append({"position": s["position"], "message": f"Повтор поста от {p['date']} «{p['title']}» (сходство {p['similarity']})"})
            elif verdict["verdict"] == "development":
                s["related"] = verdict["post"]
    await output("plan_checks", {"issues": issues})
    return {"draft": draft, "issues": issues}


def route_after_checks(state: PlanState) -> str:
    hard = [i for i in state.get("issues") or [] if not i.get("soft")]
    if hard and (state.get("fix_attempts") or 0) < MAX_FIXES:
        return "strategist_fix"
    return "save_draft"


@node("strategist_fix", "Стратег исправляет проблемные позиции")
async def strategist_fix(state: PlanState) -> dict:
    ctx = state["ctx"]
    hard = [i for i in state["issues"] if not i.get("soft")]
    bad_positions = sorted({i["position"] for i in hard})
    current = "\n".join(f"[{s['position']}] {s['label']} — {s.get('rubric')}: {s.get('topic')}" for s in state["draft"])
    problems = "\n".join(f"- позиция {i['position']}: {i['message']}" for i in hard)
    system = await system_prompt(ctx, "strategist", "plan")
    user = join_blocks(
        state["context_text"],
        block("ТЕКУЩИЙ ПЛАН", current),
        block("ПРОБЛЕМЫ", problems),
        f"Верни новые варианты только для позиций {', '.join(map(str, bad_positions))}. Остальные позиции не возвращай.",
    )
    answer = await ask("strategist", system, user, PlanAnswer, label="Исправление плана")
    fixes = {s.position: s.model_dump() for s in answer.slots if s.position in bad_positions}
    draft = [{**d, **fixes[d["position"]]} if d["position"] in fixes else d for d in state["draft"]]
    for d in draft:
        if d["position"] in fixes:
            d.pop("embedding", None)
            d.pop("related", None)
    return {"draft": draft, "fix_attempts": (state.get("fix_attempts") or 0) + 1}


@node("save_draft", "Сохранение черновика плана")
async def save_draft(state: PlanState) -> dict:
    ctx = state["ctx"]
    issues_by_pos: dict[int, list] = {}
    for i in state.get("issues") or []:
        issues_by_pos.setdefault(i["position"], []).append({"code": "plan", "message": i["message"]})
    async with session_scope() as s:
        plan = await s.get(Plan, state["plan_id"])
        await s.execute(delete(Slot).where(Slot.plan_id == plan.id, Slot.status == SlotStatus.draft, Slot.locked.is_(False)))
        first = None
        for d in state["draft"]:
            if not d.get("topic"):
                continue
            publish_at = datetime.fromisoformat(d["publish_at"])
            first = publish_at if first is None or publish_at < first else first
            warnings = issues_by_pos.get(d["position"], [])
            if d.get("related"):
                warnings.append({"code": "development", "message": f"Развивает пост от {d['related']['date']} «{d['related']['title']}»"})
            s.add(
                Slot(
                    channel_id=ctx["channel_id"],
                    plan_id=plan.id,
                    publish_at=publish_at,
                    rubric=d.get("rubric"),
                    format=_rubric_format(ctx, d.get("rubric")),
                    topic=d["topic"],
                    reader_goal=d.get("reader_goal", ""),
                    key_idea=d.get("key_idea", ""),
                    channel_position=d.get("channel_position") or None,
                    idea_id=d.get("idea_id") if d.get("idea_id") else None,
                    status=SlotStatus.draft,
                    warnings=warnings,
                    embedding=d.get("embedding"),
                )
            )
            if d.get("idea_id"):
                await s.execute(update(Idea).where(Idea.id == d["idea_id"], Idea.channel_id == ctx["channel_id"]).values(status=IdeaStatus.planned))
        plan.summary = state.get("summary", "")
        plan.status = "draft"
        plan.comment = state.get("comment") or ""
        hours = ctx["options"].get("plan_auto_approve_hours", 12)
        if first:
            plan.auto_approve_at = max(first - timedelta(hours=hours), datetime.now(UTC) + timedelta(minutes=30))
        plan.run_id = state["run_id"]
    return {}


def _rubric_format(ctx: dict, rubric: str | None) -> str:
    strategy = Strategy.model_validate(ctx["strategy"] or {})
    r = next((x for x in strategy.rubrics if x.name == rubric), None)
    return r.format if r else "text"


def route_after_save(state: PlanState) -> str:
    return "approve_all" if state["ctx"]["publish_mode"] == "autopilot" else "notify_plan"


@node("notify_plan", "План отправлен владельцу на утверждение")
async def notify_plan(state: PlanState) -> dict:
    await notify.notify_owner(state["ctx"]["channel_id"], "Контент-план на неделю готов и ждёт утверждения.", buttons=notify.link_buttons(f"/channels/{state['ctx']['channel_id']}/plan"))
    return {}


@node("await_plan", "Ожидание утверждения плана")
async def await_plan(state: PlanState) -> dict:
    decision = interrupt({"type": "plan_approval", "plan_id": state["plan_id"]})
    return {"decision": decision if isinstance(decision, dict) else {"action": str(decision)}}


def route_after_plan_decision(state: PlanState) -> str:
    action = (state.get("decision") or {}).get("action")
    if action == "replan":
        return "collect_context"
    return "approve_all"


@node("approve_all", "План утверждён")
async def approve_all(state: PlanState) -> dict:
    async with session_scope() as s:
        plan = await s.get(Plan, state["plan_id"])
        await s.execute(update(Slot).where(Slot.plan_id == plan.id, Slot.status == SlotStatus.draft).values(status=SlotStatus.approved))
        plan.status = "approved"
        plan.approved_at = datetime.now(UTC)
    await output("plan_approved", {"plan_id": state["plan_id"]})
    return {"outcome": "approved", "decision": None, "result": {"plan_id": state["plan_id"]}}


def route_start(state: PlanState) -> str:
    return "suggest_topics" if state.get("mode") in ("suggest_topics", "replace_slot") else "collect_context"


@node("suggest_topics", "Стратег предлагает темы")
async def suggest_topics(state: PlanState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    history, _ = await _history(state["channel_id"])
    async with session_scope() as s:
        planned = (await s.execute(select(Slot.topic).where(Slot.channel_id == state["channel_id"], Slot.publish_at >= datetime.now(UTC)))).scalars().all()
        slot = await s.get(Slot, state["slot_id"]) if state.get("slot_id") else None
    rubric = state.get("rubric") or (slot.rubric if slot else "")
    count = 1 if state.get("mode") == "replace_slot" else state.get("count") or 4
    hint = state.get("hint") or state.get("comment") or ""
    user = join_blocks(
        f"Предложи {count} {'тему' if count == 1 else 'тем'}" + (f" для рубрики «{rubric}»" if rubric else "") + ".",
        block("ПРОШЛЫЕ ПОСТЫ", history),
        block("УЖЕ ЗАПЛАНИРОВАНО", "\n".join(f"- {t}" for t in planned)),
        block("ЗАМЕНЯЕМАЯ ТЕМА", slot.topic if slot and state.get("mode") == "replace_slot" else ""),
        block("ПОДСКАЗКА ВЛАДЕЛЬЦА", hint),
        block("ИДЕИ", await _ideas(state["channel_id"])),
        block("СВЕЖИЕ СЮЖЕТЫ ИЗ ЛЕНТ КАНАЛА", "\n".join(await _feed_stories(state["channel_id"]))),
    )
    system = await system_prompt(ctx, "strategist", "topics")
    answer = await ask("strategist", system, user, TopicsAnswer, label="Варианты тем")
    topics = [t.model_dump() for t in answer.topics][: max(count, 1)]
    checked = []
    for t in topics:
        try:
            verdict = await classify_topic(state["channel_id"], t["topic"], days=ctx["options"]["novelty_window_days"])
        except EmbeddingError:
            verdict = {"verdict": "new", "post": None}
        checked.append({**t, "novelty": verdict["verdict"], "similar_post": verdict.get("post")})
    if state.get("mode") == "replace_slot" and slot is not None and checked:
        best = next((t for t in checked if t["novelty"] != "same"), checked[0])
        async with session_scope() as s:
            sl = await s.get(Slot, slot.id)
            sl.topic, sl.reader_goal, sl.key_idea = best["topic"], best["reader_goal"], best["key_idea"]
            sl.rubric = best["rubric"] or sl.rubric
            sl.warnings = [w for w in (sl.warnings or []) if w.get("code") not in ("plan", "needs_attention", "slot_return")]
            sl.embedding = None
            if sl.status in (SlotStatus.needs_attention, SlotStatus.failed):
                sl.status = SlotStatus.approved
    await output("topics", {"topics": checked})
    return {"topics": checked, "result": {"topics": checked}}


def build_planning_graph(checkpointer=None):
    g = StateGraph(PlanState)
    g.add_node("collect_context", collect_context)
    g.add_node("strategist_plan", strategist_plan)
    g.add_node("plan_checks", plan_checks)
    g.add_node("strategist_fix", strategist_fix)
    g.add_node("save_draft", save_draft)
    g.add_node("notify_plan", notify_plan)
    g.add_node("await_plan", await_plan)
    g.add_node("approve_all", approve_all)
    g.add_node("suggest_topics", suggest_topics)
    g.add_conditional_edges(START, route_start, ["collect_context", "suggest_topics"])
    g.add_edge("collect_context", "strategist_plan")
    g.add_edge("strategist_plan", "plan_checks")
    g.add_conditional_edges("plan_checks", route_after_checks, ["strategist_fix", "save_draft"])
    g.add_edge("strategist_fix", "plan_checks")
    g.add_conditional_edges("save_draft", route_after_save, ["approve_all", "notify_plan"])
    g.add_edge("notify_plan", "await_plan")
    g.add_conditional_edges("await_plan", route_after_plan_decision, ["collect_context", "approve_all"])
    g.add_edge("approve_all", END)
    g.add_edge("suggest_topics", END)
    return g.compile(checkpointer=checkpointer)


def default_week(today: date | None = None) -> date:
    from app.services.schedule import next_week_start

    return next_week_start(today)
