import json
import logging

from langgraph.graph import END, START, StateGraph

from app.agents.schemas import DRAFT_SCHEMAS, GoalCheckAnswer, PublisherAnswer, ResearchReport, Review
from app.domain.enums import ChannelType
from app.domain.schemas import Styleguide
from app.graphs.common import (
    allowed_urls,
    block,
    calculations_text,
    facts_text,
    join_blocks,
    main_source_url,
    materials,
    node,
    output,
    quote_in,
    system_prompt,
)
from app.graphs.post import render
from app.graphs.post.state import PostState
from app.llm.agent import ask, run_agent
from app.quality.checks import auto_checks, check_numbers, check_publisher, numbers_in, safe_html
from app.runtime.events import emit
from app.tools import agent_tools, media

log = logging.getLogger(__name__)

MAX_RESEARCH_ROUNDS = 2


def _brief_block(brief: dict) -> str:
    lines = [f"Тема: {brief.get('topic', '')}"]
    if brief.get("rubric"):
        lines.append(f"Рубрика: {brief['rubric']}")
    lines.append(f"Формат: {render.FORMAT_NAMES.get(brief.get('format', 'text'), 'пост')}")
    if brief.get("reader_goal"):
        lines.append(f"Цель для читателя: {brief['reader_goal']}")
    if brief.get("key_idea"):
        lines.append(f"Ключевая мысль: {brief['key_idea']}")
    if brief.get("angle"):
        lines.append(f"Подача: {brief['angle']}")
    if brief.get("note"):
        lines.append(f"Примечание: {brief['note']}")
    return "\n".join(lines)


def route_entry(state: PostState) -> str:
    brief = state.get("brief") or {}
    if brief.get("needs_research") and not state.get("facts") and (state.get("research_rounds") or 0) == 0:
        return "researcher"
    return "writer"


