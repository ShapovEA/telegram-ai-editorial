import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import current_user, owned_channel
from app.api.serializers import event_out, run_out
from app.api.utils import kick
from app.db.models import LlmCall, Run, RunEvent, User
from app.db.session import get_session, session_scope
from app.domain.enums import RunStatus
from app.graphs.common import NODE_LABELS, cancel_key
from app.graphs.runner import graph_for
from app.runtime.redis import channel_feed, get_redis, run_channel
from app.services import jobs

router = APIRouter(tags=["runs"])

FINAL = {RunStatus.done, RunStatus.failed, RunStatus.cancelled}


async def _run(session: AsyncSession, run_id: str, user: User) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Запуск не найден")
    if run.channel_id:
        await owned_channel(run.channel_id, user, session)
    return run


@router.get("/channels/{channel_id}/runs")
async def list_runs(channel_id: int, kind: str | None = None, status: str | None = None, limit: int = 50, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    ch = await owned_channel(channel_id, user, session)
    q = select(Run).where(Run.channel_id == ch.id)
    if kind:
        q = q.where(Run.kind == kind)
    if status:
        q = q.where(Run.status.in_(status.split(",")))
    rows = (await session.execute(q.order_by(Run.created_at.desc()).limit(min(limit, 200)))).scalars().all()
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    run = await _run(session, run_id, user)
    events = (await session.execute(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq))).scalars().all()
    calls = (await session.execute(select(LlmCall).where(LlmCall.run_id == run.id).order_by(LlmCall.created_at))).scalars().all()
    return {
        **run_out(run),
        "events": [event_out(e) for e in events],
        "llm": {
            "calls": len(calls),
            "cost": float(sum(c.cost_usd for c in calls)),
            "prompt_tokens": sum(c.prompt_tokens for c in calls),
            "completion_tokens": sum(c.completion_tokens for c in calls),
            "latency_ms": sum(c.latency_ms for c in calls),
        },
    }


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request, since: int = 0, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> EventSourceResponse:
    run = await _run(session, run_id, user)
    run_id = run.id

    async def gen():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(run_channel(run_id))
        last = since
        try:
            async with session_scope() as s:
                events = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > since).order_by(RunEvent.seq))).scalars().all()
                status = (await s.get(Run, run_id)).status
            for e in events:
                last = max(last, e.seq)
                yield {"event": "event", "data": json.dumps(event_out(e), ensure_ascii=False)}
            if status in FINAL:
                yield {"event": "end", "data": status}
                return
            idle = 0
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
                if msg is None:
                    idle += 1
                    yield {"event": "ping", "data": ""}
                    if idle % 3 == 0:
                        async with session_scope() as s:
                            current = (await s.get(Run, run_id)).status
                        if current in FINAL:
                            yield {"event": "end", "data": current}
                            return
                    continue
                idle = 0
                payload = json.loads(msg["data"])
                seq = payload.get("seq")
                if seq is not None and seq <= last:
                    continue
                if seq is not None:
                    last = seq
                yield {"event": "event", "data": msg["data"]}
                if payload.get("type") == "run_end":
                    yield {"event": "end", "data": (payload.get("data") or {}).get("status", "")}
                    return
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return EventSourceResponse(gen())


@router.get("/channels/{channel_id}/events")
async def channel_events(channel_id: int, request: Request, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> EventSourceResponse:
    await owned_channel(channel_id, user, session)

    async def gen():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel_feed(channel_id))
        try:
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield {"event": "ping", "data": ""}
                    continue
                yield {"event": "update", "data": msg["data"]}
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return EventSourceResponse(gen())


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    run = await _run(session, run_id, user)
    if run.status in FINAL:
        return {"status": run.status}
    await get_redis().set(cancel_key(run.id), "1", ex=3600)
    if run.status in (RunStatus.waiting, RunStatus.deferred, RunStatus.queued):
        run.status = RunStatus.cancelled
        run.error = "Остановлен пользователем"
        await session.commit()
    return {"status": "cancelling"}


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    run = await _run(session, run_id, user)
    if run.status not in (RunStatus.failed, RunStatus.deferred):
        raise HTTPException(409, "Повторить можно только запуск, который завершился ошибкой или ждёт повтора")
    await jobs.retry_run(run.id)
    await kick(run.id)
    return {"run_id": run.id}


_graph_cache: dict[str, Any] = {}


@router.get("/graphs/{kind}")
async def graph_structure(kind: str, user: User = Depends(current_user)) -> dict:
    if kind in _graph_cache:
        return _graph_cache[kind]
    try:
        graph = await graph_for(kind)
    except KeyError as exc:
        raise HTTPException(404, "Нет такого графа") from exc
    g = graph.get_graph(xray=1)
    nodes = []
    for node_id in g.nodes:
        if node_id in ("__start__", "__end__") or node_id.endswith(":__start__") or node_id.endswith(":__end__"):
            nodes.append({"id": node_id, "name": node_id.split(":")[-1], "label": "Старт" if "start" in node_id else "Конец", "parent": node_id.split(":")[0] if ":" in node_id else None, "terminal": True})
            continue
        name = node_id.split(":")[-1]
        nodes.append({"id": node_id, "name": name, "label": NODE_LABELS.get(name, name), "parent": node_id.split(":")[0] if ":" in node_id else None, "terminal": False})
    edges = [{"source": e.source, "target": e.target, "conditional": bool(e.conditional)} for e in g.edges]
    data = {"kind": kind, "nodes": nodes, "edges": edges, "groups": {"news_head": "Голова: новости", "smm_head": "Голова: SMM", "production": "Производство поста"}}
    _graph_cache[kind] = data
    return data
