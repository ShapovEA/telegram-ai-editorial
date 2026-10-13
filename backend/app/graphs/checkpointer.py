from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _pool, _saver
    if _saver is not None:
        return _saver
    _pool = AsyncConnectionPool(
        conninfo=get_settings().psycopg_dsn,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open()
    _saver = AsyncPostgresSaver(_pool)
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool = None
    _saver = None
