import logging
from datetime import UTC, datetime

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import update

from app.db.models import ChannelStory, Idea, LlmCall, Post, Slot
from app.db.session import session_scope
from app.domain.enums import ChannelType, IdeaStatus, PostStatus, SlotStatus, StoryStatus
from app.graphs.common import main_source_url, node, output
from app.graphs.context import build_ctx
from app.graphs.post import render
from app.graphs.post.news_head import build_news_head
from app.graphs.post.production import build_production
from app.graphs.post.smm_head import build_smm_head
from app.graphs.post.state import PostState
from app.runtime.context import current_run
from app.services.embeddings import EmbeddingError, embed_one
from app.services.posts_index import post_embedding_text

log = logging.getLogger(__name__)


def _slot_dict(slot: Slot) -> dict:
    return {
        "id": slot.id,
        "rubric": slot.rubric,
        "format": slot.format,
        "topic": slot.topic,
        "reader_goal": slot.reader_goal,
        "key_idea": slot.key_idea,
        "channel_position": slot.channel_position,
        "comment": slot.comment,
        "story_id": slot.story_id,
        "idea_id": slot.idea_id,
        "post_id": slot.post_id,
    }


@node("load_context", "Загрузка канала и слота")
async def load_context(state: PostState) -> dict:
    ctx = await build_ctx(state["channel_id"])
    async with session_scope() as s:
        slot = await s.get(Slot, state["slot_id"])
        if slot is None:
            raise ValueError(f"Слот {state['slot_id']} не найден")
        slot.status = SlotStatus.in_production
        slot.run_id = state["run_id"]
        slot_data = _slot_dict(slot)
    return {
        "ctx": ctx,
        "slot": slot_data,
        "facts": [],
        "calculations": [],
        "not_found": [],
        "past_posts": [],
        "research_rounds": 0,
        "write_attempts": 0,
        "owner_revisions": 0,
        "review_history": [],
        "rejected_story_ids": [],
        "outcome": None,
    }


def route_after_head(state: PostState) -> str:
    if state.get("outcome") or not state.get("brief"):
        return "finalize"
    return "production"


def route_after_production(state: PostState) -> str:
    return "finalize" if state.get("outcome") else "save_post"


@node("save_post", "Сохранение поста")
async def save_post(state: PostState) -> dict:
    ctx = state["ctx"]
    brief = state["brief"]
    fmt = brief.get("format", "text")
    draft = state["draft"]
    title, text = render.draft_title_text(draft, fmt)
    formatted = state["formatted"]
    content = {
        "draft": draft,
        "brief": brief,
        "facts": state.get("facts") or [],
        "calculations": state.get("calculations") or [],
        "poll": formatted.get("poll"),
        "attention": state.get("attention"),
    }
    vector = None
    try:
        vector = await embed_one(post_embedding_text(title or brief.get("topic", ""), draft.get("key_idea", ""), text))
    except EmbeddingError:
        log.warning("post embedding skipped")
    async with session_scope() as s:
        slot = await s.get(Slot, state["slot_id"])
        post = await s.get(Post, state["post_id"]) if state.get("post_id") else None
        if post is None:
            post = Post(channel_id=ctx["channel_id"], slot_id=state["slot_id"], run_id=state["run_id"])
            s.add(post)
        post.format = fmt
        post.rubric = brief.get("rubric")
        post.title = title
        post.text = text
        post.writer_text = text
        post.key_idea = draft.get("key_idea", "")
        post.body_html = formatted.get("html", "")
        post.content = content
        post.media = state.get("media") or {}
        post.source_url = main_source_url(state)
        post.status = PostStatus.draft
        post.review_attempts = state.get("write_attempts") or 0
        post.publish_at = slot.publish_at
        if vector is not None:
            post.embedding = vector
        await s.flush()
        post_id = post.id
        slot.post_id = post_id
        await s.execute(update(LlmCall).where(LlmCall.run_id == state["run_id"], LlmCall.post_id.is_(None)).values(post_id=post_id))
    current_run().post_id = post_id
    await output("post", {"post_id": post_id, "title": title})
    return {"post_id": post_id}


def route_delivery(state: PostState) -> str:
    if state.get("attention") or state["ctx"]["publish_mode"] != "autopilot":
        return "request_approval"
    return "schedule"


@node("request_approval", "Пост отправлен владельцу на одобрение")
async def request_approval(state: PostState) -> dict:
    post_id = state["post_id"]
    attention = state.get("attention")
    async with session_scope() as s:
        await s.execute(update(Post).where(Post.id == post_id).values(status=PostStatus.needs_attention if attention else PostStatus.awaiting_approval))
        slot = await s.get(Slot, state["slot_id"])
        slot.status = SlotStatus.needs_attention if attention else SlotStatus.awaiting_approval
        if attention:
            slot.warnings = [*(slot.warnings or []), {"code": "needs_attention", "message": attention["reason"]}]
    return {}


