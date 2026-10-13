import logging

from taskiq import TaskiqEvents, TaskiqScheduler, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisStreamBroker

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

broker = RedisStreamBroker(url=get_settings().redis_url, queue_name="smm-tasks")
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState) -> None:
    from app.graphs.checkpointer import get_checkpointer
    from app.services.service_settings import ensure_service_settings

    await ensure_service_settings()
    await get_checkpointer()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState) -> None:
    from app.graphs.checkpointer import close_checkpointer

    await close_checkpointer()