@node("researcher", "Расследователь ищет фактуру")
async def researcher(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    session = agent_tools.ResearchSession(channel_id=ctx["channel_id"])
    tools = [
        agent_tools.past_posts_tool(session),
        agent_tools.web_search_tool(session),
        agent_tools.read_page_tool(session),
        agent_tools.calculate_tool(session),
    ]
    questions = state.get("research_questions") or []
    task = (
        "Ответь на вопросы Писателя:\n" + "\n".join(f"- {q}" for q in questions)
        if questions
        else "Собери фактуру для поста по заданию: конкретные факты, цифры, примеры, которые докажут ключевую мысль и помогут читателю."
    )
    known = facts_text(state.get("facts") or [])
    user = join_blocks(
        f"Сегодня {ctx['today']}.",
        block("ЗАДАНИЕ", _brief_block(brief)),
        block("УЖЕ ИЗВЕСТНЫЕ ФАКТЫ", known),
        task,
    )
    system = await system_prompt(ctx, "researcher")
    report = await run_agent(
        "researcher",
        system,
        user,
        tools,
        ResearchReport,
        final_name="report",
        final_description="Итог: проверенные факты с дословными цитатами и вопросы без ответа",
        max_steps=8,
        label="Поиск фактуры",
    )
    accepted, rejected = [], []
    calc_outputs = [c["output"] + " " + c["code"] for c in session.calculations]
    existing = {f["claim"] for f in state.get("facts") or []}
    for fact in report.facts:
        d = fact.model_dump()
        if fact.claim in existing:
            continue
        if fact.source_url.strip().lower() == "calculate":
            quote_numbers = {v for _, v in numbers_in(fact.quote)}
            calc_numbers = {v for c in calc_outputs for _, v in numbers_in(c)}
            ok = quote_in(fact.quote, calc_outputs) or bool(quote_numbers) and quote_numbers <= calc_numbers
        else:
            page = session.pages.get(fact.source_url)
            ok = page is not None and quote_in(fact.quote, [page])
        if ok:
            d["origin"] = "research"
            accepted.append(d)
        else:
            rejected.append({**d, "reason": "цитата не найдена на прочитанной странице"})
    for r in rejected:
        await emit("fact_rejected", {"claim": r["claim"], "source_url": r["source_url"], "reason": r["reason"]})
    await output("research", {"facts": accepted, "rejected": len(rejected), "not_found": report.not_found, "pages": list(session.pages), "calculations": session.calculations})
    past = list({p["id"]: p for p in (state.get("past_posts") or []) + session.past_posts}.values())
    sources = list(state.get("sources") or [])
    return {
        "facts": (state.get("facts") or []) + accepted,
        "not_found": (state.get("not_found") or []) + report.not_found,
        "calculations": (state.get("calculations") or []) + session.calculations,
        "past_posts": past,
        "research_rounds": (state.get("research_rounds") or 0) + 1,
        "research_questions": [],
        "sources": sources,
    }


def route_after_research(state: PostState) -> str:
    brief = state.get("brief") or {}
    if not state.get("goal_checked") and brief.get("key_idea"):
        return "goal_check"
    return "writer"


@node("goal_check", "Фактчекер сверяет задачу поста с фактами")
async def goal_check(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = dict(state["brief"])
    facts = state.get("facts") or []
    if not facts:
        if brief.get("needs_research"):
            await output("goal_check", {"status": "unsupported", "comment": "Расследователь не нашёл фактуры"})
            return {"goal_checked": True, "outcome": "slot_return", "outcome_reason": "Не нашлось фактов для этой темы: тема возвращена Стратегу"}
        return {"goal_checked": True}
    system = await system_prompt(ctx, "factchecker", "goal")
    user = join_blocks(block("ЗАДАНИЕ", _brief_block(brief)), block("ФАКТЫ", facts_text(facts) + "\n" + calculations_text(state.get("calculations") or [])))
    answer = await ask("factchecker", system, user, GoalCheckAnswer, label="Проверка задачи по фактам")
    await output("goal_check", answer.model_dump())
    if answer.status == "narrow" and answer.adjusted_key_idea:
        brief["key_idea"] = answer.adjusted_key_idea
        brief["note"] = "Ключевая мысль сужена по фактам: " + answer.comment
    elif answer.status == "unsupported":
        brief["key_idea"] = ""
        brief["note"] = "Исходная мысль не подтвердилась фактами. Найди мысль, которую факты подтверждают, и пиши её. " + answer.comment
    return {"goal_checked": True, "brief": brief}


def route_after_goal(state: PostState) -> str:
    return END if state.get("outcome") == "slot_return" else "writer"


def _remarks(state: PostState) -> str:
    review = state.get("review") or {}
    lines = []
    for r in review.get("merged", []):
        tag = "[обязательно]" if r.get("critical") else "[подсказка]"
        frag = f" Фрагмент: «{r['fragment']}»." if r.get("fragment") else ""
        lines.append(f"{tag} {r['issue']}. {r.get('suggestion', '')}{frag}".strip())
    return "\n".join(lines)


def _voice_block(ctx: dict) -> str:
    ex = ctx.get("voice_examples") or []
    return "\n\n---\n\n".join(((e.get("title") + "\n") if e.get("title") else "") + e["text"][:1500] for e in ex[:4])


@node("writer", "Писатель пишет пост")
async def writer(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    fmt = brief.get("format", "text")
    schema = DRAFT_SCHEMAS[fmt]
    session = agent_tools.ResearchSession(channel_id=ctx["channel_id"])
    news = brief.get("mode") == "news"
    source = brief.get("source") or {}
    source_texts = "\n\n".join(s["text"][:6000] for s in state.get("sources") or [])
    unconfirmed = "\n".join(f"- {c}" for c in brief.get("unconfirmed_claims") or [])
    past = "\n".join(f"- {p['date']} «{p['title']}» {p.get('url') or ''}" for p in state.get("past_posts") or [])
    draft = state.get("draft")
    previous = render.draft_text(draft, fmt) if draft and (state.get("review") or state.get("owner_feedback")) else ""
    forced = "Новых фактов не будет: напиши лучший пост по тому, что есть, без need_facts." if state.get("writer_forced") else ""
    user = join_blocks(
        f"Сегодня {ctx['today']}.",
        block("ЗАДАНИЕ", _brief_block(brief)),
        block("ИНФОПОВОД", f"{brief.get('topic', '')}\nИсточник: {source.get('url', '')}") if news and source else "",
        block("ТЕКСТ ИСТОЧНИКА", source_texts) if news else "",
        block("ФАКТЫ ОТ РАССЛЕДОВАТЕЛЯ", facts_text(state.get("facts") or [])),
        block("ВЫЧИСЛЕНИЯ", calculations_text(state.get("calculations") or [])),
        block("ФАКТЧЕКЕР НЕ ПОДТВЕРДИЛ", unconfirmed) if news else "",
        block("ПОЗИЦИЯ КАНАЛА", brief.get("channel_position") or ""),
        block("НАШИ ПРОШЛЫЕ ПОСТЫ", past),
        block("ПРИМЕРЫ ГОЛОСА КАНАЛА (манера, не содержание)", _voice_block(ctx)),
        block("ПРЕДЫДУЩИЙ ВАРИАНТ", previous),
        block("ЗАМЕЧАНИЯ РЕДАКТОРА", _remarks(state)),
        block("КОММЕНТАРИЙ ВЛАДЕЛЬЦА КАНАЛА", state.get("owner_feedback") or ""),
        forced,
    )
    system = await system_prompt(ctx, "writer", "main", fmt)
    answer = await run_agent(
        "writer",
        system,
        user,
        [agent_tools.calculate_tool(session)],
        schema,
        final_name="answer",
        final_description="Готовый пост строго по схеме",
        max_steps=4,
        live_field="intro" if fmt == "poll" else "text",
        label="Текст поста",
    )
    d = answer.model_dump()
    attempts = (state.get("write_attempts") or 0) + 1
    await output("draft", {"attempt": attempts, "format": fmt, **d})
    update = {
        "draft": d,
        "write_attempts": attempts,
        "calculations": (state.get("calculations") or []) + session.calculations,
    }
    if answer.need_facts:
        update["research_questions"] = answer.questions
    return update


def route_after_writer(state: PostState) -> str:
    draft = state.get("draft") or {}
    if draft.get("need_facts"):
        if (state.get("research_rounds") or 0) < MAX_RESEARCH_ROUNDS:
            return "researcher"
        if not state.get("writer_forced"):
            return "force_writer"
        return "no_facts"
    return "auto_checks"


@node("force_writer", "Писать по имеющимся фактам")
async def force_writer(state: PostState) -> dict:
    return {"writer_forced": True}


@node("no_facts", "Фактуры не хватило для поста")
async def no_facts(state: PostState) -> dict:
    return {"outcome": "needs_attention", "outcome_reason": "Писателю не хватило фактов даже после дополнительного поиска"}


@node("auto_checks", "Проверки кодом: штампы, стайлгайд, числа, ссылки")
async def run_auto_checks(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    fmt = brief.get("format", "text")
    draft = state["draft"]
    sg = Styleguide.model_validate(ctx.get("styleguide") or {})
    title, text = render.draft_title_text(draft, fmt)
    allowed = allowed_urls(state)
    issues = auto_checks(
        title=title,
        text=text,
        fmt=fmt,
        mode=brief.get("mode", "smm"),
        styleguide=sg,
        materials=materials(state),
        allowed_urls=allowed,
        extra_stamps=ctx.get("extra_stamps"),
        whitelist=set(ctx.get("latin_whitelist") or []),
    )
    data = [i.to_dict() for i in issues]
    if fmt == "digest":
        for item in draft.get("items") or []:
            if item.get("url") and item["url"] not in allowed:
                data.append({"code": "links", "message": f"Адрес пункта «{item['name']}» не из фактов", "fragment": item["url"], "critical": True, "suggestion": "Используй только адреса из блока ФАКТЫ."})
    if fmt == "poll":
        if len(draft.get("options") or []) < 2:
            data.append({"code": "poll", "message": "В опросе меньше двух вариантов", "fragment": "", "critical": True, "suggestion": "Дай 2–10 вариантов."})
    await output("auto_checks", {"issues": data, "critical": sum(1 for i in data if i["critical"])})
    return {"auto_issues": data}


@node("editor", "Редактор проверяет пост")
async def editor(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    fmt = brief.get("format", "text")
    draft = state["draft"]
    news = brief.get("mode") == "news"
    history = state.get("review_history") or []
    prev = "\n".join(f"- {'[критично] ' if r.get('critical') else ''}{r['issue']}" for r in (history[-1]["merged"] if history else []))
    checks = "\n".join(f"- {'[критично] ' if i['critical'] else ''}{i['message']}" + (f" («{i['fragment']}»)" if i.get("fragment") else "") for i in state.get("auto_issues") or [])
    user = join_blocks(
        block("ЗАДАНИЕ", _brief_block(brief)),
        block("ПОСТ", render.draft_text(draft, fmt)),
        block("КЛЮЧЕВАЯ МЫСЛЬ ПО ЗАМЫСЛУ АВТОРА", draft.get("key_idea", "")),
        block("ФАКТЫ", facts_text(state.get("facts") or []) + ("\n" + calculations_text(state.get("calculations") or []) if state.get("calculations") else "")),
        block("ТЕКСТ ИСТОЧНИКА", "\n\n".join(s["text"][:6000] for s in state.get("sources") or [])) if news else "",
        block("НЕ ПОДТВЕРЖДЕНО ФАКТЧЕКЕРОМ", "\n".join(f"- {c}" for c in brief.get("unconfirmed_claims") or [])) if news else "",
        block("ПОЗИЦИЯ КАНАЛА", brief.get("channel_position") or ""),
        block("ПРОВЕРКИ", checks),
        block("ПРОШЛЫЕ ЗАМЕЧАНИЯ", prev),
    )
    system = await system_prompt(ctx, "editor", "main", fmt)
    review = await ask("editor", system, user, Review, label="Редактура")
    merged = [
        {"issue": i["message"], "suggestion": i.get("suggestion", ""), "fragment": i.get("fragment", ""), "critical": i["critical"], "origin": "auto"}
        for i in state.get("auto_issues") or []
    ]
    merged += [{**r.model_dump(), "origin": "editor"} for r in review.recommendations[:5]]
    if not review.complete and not any(r["critical"] for r in merged):
        merged.append({"issue": "Пост не законченный", "suggestion": "Добавь вывод для читателя и закрой мысль.", "fragment": "", "critical": True, "origin": "editor"})
    if not review.main_idea.strip() and not any(r["critical"] for r in merged):
        merged.append({"issue": "Редактор не смог сформулировать главную мысль", "suggestion": "Сделай одну ключевую мысль явной.", "fragment": "", "critical": True, "origin": "editor"})
    record = {"main_idea": review.main_idea, "complete": review.complete, "merged": merged, "attempt": state.get("write_attempts") or 1}
    critical = sum(1 for r in merged if r["critical"])
    await output("review", {**record, "critical": critical})
    return {"review": record, "review_history": history + [record]}


def route_after_editor(state: PostState) -> str:
    review = state.get("review") or {}
    critical = any(r["critical"] for r in review.get("merged", []))
    if not critical:
        return "publisher"
    max_attempts = state["ctx"]["options"].get("max_review_attempts", 3)
    if (state.get("write_attempts") or 0) < max_attempts:
        return "writer"
    return "review_failed"


@node("review_failed", "Лимит доработок исчерпан: пост пойдёт владельцу с замечаниями")
async def review_failed(state: PostState) -> dict:
    review = state.get("review") or {}
    issues = [{"issue": r["issue"], "suggestion": r.get("suggestion", ""), "fragment": r.get("fragment", "")} for r in review.get("merged", []) if r["critical"]]
    reason = "После доработок остались критичные замечания: " + "; ".join(i["issue"] for i in issues[:3])
    return {"attention": {"reason": reason, "issues": issues}}


@node("publisher", "Издатель оформляет пост")
async def publisher(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    fmt = brief.get("format", "text")
    draft = state["draft"]
    sg = Styleguide.model_validate(ctx.get("styleguide") or {})
    if fmt != "text":
        formatted = render.format_non_text(draft, fmt, sg)
        await output("formatted", formatted)
        return {"formatted": formatted, "media": None}
    text = draft["text"]
    allowed = set(render.urls(text))
    system = await system_prompt(ctx, "publisher", "main", fmt)
    user = block("ТЕКСТ", text)
    answer = await ask("publisher", system, user, PublisherAnswer, label="Оформление")
    errors = check_publisher(answer.body_html, text, allowed_urls=allowed, emoji_max=sg.structured.emoji_max)
    if errors:
        await emit("publisher_retry", {"errors": errors})
        history = [
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(answer.model_dump(), ensure_ascii=False)},
        ]
        answer = await ask(
            "publisher",
            system,
            "Оформление нарушает правила: " + "; ".join(errors) + ". Исправь только эти ошибки, не меняя ни одного слова текста. Остальное оформление — эмодзи, жирный, цитаты — сохрани.",
            PublisherAnswer,
            label="Оформление (повтор)",
            history=history,
        )
        errors = check_publisher(answer.body_html, text, allowed_urls=allowed, emoji_max=sg.structured.emoji_max)
    body = answer.body_html if not errors else safe_html(text)
    chart = answer.chart.model_dump() if answer.chart and answer.image_kind == "chart" else None
    if chart and check_numbers(" ".join(str(v) for v in chart["values"]), materials(state)):
        chart = None
    formatted = {
        "html": render.compose_html(draft.get("title", ""), body, sg, main_source_url(state)),
        "body_html": body,
        "fallback": bool(errors),
        "image_kind": "chart" if chart else answer.image_kind if answer.image_kind != "chart" else "none",
        "image_query": answer.image_query,
        "chart": chart,
    }
    await output("formatted", {k: v for k, v in formatted.items() if k != "body_html"})
    return {"formatted": formatted}


@node("media", "Подбор картинки или построение графика")
async def make_media(state: PostState) -> dict:
    ctx = state["ctx"]
    formatted = state.get("formatted") or {}
    if not ctx["options"].get("images", True):
        return {"media": None}
    kind = formatted.get("image_kind")
    result = None
    if kind == "chart" and formatted.get("chart"):
        result = await media.chart(ctx["channel_id"], formatted["chart"])
    elif kind == "stock" and formatted.get("image_query"):
        result = await media.stock_photo(formatted["image_query"])
    await output("media", result or {"kind": "none"})
    return {"media": result}


def route_after_publisher(state: PostState) -> str:
    fmt = (state.get("brief") or {}).get("format", "text")
    return "media" if fmt == "text" else END


def build_production(channel_type: str):
    g = StateGraph(PostState)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_node("force_writer", force_writer)
    g.add_node("no_facts", no_facts)
    g.add_node("auto_checks", run_auto_checks)
    g.add_node("editor", editor)
    g.add_node("review_failed", review_failed)
    g.add_node("publisher", publisher)
    g.add_node("media", make_media)
    g.add_conditional_edges(START, route_entry, ["researcher", "writer"])
    if channel_type == ChannelType.smm:
        g.add_node("goal_check", goal_check)
        g.add_conditional_edges("researcher", route_after_research, ["goal_check", "writer"])
        g.add_conditional_edges("goal_check", route_after_goal, ["writer", END])
    else:
        g.add_edge("researcher", "writer")
    g.add_conditional_edges("writer", route_after_writer, ["researcher", "force_writer", "no_facts", "auto_checks"])
    g.add_edge("force_writer", "writer")
    g.add_edge("no_facts", END)
    g.add_edge("auto_checks", "editor")
    g.add_conditional_edges("editor", route_after_editor, ["publisher", "writer", "review_failed"])
    g.add_edge("review_failed", "publisher")
    g.add_conditional_edges("publisher", route_after_publisher, ["media", END])
    g.add_edge("media", END)
    return g.compile()
