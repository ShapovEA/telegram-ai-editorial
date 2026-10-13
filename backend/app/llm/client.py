import asyncio
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import jiter
from sqlalchemy import func, select, update

from app.config import get_settings
from app.db.models import LlmCall, Run
from app.db.session import session_scope
from app.llm import catalog
from app.observability import tracing
from app.runtime.context import current_node, current_run
from app.runtime.events import emit, publish_live

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


class BudgetExceeded(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ChatResult:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    generation_id: str | None = None
    finish_reason: str | None = None


_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        s = get_settings()
        _http = httpx.AsyncClient(
            base_url=s.openrouter_base_url,
            timeout=httpx.Timeout(s.llm_timeout_seconds, connect=20.0),
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": s.app_public_url,
                "X-Title": s.openrouter_app_name,
            },
        )
    return _http


def _with_cache_control(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m.get("role") == "system" and isinstance(m.get("content"), str):
            out.append({"role": "system", "content": [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]})
        else:
            out.append(m)
    return out


async def check_budget() -> None:
    ctx = current_run()
    if not ctx.channel_id or not ctx.budget_usd:
        return
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with session_scope() as s:
        spent = (
            await s.execute(
                select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
                    LlmCall.channel_id == ctx.channel_id, LlmCall.created_at >= month_start
                )
            )
        ).scalar_one()
    if float(spent) >= ctx.budget_usd:
        raise BudgetExceeded(f"Месячный бюджет канала исчерпан: ${float(spent):.2f} из ${ctx.budget_usd:.2f}")


def _partial_field(raw: str, field_name: str) -> str | None:
    if not raw:
        return None
    try:
        data = jiter.from_json(raw.encode(), partial_mode="trailing-strings")
    except Exception:
        return None
    if isinstance(data, dict):
        value = data.get(field_name)
        if isinstance(value, str):
            return value
    return None


async def _record(role: str, model_requested: str, result: ChatResult, status: str, error: str | None) -> None:
    ctx = current_run()
    try:
        async with session_scope() as s:
            s.add(
                LlmCall(
                    run_id=ctx.run_id,
                    channel_id=ctx.channel_id,
                    post_id=ctx.post_id,
                    node=current_node(),
                    role=role,
                    model_requested=model_requested,
                    model_used=result.model_used or None,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    reasoning_tokens=result.reasoning_tokens,
                    cached_tokens=result.cached_tokens,
                    cost_usd=Decimal(str(round(result.cost, 8))),
                    latency_ms=result.latency_ms,
                    status=status,
                    error=error,
                    generation_id=result.generation_id,
                )
            )
            if ctx.run_id and result.cost:
                await s.execute(
                    update(Run).where(Run.id == ctx.run_id).values(cost_usd=Run.cost_usd + Decimal(str(round(result.cost, 8))))
                )
    except Exception:
        log.warning("llm call record failed", exc_info=True)


