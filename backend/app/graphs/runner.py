import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from langgraph.types import Command
from sqlalchemy import func, select, update

from app.db.models import Channel, ChannelStory, Run, RunEvent, Slot
from app.db.session import session_scope
from app.domain.enums import RunKind, RunStatus, SlotStatus, StoryStatus
from app.domain.schemas import RoleModel
from app.graphs.checkpointer import get_checkpointer
from app.graphs.common import RunCancelled
from app.llm.agent import BadOutput
from app.llm.client import BudgetExceeded, LLMUnavailable
from app.observability import tracing
from app.runtime.context import RunContext, reset_run, set_run
from app.runtime.events import emit, notify_channel
from app.services.service_settings import get_service_config

log = logging.getLogger(__name__)

DEFER_STEPS = [15, 30, 60, 120]
MAX_DEFERS = 4


def _builders(channel_type: str | None) -> dict[str, Callable]:
    from app.graphs.analytics import build_analytics_graph
    from app.graphs.onboarding import build_onboarding_graph
    from app.graphs.planning import build_planning_graph
    from app.graphs.post.graph import build_post_graph
    from app.graphs.utility import build_brief_check_graph, build_prompt_test_graph, build_rules_graph

    return {
        RunKind.post: partial(build_post_graph, channel_type),
        RunKind.planning: build_planning_graph,
        RunKind.onboarding: partial(build_onboarding_graph, channel_type),
        RunKind.analytics: build_analytics_graph,
        RunKind.brief_check: build_brief_check_graph,
        RunKind.prompt_test: build_prompt_test_graph,
        RunKind.channel_rules: build_rules_graph,
    }


_compiled: dict[tuple[str, str | None], Any] = {}


async def graph_for(kind: str, channel_type: str | None):
    key = (kind, channel_type)
    if key not in _compiled:
        _compiled[key] = _builders(channel_type)[kind](await get_checkpointer())
    return _compiled[key]


async def create_run(kind: str, channel_id: int | None, *, title: str, input: dict[str, Any], slot_id: int | None = None, plan_id: int | None = None, post_id: int | None = None) -> str:
    async with session_scope() as s:
        run = Run(kind=kind, channel_id=channel_id, title=title, input=input, slot_id=slot_id, plan_id=plan_id, post_id=post_id, status=RunStatus.queued)
        s.add(run)
        await s.flush()
        run_id = run.id
    if channel_id:
        await notify_channel(channel_id, {"type": "run_created", "run_id": run_id, "kind": kind, "title": title})
    return run_id


async def role_models_for(ch: Channel | None) -> dict[str, RoleModel]:
    cfg = await get_service_config()
    models: dict[str, RoleModel] = dict(cfg.default_models)
    if ch is not None:
        for role, data in (ch.models or {}).items():
            try:
                models[role] = RoleModel.model_validate(data)
            except Exception:
                log.warning("bad model config for %s", role)
    return models


async def _context_for(run: Run) -> RunContext:
    models: dict[str, RoleModel] = await role_models_for(None)
    budget = None
    channel_type = None
    if run.channel_id:
        async with session_scope() as s:
            ch = await s.get(Channel, run.channel_id)
            if ch:
                models = await role_models_for(ch)
                budget = float(ch.budget_month_usd) if ch.budget_month_usd else None
                channel_type = ch.type
    async with session_scope() as s:
        seq = (await s.execute(select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run.id))).scalar_one()
    return RunContext(run_id=run.id, channel_id=run.channel_id, channel_type=channel_type, post_id=run.post_id, kind=run.kind, role_models=models, budget_usd=budget, seq=int(seq))


async def _set(run_id: str, **values: Any) -> None:
    async with session_scope() as s:
        await s.execute(update(Run).where(Run.id == run_id).values(**values))


async def _on_problem(run: Run, status: str, message: str) -> None:
    if run.kind == RunKind.post and run.slot_id:
        slot_status = {RunStatus.deferred: SlotStatus.deferred, RunStatus.cancelled: SlotStatus.skipped}.get(status, SlotStatus.failed)
        async with session_scope() as s:
            slot = await s.get(Slot, run.slot_id)
            if slot:
                slot.status = slot_status
                slot.warnings = [*(slot.warnings or []), {"code": status, "message": message[:500]}]
                if slot.story_id and status != RunStatus.deferred:
                    await s.execute(
                        update(ChannelStory)
                        .where(ChannelStory.channel_id == slot.channel_id, ChannelStory.story_id == slot.story_id, ChannelStory.status == StoryStatus.in_work)
                        .values(status=StoryStatus.new, reason="Пост не написан из-за ошибки, сюжет вернулся в пул")
                    )


