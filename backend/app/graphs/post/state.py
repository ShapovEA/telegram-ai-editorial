from typing import Any, TypedDict


class PostState(TypedDict, total=False):
    run_id: str
    channel_id: int
    slot_id: int
    ctx: dict[str, Any]
    slot: dict[str, Any]

    stories: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    chosen_story_id: int | None
    sources: list[dict[str, Any]]
    factcheck: dict[str, Any] | None
    chief_attempts: int
    rejected_story_ids: list[int]

    brief: dict[str, Any] | None

    facts: list[dict[str, Any]]
    not_found: list[str]
    calculations: list[dict[str, Any]]
    research_questions: list[str]
    research_rounds: int
    past_posts: list[dict[str, Any]]
    goal_checked: bool

    draft: dict[str, Any] | None
    write_attempts: int
    writer_forced: bool
    auto_issues: list[dict[str, Any]]
    review: dict[str, Any] | None
    review_history: list[dict[str, Any]]
    attention: dict[str, Any] | None
    owner_feedback: str | None
    owner_revisions: int

    formatted: dict[str, Any] | None
    media: dict[str, Any] | None
    post_id: int | None

    decision: dict[str, Any] | None

    outcome: str | None
    outcome_reason: str | None