async def _stream_once(body: dict[str, Any], call_id: str, live_field: str | None) -> ChatResult:
    result = ChatResult()
    started = time.monotonic()
    tool_parts: dict[int, dict[str, str]] = {}
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    last_live = 0.0
    async with _client().stream("POST", "/chat/completions", json=body) as resp:
        if resp.status_code != 200:
            text = (await resp.aread()).decode(errors="replace")[:1000]
            raise _status_error(resp.status_code, text)
        async for line in resp.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if "error" in chunk:
                err = chunk["error"] or {}
                code = err.get("code")
                raise _status_error(int(code) if isinstance(code, int) else 502, str(err.get("message", err)))
            result.generation_id = result.generation_id or chunk.get("id")
            if chunk.get("model"):
                result.model_used = chunk["model"]
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    content_parts.append(delta["content"])
                if delta.get("reasoning"):
                    reasoning_parts.append(delta["reasoning"])
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    part = tool_parts.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        part["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        part["name"] = fn["name"]
                    if fn.get("arguments"):
                        part["arguments"] += fn["arguments"]
                if choice.get("finish_reason"):
                    result.finish_reason = choice["finish_reason"]
            usage = chunk.get("usage")
            if usage:
                result.prompt_tokens = int(usage.get("prompt_tokens") or 0)
                result.completion_tokens = int(usage.get("completion_tokens") or 0)
                result.cost = float(usage.get("cost") or 0.0)
                result.cached_tokens = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                result.reasoning_tokens = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
            now = time.monotonic()
            if now - last_live > 0.25:
                live_text = None
                if live_field and tool_parts:
                    live_text = _partial_field(next(iter(tool_parts.values()))["arguments"], live_field)
                elif content_parts and not tool_parts:
                    live_text = "".join(content_parts)
                if live_text or reasoning_parts:
                    last_live = now
                    await publish_live(
                        {
                            "type": "llm_delta",
                            "node": current_node(),
                            "data": {"call_id": call_id, "text": live_text or "", "reasoning": "".join(reasoning_parts)[-1500:]},
                        }
                    )
    result.content = "".join(content_parts)
    result.reasoning = "".join(reasoning_parts)
    result.tool_calls = [
        ToolCall(id=p["id"] or f"call_{i}", name=p["name"], arguments=p["arguments"] or "{}")
        for i, p in sorted(tool_parts.items())
        if p["name"]
    ]
    result.latency_ms = int((time.monotonic() - started) * 1000)
    return result


class _HttpStatusError(LLMError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def _status_error(status: int, text: str) -> LLMError:
    if status in (401, 403):
        return LLMUnavailable(f"OpenRouter отклонил ключ ({status}): {text}")
    if status == 402:
        return LLMUnavailable(f"На счёте OpenRouter недостаточно средств: {text}")
    return _HttpStatusError(status, text)


async def chat(
    role: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    live_field: str | None = None,
    max_tokens: int | None = None,
    label: str | None = None,
) -> ChatResult:
    await check_budget()
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise LLMUnavailable("Не задан OPENROUTER_API_KEY")
    ctx = current_run()
    rm = ctx.model_for(role)
    model_info = await catalog.get_model(rm.model)
    body: dict[str, Any] = {
        "model": rm.model,
        "messages": _with_cache_control(messages) if rm.model.startswith("anthropic/") else messages,
        "stream": True,
        "usage": {"include": True},
    }
    if rm.fallbacks:
        body["models"] = [rm.model, *[m for m in rm.fallbacks if m != rm.model]]
    reasoning = catalog.reasoning_param(model_info, rm.reasoning)
    if reasoning:
        body["reasoning"] = reasoning
    if rm.temperature is not None and (not reasoning or reasoning.get("effort") == "none"):
        body["temperature"] = rm.temperature
    if tools:
        body["tools"] = tools
    if max_tokens:
        body["max_tokens"] = max_tokens

    call_id = uuid.uuid4().hex[:12]
    await emit(
        "llm_start",
        {"call_id": call_id, "role": role, "model": rm.model, "label": label, "reasoning": (reasoning or {}).get("effort")},
        persist=False,
    )
    attempt = 0
    last_error: Exception | None = None
    with tracing.observe(
        f"llm:{role}",
        as_type="generation",
        model=rm.model,
        input=messages,
        model_parameters={k: v for k, v in {"temperature": body.get("temperature"), "reasoning": (reasoning or {}).get("effort")}.items() if v is not None},
    ) as obs:
        while attempt <= settings.llm_max_retries:
            attempt += 1
            try:
                result = await _stream_once(body, call_id, live_field)
                if not result.cost and model_info:
                    used = await catalog.get_model(result.model_used) if result.model_used else model_info
                    result.cost = catalog.estimate_cost(used or model_info, result.prompt_tokens, result.completion_tokens)
                await _record(role, rm.model, result, "ok", None)
                obs.update(
                    output={"content": result.content, "tool_calls": [{"name": t.name, "arguments": t.arguments} for t in result.tool_calls]},
                    model=result.model_used or rm.model,
                    usage_details={"input": result.prompt_tokens, "output": result.completion_tokens, "reasoning": result.reasoning_tokens, "cached": result.cached_tokens},
                    cost_details={"total": result.cost},
                    metadata={"latency_ms": result.latency_ms, "fallback_used": bool(result.model_used and result.model_used != rm.model)},
                )
                await emit(
                    "llm_call",
                    {
                        "call_id": call_id,
                        "role": role,
                        "label": label,
                        "model": rm.model,
                        "model_used": result.model_used,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "reasoning_tokens": result.reasoning_tokens,
                        "cached_tokens": result.cached_tokens,
                        "cost": round(result.cost, 6),
                        "latency_ms": result.latency_ms,
                        "reasoning": result.reasoning[:4000],
                        "attempt": attempt,
                    },
                )
                return result
            except LLMUnavailable as exc:
                await _record(role, rm.model, ChatResult(), "error", str(exc))
                raise
            except (_HttpStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                status = getattr(exc, "status", None)
                retryable = status is None or status in RETRYABLE_STATUS
                await emit("llm_retry", {"call_id": call_id, "role": role, "attempt": attempt, "error": str(exc)[:500], "retryable": retryable})
                if not retryable:
                    await _record(role, rm.model, ChatResult(), "error", str(exc))
                    raise LLMError(str(exc)) from exc
                if attempt > settings.llm_max_retries:
                    break
                delay = min(30.0, 1.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
    await _record(role, rm.model, ChatResult(), "error", str(last_error))
    raise LLMUnavailable(f"OpenRouter недоступен после {attempt} попыток: {last_error}")