def _result_summary(values: dict[str, Any]) -> dict[str, Any]:
    keys = ("outcome", "outcome_reason", "post_id", "plan_id", "report_id", "result")
    return {k: values.get(k) for k in keys if values.get(k) is not None}


async def execute_run(run_id: str, resume: dict[str, Any] | None = None, *, inline: bool = False) -> str:
    async with session_scope() as s:
        run = await s.get(Run, run_id)
        if run is None:
            log.warning("run %s not found", run_id)
            return "missing"
        if run.status in (RunStatus.done, RunStatus.cancelled):
            return run.status
        if run.status == RunStatus.waiting and resume is None:
            return run.status
        run.status = RunStatus.running
        run.started_at = run.started_at or datetime.now(UTC)
        run.attempts = (run.attempts or 0) + 1
        run.waiting_for = None
        run.error = None
        snapshot = Run(**{c.name: getattr(run, c.name) for c in Run.__table__.columns})
    run = snapshot
    cfg = await get_service_config()
    tracing.set_enabled(cfg.langfuse_enabled)
    ctx = await _context_for(run)
    token = set_run(ctx)
    graph = await graph_for(run.kind, ctx.channel_type)
    config = {"configurable": {"thread_id": run.id}, "recursion_limit": 120}
    if resume is not None:
        inp: Any = Command(resume=resume)
    else:
        existing = await graph.aget_state(config)
        inp = None if existing and existing.next else {**run.input, "run_id": run.id}
    status, error = RunStatus.done, None
    waiting: dict[str, Any] | None = None
    if run.channel_id:
        await notify_channel(run.channel_id, {"type": "run_status", "run_id": run.id, "status": RunStatus.running})
    await emit("run_start", {"kind": run.kind, "title": run.title, "resume": resume, "attempt": run.attempts})
    try:
        async with tracing.trace_run(f"{run.kind}: {run.title}", run_id=run.id, channel_id=run.channel_id, kind=run.kind, input=run.input if resume is None else resume) as obs:
            async for chunk in graph.astream(inp, config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    intr = chunk["__interrupt__"]
                    waiting = intr[0].value if intr else {}
            final = await graph.aget_state(config)
            values = final.values or {}
            if final.next and waiting is not None:
                status = RunStatus.waiting
            obs.update(output=_result_summary(values))
        result = _result_summary(values)
        await _set(
            run.id,
            status=status,
            waiting_for=waiting if status == RunStatus.waiting else None,
            result=result,
            finished_at=datetime.now(UTC) if status == RunStatus.done else None,
            current_node=None if status == RunStatus.done else run.current_node,
            current_label="Ожидание решения владельца" if status == RunStatus.waiting else None,
            post_id=values.get("post_id") or run.post_id,
        )
    except LLMUnavailable as exc:
        error = str(exc)
        if inline or run.attempts >= MAX_DEFERS:
            status = RunStatus.failed
            await _set(run.id, status=status, error=error, finished_at=datetime.now(UTC))
        else:
            status = RunStatus.deferred
            delay = DEFER_STEPS[min(run.attempts - 1, len(DEFER_STEPS) - 1)]
            await _set(run.id, status=status, error=error, next_attempt_at=datetime.now(UTC) + timedelta(minutes=delay))
        await _on_problem(run, status, error)
    except BudgetExceeded as exc:
        status, error = RunStatus.failed, str(exc)
        await _set(run.id, status=status, error=error, finished_at=datetime.now(UTC))
        await _on_problem(run, status, error)
    except RunCancelled as exc:
        status, error = RunStatus.cancelled, str(exc)
        await _set(run.id, status=status, error=error, finished_at=datetime.now(UTC))
        await _on_problem(run, status, error)
    except asyncio.CancelledError:
        if inline:
            status, error = RunStatus.failed, "Запуск не уложился в отведённое время"
            await _set(run.id, status=status, error=error, finished_at=datetime.now(UTC))
        else:
            status, error = "interrupted", "Запуск прерван"
        raise
    except (BadOutput, Exception) as exc:
        log.exception("run %s failed", run.id)
        status, error = RunStatus.failed, f"{type(exc).__name__}: {exc}"
        await _set(run.id, status=status, error=error[:4000], finished_at=datetime.now(UTC))
        await _on_problem(run, status, error)
    finally:
        await emit("run_end", {"status": status, "error": error, "waiting": waiting})
        tracing.flush()
        reset_run(token)
    if run.channel_id:
        await notify_channel(run.channel_id, {"type": "run_status", "run_id": run.id, "status": status})
    return status