@node("await_approval", "Ожидание решения владельца")
async def await_approval(state: PostState) -> dict:
    decision = interrupt({"type": "post_approval", "post_id": state["post_id"]})
    return {"decision": decision if isinstance(decision, dict) else {"action": str(decision)}}


def route_after_approval(state: PostState) -> str:
    action = (state.get("decision") or {}).get("action")
    if action in ("approve", "edited"):
        return "schedule"
    if action == "revise":
        return "prepare_revision"
    return "finalize"


@node("prepare_revision", "Доработка по комментарию владельца")
async def prepare_revision(state: PostState) -> dict:
    decision = state.get("decision") or {}
    revisions = (state.get("owner_revisions") or 0) + 1
    return {
        "owner_feedback": decision.get("comment", ""),
        "owner_revisions": revisions,
        "write_attempts": 0,
        "review": None,
        "review_history": [],
        "writer_forced": False,
        "attention": None,
        "decision": None,
    }


@node("schedule", "Пост поставлен в расписание")
async def schedule(state: PostState) -> dict:
    async with session_scope() as s:
        slot = await s.get(Slot, state["slot_id"])
        publish_at = max(slot.publish_at, datetime.now(UTC))
        slot.status = SlotStatus.scheduled
        await s.execute(update(Post).where(Post.id == state["post_id"]).values(status=PostStatus.scheduled, publish_at=publish_at))
    await output("scheduled", {"publish_at": publish_at.isoformat()})
    return {"outcome": "scheduled"}


OUTCOME_SLOT = {
    "scheduled": SlotStatus.scheduled,
    "skipped": SlotStatus.skipped,
    "needs_attention": SlotStatus.needs_attention,
    "slot_return": SlotStatus.needs_attention,
    "rejected": SlotStatus.skipped,
    "not_approved": SlotStatus.not_approved,
}


@node("finalize", "Завершение")
async def finalize(state: PostState) -> dict:
    ctx = state["ctx"]
    outcome = state.get("outcome")
    reason = state.get("outcome_reason") or ""
    decision = (state.get("decision") or {}).get("action")
    if decision == "reject":
        outcome, reason = "rejected", "Отклонён владельцем"
    elif decision == "expire":
        outcome = "skipped" if ctx["type"] == "news" else "not_approved"
        reason = "Не одобрен к сроку публикации"
    outcome = outcome or "skipped"
    if outcome == "scheduled":
        return {"outcome": outcome}
    async with session_scope() as s:
        slot = await s.get(Slot, state["slot_id"])
        if slot is not None:
            slot.status = OUTCOME_SLOT.get(outcome, SlotStatus.skipped)
            if reason:
                slot.warnings = [*(slot.warnings or []), {"code": outcome, "message": reason}]
        if state.get("post_id"):
            await s.execute(update(Post).where(Post.id == state["post_id"]).values(status=PostStatus.rejected))
        brief = state.get("brief") or {}
        if ctx["type"] == "news" and state.get("chosen_story_id") and outcome != "needs_attention":
            await s.execute(
                update(ChannelStory)
                .where(ChannelStory.channel_id == ctx["channel_id"], ChannelStory.story_id == state["chosen_story_id"])
                .values(status=StoryStatus.rejected, reason=reason[:500])
            )
        if brief.get("idea_id") and outcome in ("skipped", "rejected"):
            await s.execute(update(Idea).where(Idea.id == brief["idea_id"]).values(status=IdeaStatus.new))
    await output("outcome", {"outcome": outcome, "reason": reason})
    return {"outcome": outcome, "outcome_reason": reason}


HEADS = {ChannelType.news: ("news_head", build_news_head), ChannelType.smm: ("smm_head", build_smm_head)}


def build_post_graph(channel_type: str, checkpointer=None):
    head, build_head = HEADS[channel_type]
    g = StateGraph(PostState)
    g.add_node("load_context", load_context)
    g.add_node(head, build_head())
    g.add_node("production", build_production(channel_type))
    g.add_node("save_post", save_post)
    g.add_node("request_approval", request_approval)
    g.add_node("await_approval", await_approval)
    g.add_node("prepare_revision", prepare_revision)
    g.add_node("schedule", schedule)
    g.add_node("finalize", finalize)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", head)
    g.add_conditional_edges(head, route_after_head, ["production", "finalize"])
    g.add_conditional_edges("production", route_after_production, ["save_post", "finalize"])
    g.add_conditional_edges("save_post", route_delivery, ["schedule", "request_approval"])
    g.add_edge("request_approval", "await_approval")
    g.add_conditional_edges("await_approval", route_after_approval, ["schedule", "prepare_revision", "finalize"])
    g.add_edge("prepare_revision", "production")
    g.add_edge("schedule", END)
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
