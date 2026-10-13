import logging
import time
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db.models import ModelInfo
from app.db.session import session_scope

log = logging.getLogger(__name__)

EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]

_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
_TTL = 300.0


async def sync_catalog() -> int:
    s = get_settings()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{s.openrouter_base_url}/models")
        resp.raise_for_status()
        items = resp.json().get("data", [])
    rows = []
    for m in items:
        pricing = m.get("pricing") or {}
        params = m.get("supported_parameters") or []
        rows.append(
            {
                "id": m["id"],
                "name": m.get("name") or m["id"],
                "context_length": int(m.get("context_length") or 0),
                "prompt_price": Decimal(str(pricing.get("prompt") or 0)),
                "completion_price": Decimal(str(pricing.get("completion") or 0)),
                "supports_tools": "tools" in params,
                "reasoning": m.get("reasoning"),
                "raw": {
                    "description": (m.get("description") or "")[:2000],
                    "supported_parameters": params,
                    "pricing": pricing,
                    "created": m.get("created"),
                },
            }
        )
    if not rows:
        return 0
    async with session_scope() as session:
        for chunk_start in range(0, len(rows), 200):
            chunk = rows[chunk_start : chunk_start + 200]
            stmt = insert(ModelInfo).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ModelInfo.id],
                set_={c: stmt.excluded[c] for c in ("name", "context_length", "prompt_price", "completion_price", "supports_tools", "reasoning", "raw")},
            )
            await session.execute(stmt)
    invalidate()
    return len(rows)


def invalidate() -> None:
    global _cache
    _cache = None


async def get_catalog() -> dict[str, dict[str, Any]]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _TTL:
        return _cache[1]
    async with session_scope() as session:
        rows = (await session.execute(select(ModelInfo))).scalars().all()
    data = {
        r.id: {
            "id": r.id,
            "name": r.name,
            "context_length": r.context_length,
            "prompt_price": float(r.prompt_price),
            "completion_price": float(r.completion_price),
            "supports_tools": r.supports_tools,
            "reasoning": r.reasoning,
        }
        for r in rows
    }
    _cache = (now, data)
    return data


async def get_model(model_id: str) -> dict[str, Any] | None:
    return (await get_catalog()).get(model_id)


def reasoning_param(model: dict[str, Any] | None, requested: str) -> dict[str, Any] | None:
    if model is None:
        return {"effort": "none"} if requested == "none" else {"effort": requested}
    info = model.get("reasoning")
    if not info:
        return None
    supported = [e for e in (info.get("supported_efforts") or []) if e in EFFORT_ORDER]
    mandatory = bool(info.get("mandatory"))
    if requested == "none":
        if not mandatory:
            return {"effort": "none"}
        if supported:
            return {"effort": min(supported, key=EFFORT_ORDER.index)}
        return None
    if supported and requested not in supported:
        higher = [e for e in supported if EFFORT_ORDER.index(e) >= EFFORT_ORDER.index(requested)]
        effort = min(higher, key=EFFORT_ORDER.index) if higher else max(supported, key=EFFORT_ORDER.index)
        return {"effort": effort}
    return {"effort": requested}


def estimate_cost(model: dict[str, Any] | None, prompt_tokens: int, completion_tokens: int) -> float:
    if not model:
        return 0.0
    return prompt_tokens * model["prompt_price"] + completion_tokens * model["completion_price"]
