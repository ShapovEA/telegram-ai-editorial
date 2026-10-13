from enum import StrEnum


class ChannelType(StrEnum):
    news = "news"
    smm = "smm"


class ChannelStatus(StrEnum):
    draft = "draft"
    onboarding = "onboarding"
    active = "active"
    paused = "paused"


class PublishMode(StrEnum):
    autopilot = "autopilot"
    approval = "approval"


class Role(StrEnum):
    account_manager = "account_manager"
    designer = "designer"
    strategist = "strategist"
    scout = "scout"
    chief = "chief"
    factchecker = "factchecker"
    researcher = "researcher"
    writer = "writer"
    editor = "editor"
    publisher = "publisher"
    analyst = "analyst"
    guard = "guard"
    novelty = "novelty"


class PostFormat(StrEnum):
    text = "text"
    poll = "poll"
    digest = "digest"


class SlotStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    in_production = "in_production"
    awaiting_approval = "awaiting_approval"
    scheduled = "scheduled"
    published = "published"
    skipped = "skipped"
    failed = "failed"
    deferred = "deferred"
    needs_attention = "needs_attention"
    not_approved = "not_approved"


class PostStatus(StrEnum):
    draft = "draft"
    awaiting_approval = "awaiting_approval"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"
    rejected = "rejected"
    needs_attention = "needs_attention"


AWAITING_DECISION = (PostStatus.awaiting_approval, PostStatus.needs_attention)


class RunKind(StrEnum):
    brief_check = "brief_check"
    onboarding = "onboarding"
    planning = "planning"
    post = "post"
    analytics = "analytics"
    prompt_test = "prompt_test"
    channel_rules = "channel_rules"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    done = "done"
    failed = "failed"
    deferred = "deferred"
    cancelled = "cancelled"


class StoryStatus(StrEnum):
    new = "new"
    in_work = "in_work"
    published = "published"
    rejected = "rejected"
    expired = "expired"
    hidden = "hidden"


class IdeaStatus(StrEnum):
    new = "new"
    planned = "planned"
    used = "used"
    rejected = "rejected"


class InjectionStatus(StrEnum):
    unchecked = "unchecked"
    clean = "clean"
    injection = "injection"


class SourceStatus(StrEnum):
    new = "new"
    ok = "ok"
    error = "error"
    stale = "stale"
