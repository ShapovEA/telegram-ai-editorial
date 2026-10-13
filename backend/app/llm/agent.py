import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.client import ChatResult, LLMError, chat
from app.observability import tracing
from app.runtime.events import emit

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

TOOL_RESULT_LIMIT = 14000


class BadOutput(LLMError):
    pass


def _clean_schema(node: Any, in_properties: bool = False, defs: dict[str, Any] | None = None) -> Any:
    if isinstance(node, list):
        return [_clean_schema(x, False, defs) for x in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node and defs is not None:
        ref = node["$ref"].split("/")[-1]
        merged = dict(defs.get(ref, {}))
        merged.update({k: v for k, v in node.items() if k != "$ref"})
        return _clean_schema(merged, False, defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if in_properties:
            out[key] = _clean_schema(value, False, defs)
            continue
        if key in ("title", "$defs"):
            continue
        if key == "properties":
            out[key] = _clean_schema(value, True, defs)
        else:
            out[key] = _clean_schema(value, False, defs)
    return out


def tool_spec(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    params = _clean_schema(schema, False, defs)
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: type[BaseModel]
    handler: Callable[[Any], Awaitable[str]]
    label: Callable[[Any], str] | None = None


def _parse(raw: str, schema: type[T]) -> T:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise BadOutput(f"Аргументы не являются корректным JSON: {exc}") from exc
    if isinstance(data, dict) and len(data) == 1 and isinstance(next(iter(data.values())), dict):
        only = next(iter(data.values()))
        if set(schema.model_fields) & set(only) and not set(schema.model_fields) & set(data):
            data = only
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise BadOutput(_short_errors(exc)) from exc


def _short_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:8]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts)


def _assistant_message(result: ChatResult) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": result.content or ""}
    if result.tool_calls:
        msg["tool_calls"] = [
            {"id": t.id, "type": "function", "function": {"name": t.name, "arguments": t.arguments}} for t in result.tool_calls
        ]
    return msg


def _content_json(content: str) -> str | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    return text[start : end + 1]


async def ask(
    role: str,
    system: str,
    user: str,
    schema: type[T],
    *,
    answer_name: str = "answer",
    answer_description: str = "Итоговый ответ строго по схеме",
    live_field: str | None = None,
    label: str | None = None,
    max_fix: int = 2,
    history: list[dict[str, Any]] | None = None,
) -> T:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": user}]
    tools = [tool_spec(answer_name, answer_description, schema)]
    last_error = ""
    for attempt in range(max_fix + 1):
        result = await chat(role, messages, tools=tools, live_field=live_field, label=label)
        call = next((t for t in result.tool_calls if t.name == answer_name), None)
        raw = call.arguments if call else _content_json(result.content)
        try:
            if raw is None:
                raise BadOutput("Ответ без вызова инструмента answer")
            return _parse(raw, schema)
        except BadOutput as exc:
            last_error = str(exc)
            await emit("schema_retry", {"role": role, "attempt": attempt + 1, "error": last_error[:500], "raw": (raw or result.content or "")[:2000]})
            messages.append(_assistant_message(result))
            if call:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": f"Ошибка: ответ не прошёл проверку схемы. {last_error}. Вызови {answer_name} ещё раз с исправленными полями."})
            else:
                messages.append({"role": "user", "content": f"Ответь только вызовом инструмента {answer_name} строго по схеме. Ошибка: {last_error}"})
    raise BadOutput(f"{role}: ответ не соответствует схеме после {max_fix + 1} попыток: {last_error}")


async def _run_tool(tool: AgentTool, call_id: str, raw_args: str) -> str:
    try:
        args = tool.parameters.model_validate(json.loads(raw_args or "{}"))
    except (json.JSONDecodeError, ValidationError) as exc:
        return f"Ошибка: неверные аргументы инструмента {tool.name}: {exc}"
    label = tool.label(args) if tool.label else tool.name
    await emit("tool_call", {"call_id": call_id, "tool": tool.name, "label": label, "args": args.model_dump()})
    with tracing.observe(f"tool:{tool.name}", as_type="tool", input=args.model_dump()) as obs:
        try:
            output = await tool.handler(args)
        except Exception as exc:
            log.warning("tool %s failed", tool.name, exc_info=True)
            output = f"Ошибка инструмента {tool.name}: {exc}"
        obs.update(output=output[:4000])
    if len(output) > TOOL_RESULT_LIMIT:
        output = output[:TOOL_RESULT_LIMIT] + "\n[...обрезано...]"
    await emit("tool_result", {"call_id": call_id, "tool": tool.name, "label": label, "preview": output[:1500], "size": len(output)})
    return output


async def run_agent(
    role: str,
    system: str,
    user: str,
    tools: list[AgentTool],
    final_schema: type[T],
    *,
    final_name: str = "report",
    final_description: str = "Итоговый результат работы",
    max_steps: int = 8,
    live_field: str | None = None,
    label: str | None = None,
) -> T:
    by_name = {t.name: t for t in tools}
    specs = [tool_spec(t.name, t.description, t.parameters) for t in tools]
    specs.append(tool_spec(final_name, final_description, final_schema))
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    fixes = 0
    steps = 0
    while True:
        steps += 1
        forced = steps > max_steps
        if forced:
            messages.append({"role": "user", "content": f"Лимит шагов исчерпан. Сейчас же верни итог инструментом {final_name} по тому, что уже найдено."})
        result = await chat(
            role,
            messages,
            tools=[specs[-1]] if forced else specs,
            live_field=live_field,
            label=label,
        )
        messages.append(_assistant_message(result))
        if not result.tool_calls:
            raw = _content_json(result.content)
            if raw:
                try:
                    return _parse(raw, final_schema)
                except BadOutput:
                    pass
            fixes += 1
            if fixes > 2:
                raise BadOutput(f"{role}: агент не вызвал инструменты")
            messages.append({"role": "user", "content": f"Используй инструменты. Итог верни вызовом {final_name}."})
            continue
        final_call = next((t for t in result.tool_calls if t.name == final_name), None)
        other_calls = [t for t in result.tool_calls if t.name != final_name]
        outputs = await asyncio.gather(
            *[
                _run_tool(by_name[t.name], t.id, t.arguments) if t.name in by_name else _unknown(t.name)
                for t in other_calls
            ]
        )
        for call, output in zip(other_calls, outputs, strict=True):
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
        if final_call:
            try:
                return _parse(final_call.arguments, final_schema)
            except BadOutput as exc:
                fixes += 1
                await emit("schema_retry", {"role": role, "attempt": fixes, "error": str(exc)[:500], "raw": final_call.arguments[:2000]})
                messages.append({"role": "tool", "tool_call_id": final_call.id, "content": f"Ошибка: {exc}. Вызови {final_name} ещё раз с исправленными полями."})
                if fixes > 2:
                    raise
        if steps > max_steps + 2:
            raise BadOutput(f"{role}: агент не завершил работу")


async def _unknown(name: str) -> str:
    return f"Ошибка: инструмента {name} нет"
