import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, update

from app.agents.schemas import ChiefAnswer, ChiefFixAnswer, FactcheckAnswer, ScoutAnswer
from app.db.models import ChannelStory, FeedItem, Idea, Slot, Story
from app.db.session import session_scope
from app.domain.enums import IdeaStatus, InjectionStatus, StoryStatus
from app.graphs.common import block, join_blocks, node, output, quote_in, system_prompt
from app.graphs.post.state import PostState
from app.llm.agent import ask
from app.security import injection
from app.services import feeds
from app.services.embeddings import EmbeddingError
from app.services.novelty import related_post_for_vector

MAX_STORIES = 12
MAX_CANDIDATES = 6
MAX_CHIEF_FIXES = 2


async def _with_items(s, rows) -> list[dict]:
    stories = []
    for cs, story in rows:
        items = (
            await s.execute(
                select(FeedItem)
                .where(FeedItem.story_id == story.id, FeedItem.injection_status != InjectionStatus.injection)
                .order_by(FeedItem.published_at.desc().nulls_last())
                .limit(5)
            )
        ).scalars().all()
        if not items:
            continue
        stories.append(
            {
                "story_id": story.id,
                "channel_story_id": cs.id,
                "title": story.title,
                "priority": cs.priority,
                "last_item_at": story.last_item_at.isoformat(),
                "embedding": list(story.embedding) if story.embedding is not None else None,
                "items": [
                    {
                        "id": it.id,
                        "url": it.url,
                        "title": it.title,
                        "summary": (it.summary or "")[:500],
                        "text": it.text or "",
                        "published_at": it.published_at.isoformat() if it.published_at else None,
                        "injection_status": it.injection_status,
                    }
                    for it in items
                ],
            }
        )
    return stories


async def _load_pool(channel_id: int, ttl_hours: int, exclude: list[int]) -> list[dict]:
    since = datetime.now(UTC) - timedelta(hours=ttl_hours)
    async with session_scope() as s:
        await s.execute(
            update(ChannelStory)
            .where(ChannelStory.channel_id == channel_id, ChannelStory.status == StoryStatus.new)
            .where(ChannelStory.story_id.in_(select(Story.id).where(Story.last_item_at < since)))
            .values(status=StoryStatus.expired, reason="Сюжет устарел")
        )
        rows = (
            await s.execute(
                select(ChannelStory, Story)
                .join(Story, Story.id == ChannelStory.story_id)
                .where(ChannelStory.channel_id == channel_id, ChannelStory.status == StoryStatus.new, Story.last_item_at >= since)
                .where(ChannelStory.story_id.not_in(exclude or [-1]))
                .order_by(ChannelStory.priority.desc(), ChannelStory.relevance.desc().nulls_last(), Story.last_item_at.desc())
                .limit(MAX_STORIES)
            )
        ).all()
        return await _with_items(s, rows)


async def _load_story(channel_id: int, story_id: int) -> list[dict]:
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(ChannelStory, Story).join(Story, Story.id == ChannelStory.story_id).where(ChannelStory.channel_id == channel_id, ChannelStory.story_id == story_id)
            )
        ).all()
        return await _with_items(s, rows)


async def _guard_items(stories: list[dict]) -> list[dict]:
    clean_stories = []
    for st in stories:
        kept = []
        for it in st["items"]:
            if it["injection_status"] == InjectionStatus.unchecked:
                verdict = await injection.check((it["title"] + "\n" + (it["text"] or it["summary"]))[:8000], source=it["url"])
                status = InjectionStatus.injection if verdict.injection else InjectionStatus.clean
                async with session_scope() as s:
                    await s.execute(update(FeedItem).where(FeedItem.id == it["id"]).values(injection_status=status, injection_reason=verdict.reason or None))
                it["injection_status"] = status
            if it["injection_status"] == InjectionStatus.clean:
                kept.append(it)
        if kept:
            st["items"] = kept
            clean_stories.append(st)
        else:
            async with session_scope() as s:
                await s.execute(update(ChannelStory).where(ChannelStory.id == st["channel_story_id"]).values(status=StoryStatus.rejected, reason="Все материалы сюжета отброшены как попытка инъекции"))
    return clean_stories


@node("refresh_feeds", "Обновление RSS-лент канала")
async def refresh_feeds(state: PostState) -> dict:
    ids = await feeds.due_sources(channel_id=state["ctx"]["channel_id"])
    results = [await feeds.fetch_source(sid) for sid in ids]
    await output("feeds", {"refreshed": len(ids), "new": sum(r.get("new", 0) for r in results), "errors": [r["error"] for r in results if r.get("error")]})
    return {}


