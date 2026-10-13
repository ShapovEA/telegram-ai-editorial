import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update

from app.db.models import Run, RunEvent
from app.db.session import session_scope
from app.runtime.context import current_node, current_run
from app.runtime.redis import channel_feed, get_redis, run_channel

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def publish_live(payload: dict[str, Any]) -> None:
    ctx = current_run()
    if not ctx.run_id:
        return
    try:
        await get_redis().publish(run_channel(ctx.run_id), json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        log.debug("live publish failed", exc_info=True)


async def emit(event_type: str, data: dict[str, Any] | None = None, *, node: str | None = None, persist: bool = True) -> None:
    ctx = current_run()
    if not ctx.run_id:
        return
    node = node or current_node()
    payload = {"type": event_type, "node": node, "data": data or {}, "ts": _now()}
    if persist:
        ctx.seq += 1
        payload["seq"] = ctx.seq
        try:
            async with session_scope() as s:
                s.add(RunEvent(run_id=ctx.run_id, seq=ctx.seq, type=event_type, node=node, data=data or {}))
        except Exception:
            log.warning("run event persist failed", exc_info=True)
    await publish_live(payload)


async def set_run_progress(node: str | None, label: str | None) -> None:
    ctx = current_run()
    if not ctx.run_id:
        return
    async with session_scope() as s:
        await s.execute(update(Run).where(Run.id == ctx.run_id).values(current_node=node, current_label=label))
    if ctx.channel_id:
        await notify_channel(ctx.channel_id, {"type": "run_progress", "run_id": ctx.run_id, "node": node, "label": label})


async def notify_channel(channel_id: int, payload: dict[str, Any]) -> None:
    try:
        await get_redis().publish(channel_feed(channel_id), json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        log.debug("channel publish failed", exc_info=True)
