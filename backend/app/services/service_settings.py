import time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import ServiceSettings
from app.db.session import session_scope
from app.domain.schemas import DEFAULT_ROLE_MODELS, RoleModel


class ServiceConfig(BaseModel):
    langfuse_enabled: bool = False
    default_models: dict[str, RoleModel] = Field(default_factory=lambda: dict(DEFAULT_ROLE_MODELS))
    extra_stamps: list[str] = Field(default_factory=list)
    latin_whitelist: list[str] = Field(default_factory=list)


_cache: tuple[float, ServiceConfig] | None = None
_TTL = 10.0


async def get_service_config(force: bool = False) -> ServiceConfig:
    global _cache
    now = time.monotonic()
    if not force and _cache and now - _cache[0] < _TTL:
        return _cache[1]
    async with session_scope() as s:
        row = await s.get(ServiceSettings, 1)
        data: dict[str, Any] = row.data if row else {}
    cfg = ServiceConfig.model_validate(data)
    merged = dict(DEFAULT_ROLE_MODELS)
    merged.update(cfg.default_models)
    cfg.default_models = merged
    _cache = (now, cfg)
    return cfg


async def save_service_config(cfg: ServiceConfig) -> ServiceConfig:
    global _cache
    async with session_scope() as s:
        row = await s.get(ServiceSettings, 1)
        if row is None:
            row = ServiceSettings(id=1, data={})
            s.add(row)
        row.data = cfg.model_dump(mode="json")
    _cache = None
    return await get_service_config(force=True)


async def ensure_service_settings() -> None:
    async with session_scope() as s:
        exists = (await s.execute(select(ServiceSettings.id).where(ServiceSettings.id == 1))).scalar_one_or_none()
        if exists is None:
            s.add(ServiceSettings(id=1, data=ServiceConfig().model_dump(mode="json")))
