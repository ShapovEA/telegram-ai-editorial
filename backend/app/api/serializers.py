from typing import Any

from app.db.models import AnalyticsReport, Channel, ChannelStory, Idea, Plan, Post, Run, RunEvent, Slot, Source, Story, User
from app.domain.schemas import Brief, ChannelOptions, NewsSchedule, SmmSchedule, Strategy, Styleguide


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "telegram_linked": bool(u.telegram_user_id), "telegram_username": u.telegram_username}


def channel_out(ch: Channel) -> dict[str, Any]:
    schedule_model = NewsSchedule if ch.type == "news" else SmmSchedule
    return {
        "id": ch.id,
        "type": ch.type,
        "title": ch.title,
        "status": ch.status,
        "publish_mode": ch.publish_mode,
        "telegram_username": ch.telegram_username,
        "telegram_title": ch.telegram_title,
        "telegram_connected": bool(ch.telegram_chat_id),
        "brief": Brief.model_validate(ch.brief or {}).model_dump(),
        "styleguide": Styleguide.model_validate(ch.styleguide or {}).model_dump(),
        "strategy": Strategy.model_validate(ch.strategy).model_dump() if ch.strategy else None,
        "schedule": schedule_model.model_validate(ch.schedule or {}).model_dump(),
        "options": ChannelOptions.model_validate(ch.options or {}).model_dump(),
        "models": ch.models or {},
        "budget_month_usd": float(ch.budget_month_usd) if ch.budget_month_usd is not None else None,
        "created_at": iso(ch.created_at),
    }


def slot_out(s: Slot) -> dict[str, Any]:
    return {
        "id": s.id,
        "channel_id": s.channel_id,
        "plan_id": s.plan_id,
        "publish_at": iso(s.publish_at),
        "rubric": s.rubric,
        "format": s.format,
        "topic": s.topic,
        "reader_goal": s.reader_goal,
        "key_idea": s.key_idea,
        "channel_position": s.channel_position,
        "status": s.status,
        "locked": s.locked,
        "warnings": s.warnings or [],
        "comment": s.comment,
        "story_id": s.story_id,
        "idea_id": s.idea_id,
        "run_id": s.run_id,
        "post_id": s.post_id,
    }


def plan_out(p: Plan, slots: list[Slot]) -> dict[str, Any]:
    return {
        "id": p.id,
        "channel_id": p.channel_id,
        "week_start": p.week_start.isoformat(),
        "status": p.status,
        "summary": p.summary,
        "comment": p.comment,
        "auto_approve_at": iso(p.auto_approve_at),
        "approved_at": iso(p.approved_at),
        "run_id": p.run_id,
        "slots": [slot_out(s) for s in sorted(slots, key=lambda x: x.publish_at)],
    }


def post_out(p: Post, *, full: bool = False, cost: float | None = None, link: str | None = None) -> dict[str, Any]:
    data = {
        "id": p.id,
        "channel_id": p.channel_id,
        "slot_id": p.slot_id,
        "run_id": p.run_id,
        "format": p.format,
        "rubric": p.rubric,
        "title": p.title,
        "text": p.text if full else p.text[:400],
        "key_idea": p.key_idea,
        "status": p.status,
        "publish_at": iso(p.publish_at),
        "published_at": iso(p.published_at),
        "reactions_total": p.reactions_total,
        "rating": p.rating,
        "media": p.media or {},
        "synthetic": p.synthetic,
        "review_attempts": p.review_attempts,
        "created_at": iso(p.created_at),
        "cost": cost,
        "link": link,
    }
    if full:
        data |= {
            "body_html": p.body_html,
            "content": p.content or {},
            "reactions": p.reactions or {},
            "poll_results": p.poll_results or {},
            "rating_comment": p.rating_comment,
            "source_url": p.source_url,
            "writer_text": p.writer_text,
        }
    return data


def run_out(r: Run) -> dict[str, Any]:
    return {
        "id": r.id,
        "channel_id": r.channel_id,
        "kind": r.kind,
        "title": r.title,
        "status": r.status,
        "current_node": r.current_node,
        "current_label": r.current_label,
        "slot_id": r.slot_id,
        "post_id": r.post_id,
        "plan_id": r.plan_id,
        "waiting_for": r.waiting_for,
        "result": r.result or {},
        "error": r.error,
        "attempts": r.attempts,
        "next_attempt_at": iso(r.next_attempt_at),
        "cost_usd": float(r.cost_usd or 0),
        "created_at": iso(r.created_at),
        "started_at": iso(r.started_at),
        "finished_at": iso(r.finished_at),
    }


def event_out(e: RunEvent) -> dict[str, Any]:
    return {"seq": e.seq, "ts": iso(e.ts), "type": e.type, "node": e.node, "data": e.data}


def source_out(s: Source) -> dict[str, Any]:
    return {
        "id": s.id,
        "url": s.url,
        "title": s.title,
        "site_url": s.site_url,
        "status": s.status,
        "error": s.error,
        "last_fetched_at": iso(s.last_fetched_at),
        "last_success_at": iso(s.last_success_at),
        "last_item_at": iso(s.last_item_at),
        "items_total": s.items_total,
    }


def story_out(cs: ChannelStory, st: Story, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": cs.id,
        "story_id": st.id,
        "title": st.title,
        "status": cs.status,
        "reason": cs.reason,
        "priority": cs.priority,
        "relevance": round(cs.relevance, 3) if cs.relevance is not None else None,
        "score": cs.score,
        "score_reason": cs.score_reason,
        "item_count": st.item_count,
        "first_seen_at": iso(st.first_seen_at),
        "last_item_at": iso(st.last_item_at),
        "related_post_id": cs.related_post_id,
        "items": items or [],
    }


def idea_out(i: Idea) -> dict[str, Any]:
    return {
        "id": i.id,
        "rubric": i.rubric,
        "format": i.format,
        "topic": i.topic,
        "reader_goal": i.reader_goal,
        "origin": i.origin,
        "note": i.note,
        "vote": i.vote,
        "status": i.status,
        "created_at": iso(i.created_at),
    }


def report_out(r: AnalyticsReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "report": r.report,
        "proposal": r.proposal,
        "status": r.status,
        "run_id": r.run_id,
        "created_at": iso(r.created_at),
    }
