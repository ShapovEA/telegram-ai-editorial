import asyncio
import logging
from typing import Any

from app.worker.broker import broker

log = logging.getLogger(__name__)


@broker.task(task_name="run_graph", timeout=3600)
async def run_graph(run_id: str, resume: dict[str, Any] | None = None) -> str:
    from app.graphs.runner import execute_run
    from app.runtime.redis import owned_lock

    async with owned_lock(f"run:lock:{run_id}") as acquired:
        if acquired:
            return await execute_run(run_id, resume)
    if resume is not None:
        await asyncio.sleep(10)
        await run_graph.kiq(run_id, resume)
    return "busy"


@broker.task(task_name="fetch_feed", timeout=600)
async def fetch_feed(source_id: int) -> dict:
    from app.services.feeds import fetch_source

    return await fetch_source(source_id)


@broker.task(task_name="publish_post", timeout=300)
async def publish_post(post_id: int) -> str:
    from app.services.publishing import publish_post as do_publish

    return await do_publish(post_id)


async def kick_runs(run_ids: list[str], resume: dict[str, Any] | None = None) -> None:
    for rid in run_ids:
        await run_graph.kiq(rid, resume)


@broker.task(task_name="tick", schedule=[{"cron": "* * * * *"}])
async def tick() -> dict:
    from app.services import jobs, publishing

    out: dict[str, int] = {}
    for post_id in await publishing.due_posts():
        await publish_post.kiq(post_id)
        out["publish"] = out.get("publish", 0) + 1
    out["news_slots"] = await jobs.ensure_news_slots()
    await kick_runs(await jobs.ensure_plans())
    started = await jobs.start_due_slots()
    await kick_runs(started)
    out["started"] = len(started)
    await kick_runs(await jobs.plans_to_auto_approve(), {"action": "auto_approve"})
    await kick_runs(await jobs.approvals_to_expire(), {"action": "expire"})
    await kick_runs(await jobs.deferred_runs())
    await kick_runs(await jobs.stale_queued_runs())
    return out


@broker.task(task_name="feeds_tick", schedule=[{"cron": "*/5 * * * *"}])
async def feeds_tick() -> int:
    from app.services.feeds import due_sources

    ids = await due_sources()
    for sid in ids:
        await fetch_feed.kiq(sid)
    return len(ids)


@broker.task(task_name="sync_models", schedule=[{"cron": "17 3 * * *"}])
async def sync_models() -> int:
    from app.llm.catalog import sync_catalog

    return await sync_catalog()


@broker.task(task_name="weekly_rules", schedule=[{"cron": "30 4 * * 1"}])
async def weekly_rules() -> int:
    from app.services.jobs import channels_for_rules

    ids = await channels_for_rules()
    await kick_runs(ids)
    return len(ids)


@broker.task(task_name="monthly_analytics", schedule=[{"cron": "0 6 1 * *"}])
async def monthly_analytics() -> int:
    from app.services.jobs import channels_for_analytics

    ids = await channels_for_analytics()
    await kick_runs(ids)
    return len(ids)
