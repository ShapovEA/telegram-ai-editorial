import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import auth, channels, costs, planning, posts, runs, service, sources
from app.config import get_settings
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.graphs.checkpointer import close_checkpointer, get_checkpointer
    from app.llm.catalog import get_catalog, sync_catalog
    from app.observability import tracing
    from app.services.service_settings import ensure_service_settings, get_service_config
    from app.worker.broker import broker

    await ensure_service_settings()
    tracing.set_enabled((await get_service_config()).langfuse_enabled)
    await get_checkpointer()
    if not broker.is_worker_process:
        await broker.startup()
    try:
        if not await get_catalog():
            log.info("model catalog synced: %s", await sync_catalog())
    except Exception:
        log.warning("model catalog sync failed", exc_info=True)
    yield
    if not broker.is_worker_process:
        await broker.shutdown()
    await close_checkpointer()


app = FastAPI(title="AI SMM Department", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url, "http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, channels, sources, planning, posts, runs, costs, service):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"ok": True}
