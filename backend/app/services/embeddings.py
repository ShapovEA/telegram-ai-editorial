import logging
import math

import httpx

from app.config import get_settings
from app.observability import tracing

log = logging.getLogger(__name__)

MAX_CHARS = 6000


class EmbeddingError(Exception):
    pass


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    s = get_settings()
    payload = {"model": s.embedding_model, "input": [t[:MAX_CHARS] for t in texts], "truncate": True}
    with tracing.observe("embed", as_type="embedding", model=s.embedding_model, input={"count": len(texts)}):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{s.ollama_url}/api/embed", json=payload)
                resp.raise_for_status()
                vectors = resp.json()["embeddings"]
        except Exception as exc:
            raise EmbeddingError(f"Ollama недоступна: {exc}") from exc
    return [_normalize(v) for v in vectors]


async def embed_one(text: str) -> list[float]:
    return (await embed([text]))[0]


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))
