import asyncio
import contextlib
from typing import Any

from app.db.models import Run
from app.db.session import session_scope
from app.graphs.runner import execute_run


async def kick(run_id: str, resume: dict[str, Any] | None = None) -> None:
    from app.worker.tasks import run_graph

    await run_graph.kiq(run_id, resume)


async def run_inline(run_id: str, resume: dict[str, Any] | None = None, timeout: float = 120) -> Run:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(execute_run(run_id, resume, inline=True), timeout=timeout)
    async with session_scope() as s:
        return await s.get(Run, run_id)