@node("pick_stories", "Отбор свежих сюжетов из RSS")
async def pick_stories(state: PostState) -> dict:
    ctx = state["ctx"]
    stories = await _load_pool(ctx["channel_id"], ctx["options"]["story_ttl_hours"], state.get("rejected_story_ids") or [])
    stories = await _guard_items(stories)
    await output("stories", {"count": len(stories), "titles": [s["title"] for s in stories]})
    return {"stories": stories}


@node("take_story", "Сюжет, выбранный владельцем")
async def take_story(state: PostState) -> dict:
    stories = await _guard_items(await _load_story(state["ctx"]["channel_id"], state["slot"]["story_id"]))
    await output("stories", {"count": len(stories), "titles": [s["title"] for s in stories]})
    return {"stories": stories}


def route_start(state: PostState) -> str:
    return "take_story" if state["slot"].get("story_id") else "refresh_feeds"


def _stories_block(stories: list[dict]) -> str:
    parts = []
    for i, st in enumerate(stories, 1):
        lines = [f"[{i}] {st['title']}" + (" (приоритет владельца)" if st.get("priority") else "")]
        for it in st["items"][:4]:
            lines.append(f"  - {it['title']} | {it['url']} | {it.get('published_at') or ''}\n    {(it['summary'] or it['text'])[:300]}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


@node("scout", "Скаут оценивает значимость сюжетов")
async def scout(state: PostState) -> dict:
    ctx = state["ctx"]
    stories = state["stories"]
    system = await system_prompt(ctx, "scout")
    user = join_blocks(
        f"Сегодня {ctx['today']}. Оцени значимость каждого сюжета для читателей канала.",
        block("СЮЖЕТЫ", _stories_block(stories)),
    )
    answer = await ask("scout", system, user, ScoutAnswer, label="Оценка значимости")
    by_index = {s.story: s for s in answer.scores if 1 <= s.story <= len(stories)}
    candidates = []
    async with session_scope() as s:
        for i, st in enumerate(stories, 1):
            sc = by_index.get(i)
            if not sc:
                continue
            await s.execute(update(ChannelStory).where(ChannelStory.id == st["channel_story_id"]).values(score=sc.significance, score_reason=sc.significance_reason))
            if sc.significance >= 3 or st.get("priority"):
                candidates.append({**st, "significance": sc.significance, "significance_reason": sc.significance_reason, "primary_source_url": sc.primary_source_url})
            else:
                await s.execute(update(ChannelStory).where(ChannelStory.id == st["channel_story_id"]).values(status=StoryStatus.rejected, reason=f"Низкая значимость ({sc.significance}): {sc.significance_reason}"))
    candidates.sort(key=lambda c: (c.get("priority", False), c["significance"]), reverse=True)
    candidates = candidates[:MAX_CANDIDATES]
    await output("scout", {"scores": [{"title": stories[s.story - 1]["title"], "significance": s.significance, "reason": s.significance_reason} for s in answer.scores if 1 <= s.story <= len(stories)]})
    return {"candidates": candidates}


def _candidates_block(cands: list[dict]) -> str:
    parts = []
    for i, c in enumerate(cands, 1):
        main = next((it for it in c["items"] if it["text"]), c["items"][0])
        excerpt = f"Текст источника (начало): {main['text'][:1500]}" if main["text"] else f"Анонс (полный текст статьи пока не получен): {main['summary']}"
        parts.append(f"[{i}] {c['title']}\nЗначимость: {c['significance']} — {c['significance_reason']}\nИсточник: {main['url']}\n{excerpt}")
    return "\n\n".join(parts)


def _recent_block(ctx: dict) -> str:
    return "\n".join(f"- {p['date']} «{p['title']}» ({p.get('rubric') or 'без рубрики'}, реакций: {p.get('reactions', 0)})" for p in ctx.get("recent_posts", [])[:20])


@node("chief", "Шеф-редактор выбирает тему и ставит задание")
async def chief(state: PostState) -> dict:
    ctx = state["ctx"]
    cands = state["candidates"]
    system = await system_prompt(ctx, "chief", "main")
    user = join_blocks(
        f"Сегодня {ctx['today']}.",
        block("КАНДИДАТЫ", _candidates_block(cands)),
        block("НАШИ ПРОШЛЫЕ ПОСТЫ", _recent_block(ctx)),
    )
    answer = await ask("chief", system, user, ChiefAnswer, label="Выбор темы")
    idx = answer.candidate if 1 <= answer.candidate <= len(cands) else 1
    chosen = cands[idx - 1]
    brief = {"topic": chosen["title"], "reader_goal": answer.reader_goal, "key_idea": answer.key_idea, "angle": answer.angle}
    await output("chief", {"story": chosen["title"], "reason": answer.reason, **brief})
    return {"chosen_story_id": chosen["story_id"], "brief": brief, "chief_attempts": 0}


async def _fill_missing_text(items: list[dict]) -> list[dict]:
    missing = [it for it in items if not it["text"]]
    texts = await asyncio.gather(*[feeds.article_text(it["url"]) for it in missing])
    fetched = {it["id"]: text for it, text in zip(missing, texts, strict=True) if text}
    kept = []
    for it in items:
        text = fetched.get(it["id"])
        if not text:
            kept.append(it)
            continue
        verdict = await injection.check((it["title"] + "\n" + text)[:8000], source=it["url"])
        if verdict.injection:
            values = {"injection_status": InjectionStatus.injection, "injection_reason": verdict.reason or None}
        else:
            values = {"text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()}
            kept.append({**it, "text": text})
        async with session_scope() as s:
            await s.execute(update(FeedItem).where(FeedItem.id == it["id"]).values(**values))
    return kept


@node("load_sources", "Загрузка текстов источников")
async def load_sources(state: PostState) -> dict:
    chosen = next(c for c in state["candidates"] if c["story_id"] == state["chosen_story_id"])
    items = await _fill_missing_text(chosen["items"])
    primary = chosen.get("primary_source_url") or ""
    readable = sorted((it for it in items if it["text"]), key=lambda it: it["url"] != primary)
    sources = [{"url": it["url"], "title": it["title"], "text": it["text"][:8000], "primary": i == 0} for i, it in enumerate(readable[:4])]
    await output(
        "sources",
        {
            "sources": [{"url": s["url"], "title": s["title"], "chars": len(s["text"])} for s in sources],
            "teaser_only": [it["url"] for it in items if not it["text"]],
        },
    )
    candidates = [{**c, "items": items} if c["story_id"] == chosen["story_id"] else c for c in state["candidates"]]
    return {"sources": sources, "candidates": candidates}


def route_after_load(state: PostState) -> str:
    return "factcheck" if state["sources"] else "reject_unreadable"


def _sources_block(sources: list[dict]) -> str:
    return "\n\n".join(f"{'[первоисточник] ' if s.get('primary') else ''}{s['title']}\n{s['url']}\n{s['text']}" for s in sources)


@node("factcheck", "Фактчекер проверяет задание по источникам")
async def factcheck(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    system = await system_prompt(ctx, "factchecker", "main")
    user = join_blocks(
        f"Сегодня {ctx['today']}.",
        block("ЗАДАНИЕ", f"Инфоповод: {brief['topic']}\nЦель для читателя: {brief['reader_goal']}\nКлючевая мысль: {brief['key_idea']}"),
        block("ТЕКСТ ИСТОЧНИКА", _sources_block(state["sources"])),
    )
    answer = await ask("factchecker", system, user, FactcheckAnswer, label="Проверка задания")
    texts = [s["text"] for s in state["sources"]]
    claims = []
    for c in answer.claims:
        d = c.model_dump()
        if c.status != "unsupported" and c.quote and not quote_in(c.quote, texts):
            d["status"] = "unsupported"
            d["note"] = "цитата не найдена в источнике"
        claims.append(d)
    key_status = answer.key_idea_status
    if key_status == "confirmed" and answer.key_idea_quote and not quote_in(answer.key_idea_quote, texts):
        key_status = "unsupported"
    report = {"claims": claims, "key_idea_status": key_status, "key_idea_quote": answer.key_idea_quote, "comment": answer.comment}
    await output("factcheck", report)
    return {"factcheck": report}


def route_after_factcheck(state: PostState) -> str:
    fc = state.get("factcheck") or {}
    if fc.get("key_idea_status") == "confirmed":
        return "build_news_brief"
    if (state.get("chief_attempts") or 0) < MAX_CHIEF_FIXES:
        return "chief_fix"
    return "reject_unconfirmed"


@node("chief_fix", "Шеф-редактор исправляет задание")
async def chief_fix(state: PostState) -> dict:
    ctx = state["ctx"]
    cands = state["candidates"]
    current = next(i for i, c in enumerate(cands, 1) if c["story_id"] == state["chosen_story_id"])
    fc = state["factcheck"]
    system = await system_prompt(ctx, "chief", "fix")
    report = "\n".join(f"- [{c['status']}] {c['claim']}" + (f" — «{c['quote']}»" if c.get("quote") else "") for c in fc["claims"])
    user = join_blocks(
        f"Текущий кандидат: [{current}].",
        block("ЗАДАНИЕ", f"Цель для читателя: {state['brief']['reader_goal']}\nКлючевая мысль: {state['brief']['key_idea']}"),
        block("ОТЧЁТ ФАКТЧЕКЕРА", f"Ключевая мысль: {fc['key_idea_status']}\n{fc.get('comment', '')}\n{report}"),
        block("КАНДИДАТЫ", _candidates_block(cands)),
    )
    answer = await ask("chief", system, user, ChiefFixAnswer, label="Исправление задания")
    idx = answer.candidate if 1 <= answer.candidate <= len(cands) else current
    chosen = cands[idx - 1]
    brief = {"topic": chosen["title"], "reader_goal": answer.reader_goal, "key_idea": answer.key_idea, "angle": state["brief"].get("angle", "")}
    await output("chief_fix", {"action": answer.action, "change_note": answer.change_note, "story": chosen["title"], **brief})
    return {"chosen_story_id": chosen["story_id"], "brief": brief, "chief_attempts": (state.get("chief_attempts") or 0) + 1}


@node("reject_unreadable", "Сюжет отброшен: нет полного текста")
async def reject_unreadable(state: PostState) -> dict:
    return await _reject(state, "Нет полного текста: в лентах только анонс, а страницы статей не открываются")


@node("reject_unconfirmed", "Сюжет отброшен: ключевая мысль не подтвердилась")
async def reject_unconfirmed(state: PostState) -> dict:
    return await _reject(state, "Фактчекер не подтвердил ключевую мысль: " + (state["factcheck"].get("comment") or "")[:500])


async def _reject(state: PostState, reason: str) -> dict:
    sid = state["chosen_story_id"]
    async with session_scope() as s:
        await s.execute(
            update(ChannelStory)
            .where(ChannelStory.channel_id == state["ctx"]["channel_id"], ChannelStory.story_id == sid)
            .values(status=StoryStatus.rejected, reason=reason)
        )
    title = next((c["title"] for c in state.get("candidates") or [] if c["story_id"] == sid), "")
    await output("rejected", {"story": title, "reason": reason})
    return {"rejected_story_ids": [*(state.get("rejected_story_ids") or []), sid], "brief": None, "factcheck": None}


@node("build_news_brief", "Задание на пост готово")
async def build_news_brief(state: PostState) -> dict:
    ctx = state["ctx"]
    chosen = next(c for c in state["candidates"] if c["story_id"] == state["chosen_story_id"])
    fc = state["factcheck"]
    primary = next((s for s in state["sources"] if s.get("primary")), state["sources"][0])
    facts = [
        {"claim": c["claim"], "quote": c["quote"], "source_url": primary["url"], "date": "", "origin": "factcheck"}
        for c in fc["claims"]
        if c["status"] == "confirmed" and c.get("quote")
    ]
    related = None
    if chosen.get("embedding"):
        try:
            related = await related_post_for_vector(ctx["channel_id"], chosen["embedding"], chosen["title"])
        except EmbeddingError:
            related = None
    brief = {
        **state["brief"],
        "mode": "news",
        "format": "text",
        "rubric": None,
        "needs_research": False,
        "source": {"url": primary["url"], "title": primary["title"]},
        "unconfirmed_claims": [c["claim"] for c in fc["claims"] if c["status"] != "confirmed"],
        "related_post": related,
        "channel_position": None,
    }
    async with session_scope() as s:
        await s.execute(update(ChannelStory).where(ChannelStory.channel_id == ctx["channel_id"], ChannelStory.story_id == chosen["story_id"]).values(status=StoryStatus.in_work))
        await s.execute(update(Slot).where(Slot.id == state["slot_id"]).values(story_id=chosen["story_id"], topic=chosen["title"], reader_goal=brief["reader_goal"], key_idea=brief["key_idea"]))
    await output("brief", brief)
    past = [related] if related else []
    return {"brief": brief, "facts": facts, "past_posts": past}


@node("no_story", "Подходящего сюжета нет")
async def no_story(state: PostState) -> dict:
    if state["slot"].get("story_id"):
        reason = "Выбранный сюжет не прошёл проверку, пост не написан"
    elif state["ctx"]["options"].get("empty_slot_policy") != "evergreen":
        reason = "Нет значимых сюжетов, слот пропущен по настройке канала"
    else:
        return {}
    return {"brief": None, "outcome": "skipped", "outcome_reason": reason}


def route_after_no_story(state: PostState) -> str:
    return END if state.get("outcome") else "evergreen"


@node("evergreen", "Берём тему из банка идей")
async def evergreen(state: PostState) -> dict:
    ctx = state["ctx"]
    async with session_scope() as s:
        idea = (
            await s.execute(
                select(Idea)
                .where(Idea.channel_id == ctx["channel_id"], Idea.status == IdeaStatus.new, Idea.vote >= 0)
                .order_by(Idea.vote.desc(), Idea.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if idea is None:
            return {"brief": None, "outcome": "skipped", "outcome_reason": "Нет значимых сюжетов и нет идей в банке"}
        idea.status = IdeaStatus.used
        await s.execute(update(Slot).where(Slot.id == state["slot_id"]).values(idea_id=idea.id, topic=idea.topic, rubric=idea.rubric, reader_goal=idea.reader_goal))
        brief = {
            "mode": "news",
            "format": idea.format or "text",
            "rubric": idea.rubric,
            "topic": idea.topic,
            "reader_goal": idea.reader_goal,
            "key_idea": "",
            "needs_research": True,
            "source": None,
            "unconfirmed_claims": [],
            "related_post": None,
            "channel_position": None,
            "evergreen": True,
            "idea_id": idea.id,
        }
    await output("brief", brief)
    return {"brief": brief}


def route_after_pick(state: PostState) -> str:
    return "scout" if state.get("stories") else "no_story"


def route_after_scout(state: PostState) -> str:
    return "chief" if state.get("candidates") else "no_story"


def route_after_reject(state: PostState) -> str:
    return "chief" if state.get("candidates") else "no_story"


def _filter_candidates(state: PostState) -> dict:
    rejected = set(state.get("rejected_story_ids") or [])
    return {"candidates": [c for c in state.get("candidates") or [] if c["story_id"] not in rejected]}


@node("drop_rejected", "Отсев отклонённых сюжетов")
async def drop_rejected(state: PostState) -> dict:
    return _filter_candidates(state)


def build_news_head():
    g = StateGraph(PostState)
    g.add_node("refresh_feeds", refresh_feeds)
    g.add_node("pick_stories", pick_stories)
    g.add_node("take_story", take_story)
    g.add_node("scout", scout)
    g.add_node("chief", chief)
    g.add_node("load_sources", load_sources)
    g.add_node("factcheck", factcheck)
    g.add_node("chief_fix", chief_fix)
    g.add_node("reject_unreadable", reject_unreadable)
    g.add_node("reject_unconfirmed", reject_unconfirmed)
    g.add_node("drop_rejected", drop_rejected)
    g.add_node("build_news_brief", build_news_brief)
    g.add_node("no_story", no_story)
    g.add_node("evergreen", evergreen)
    g.add_conditional_edges(START, route_start, ["take_story", "refresh_feeds"])
    g.add_edge("refresh_feeds", "pick_stories")
    g.add_conditional_edges("pick_stories", route_after_pick, ["scout", "no_story"])
    g.add_conditional_edges("take_story", route_after_pick, ["scout", "no_story"])
    g.add_conditional_edges("scout", route_after_scout, ["chief", "no_story"])
    g.add_edge("chief", "load_sources")
    g.add_conditional_edges("load_sources", route_after_load, ["factcheck", "reject_unreadable"])
    g.add_conditional_edges("factcheck", route_after_factcheck, ["build_news_brief", "chief_fix", "reject_unconfirmed"])
    g.add_edge("chief_fix", "load_sources")
    g.add_edge("reject_unreadable", "drop_rejected")
    g.add_edge("reject_unconfirmed", "drop_rejected")
    g.add_conditional_edges("drop_rejected", route_after_reject, ["chief", "no_story"])
    g.add_conditional_edges("no_story", route_after_no_story, ["evergreen", END])
    g.add_edge("build_news_brief", END)
    g.add_edge("evergreen", END)
    return g.compile()
