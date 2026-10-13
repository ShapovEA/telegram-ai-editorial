import logging
from typing import Any

from app.agents.schemas import SameEvent, Verdicts
from app.llm.agent import ask
from app.prompts import closed
from app.services.embeddings import embed_one
from app.services.posts_index import similar_posts

log = logging.getLogger(__name__)

POST_SAME = 0.86
POST_GRAY = 0.70
STORY_SAME = 0.85
STORY_GRAY = 0.72


async def judge_against_posts(topic: str, posts: list[dict[str, Any]]) -> dict[int, str]:
    if not posts:
        return {}
    listing = "\n".join(f"[{i}] {p['date']} «{p['title']}»: {p.get('key_idea') or p.get('excerpt', '')[:300]}" for i, p in enumerate(posts, 1))
    user = f"НОВАЯ ТЕМА:\n<data>\n{topic}\n</data>\n\nОПУБЛИКОВАННЫЕ ПОСТЫ:\n<data>\n{listing}\n</data>"
    answer = await ask("novelty", closed.NOVELTY, user, Verdicts, label="Проверка новизны")
    out = {}
    for item in answer.items:
        if 1 <= item.post <= len(posts):
            out[posts[item.post - 1]["id"]] = item.verdict
    return out


async def classify_topic(channel_id: int, topic: str, *, vector: list[float] | None = None, days: int = 60) -> dict[str, Any]:
    vector = vector or await embed_one(topic)
    similar = await similar_posts(channel_id, vector, limit=5, days=days)
    if not similar:
        return {"verdict": "new", "post": None, "similarity": 0.0}
    top = similar[0]
    if top["similarity"] >= POST_SAME:
        return {"verdict": "same", "post": top, "similarity": top["similarity"]}
    gray = [p for p in similar if p["similarity"] >= POST_GRAY]
    if not gray:
        return {"verdict": "new", "post": None, "similarity": top["similarity"]}
    verdicts = await judge_against_posts(topic, gray)
    for p in gray:
        if verdicts.get(p["id"]) == "same":
            return {"verdict": "same", "post": p, "similarity": p["similarity"]}
    for p in gray:
        if verdicts.get(p["id"]) == "development":
            return {"verdict": "development", "post": p, "similarity": p["similarity"]}
    return {"verdict": "new", "post": None, "similarity": top["similarity"]}


async def related_post_for_vector(channel_id: int, vector: list[float], topic: str) -> dict[str, Any] | None:
    result = await classify_topic(channel_id, topic, vector=vector)
    if result["verdict"] in ("development", "same"):
        return result["post"]
    return None


async def same_event(a: str, b: str) -> bool:
    user = f"НОВОСТЬ 1:\n<data>\n{a[:1500]}\n</data>\n\nНОВОСТЬ 2:\n<data>\n{b[:1500]}\n</data>"
    answer = await ask("novelty", closed.CLUSTER, user, SameEvent, label="Одно ли это событие")
    return answer.same_event
