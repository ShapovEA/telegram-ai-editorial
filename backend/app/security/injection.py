import hashlib
import logging
import re

from pydantic import BaseModel

from app.llm.agent import ask
from app.prompts import closed
from app.runtime.events import emit
from app.runtime.redis import get_redis

log = logging.getLogger(__name__)

HEURISTICS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions|prompts|messages)",
    r"disregard\s+(all\s+|the\s+)?(previous|prior|above)",
    r"you\s+are\s+now\s+(a|an|the)\b",
    r"(system|developer)\s*prompt",
    r"\bas\s+an?\s+(ai|language model|assistant)\b.*\b(must|should)\b",
    r"(игнорируй|забудь|отмени)\s+(все\s+)?(предыдущие|прошлые|прежние|свои)\s+(инструкции|указания|правила)",
    r"(ты|вы)\s+(теперь|отныне)\s+(—\s*)?(ии|бот|ассистент|модель)",
    r"(инструкция|указание|сообщение)\s+для\s+(ии|нейросети|модели|ассистента|бота|llm|gpt)",
    r"(нейросеть|модель|ассистент|бот|chatgpt|claude|gpt),?\s+(добавь|вставь|напиши|упомяни|поставь)\b",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
    r"\[\s*(system|inst)\s*\]",
    r"(add|insert|include)\s+(this|the following)\s+(link|url|text)\s+(to|in)\s+(your|the)\s+(answer|response|output)",
]
HEUR_RE = [re.compile(p, re.IGNORECASE) for p in HEURISTICS]
HIDDEN_RE = re.compile(r"[​-‏⁠-⁤﻿]{3,}")
CACHE_TTL = 7 * 24 * 3600
CHUNK = 6000


class GuardVerdict(BaseModel):
    injection: bool
    reason: str = ""


def heuristic(text: str) -> str | None:
    for rx in HEUR_RE:
        m = rx.search(text)
        if m:
            return f"эвристика: «{m.group(0)[:80]}»"
    if HIDDEN_RE.search(text):
        return "эвристика: скрытые символы"
    return None


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


async def check(text: str, *, source: str = "") -> GuardVerdict:
    text = (text or "").strip()
    if not text:
        return GuardVerdict(injection=False, reason="пусто")
    h = text_hash(text)
    redis = get_redis()
    key = f"guard:{h}"
    try:
        cached = await redis.get(key)
    except Exception:
        cached = None
    if cached:
        return GuardVerdict.model_validate_json(cached)
    reason = heuristic(text)
    if reason:
        verdict = GuardVerdict(injection=True, reason=reason)
    else:
        verdict = GuardVerdict(injection=False, reason="")
        for start in range(0, min(len(text), CHUNK * 3), CHUNK):
            chunk = text[start : start + CHUNK]
            v = await ask(
                "guard",
                closed.GUARD,
                f"<data>\n{chunk}\n</data>",
                GuardVerdict,
                label=f"Проверка на инъекции: {source[:80]}" if source else "Проверка на инъекции",
            )
            if v.injection:
                verdict = v
                break
    try:
        await redis.set(key, verdict.model_dump_json(), ex=CACHE_TTL)
    except Exception:
        pass
    await emit("guard", {"source": source[:300], "injection": verdict.injection, "reason": verdict.reason[:300]})
    return verdict
