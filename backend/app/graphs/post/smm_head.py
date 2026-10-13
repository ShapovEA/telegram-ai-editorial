from langgraph.graph import END, START, StateGraph

from app.domain.schemas import Brief, Strategy
from app.graphs.common import node, output
from app.graphs.post.state import PostState


@node("load_slot", "Задание на пост из контент-плана")
async def load_slot(state: PostState) -> dict:
    ctx = state["ctx"]
    slot = state["slot"]
    strategy = Strategy.model_validate(ctx.get("strategy") or {}) if ctx.get("strategy") else Strategy()
    rubric = next((r for r in strategy.rubrics if r.name == slot.get("rubric")), None)
    position = slot.get("channel_position")
    if rubric and rubric.opinion and not position:
        position = Brief.model_validate(ctx.get("brief") or {}).positions or None
    brief = {
        "mode": "smm",
        "format": slot.get("format") or (rubric.format if rubric else "text"),
        "rubric": slot.get("rubric"),
        "topic": slot.get("topic", ""),
        "reader_goal": slot.get("reader_goal", ""),
        "key_idea": slot.get("key_idea", ""),
        "needs_research": rubric.needs_research if rubric else True,
        "source": None,
        "unconfirmed_claims": [],
        "related_post": None,
        "channel_position": position,
        "publish_at": slot["publish_at"],
        "note": f"Комментарий владельца к теме: {slot['comment']}" if slot.get("comment") else "",
    }
    await output("brief", brief)
    return {"brief": brief}


def build_smm_head():
    g = StateGraph(PostState)
    g.add_node("load_slot", load_slot)
    g.add_edge(START, "load_slot")
    g.add_edge("load_slot", END)
    return g.compile()
