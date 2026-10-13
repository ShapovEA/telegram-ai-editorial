import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.enums import (
    ChannelStatus,
    IdeaStatus,
    InjectionStatus,
    PostStatus,
    PublishMode,
    RunStatus,
    SlotStatus,
    SourceStatus,
    StoryStatus,
)

EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_link_code: Mapped[str | None] = mapped_column(String(64), unique=True)


class ServiceSettings(Base):
    __tablename__ = "service_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default=ChannelStatus.draft)
    publish_mode: Mapped[str] = mapped_column(String(16), default=PublishMode.approval)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_title: Mapped[str | None] = mapped_column(String(255))
    brief: Mapped[dict[str, Any]] = mapped_column(default=dict)
    styleguide: Mapped[dict[str, Any]] = mapped_column(default=dict)
    strategy: Mapped[dict[str, Any]] = mapped_column(default=dict)
    models: Mapped[dict[str, Any]] = mapped_column(default=dict)
    schedule: Mapped[dict[str, Any]] = mapped_column(default=dict)
    options: Mapped[dict[str, Any]] = mapped_column(default=dict)
    budget_month_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))


class ChannelDocVersion(Base):
    __tablename__ = "channel_doc_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column()
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelPromptVersion(Base):
    __tablename__ = "channel_prompt_versions"
    __table_args__ = (Index("ix_prompt_versions_lookup", "channel_id", "role", "key", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(32), default="main")
    text: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2000), unique=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    site_url: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), default=SourceStatus.new)
    error: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(String(300))
    modified: Mapped[str | None] = mapped_column(String(300))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_item_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_total: Mapped[int] = mapped_column(Integer, default=0)


class ChannelSource(Base):
    __tablename__ = "channel_sources"

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_item_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class FeedItem(Base):
    __tablename__ = "feed_items"
    __table_args__ = (
        Index("ix_feed_items_embedding", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    summary: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    injection_status: Mapped[str] = mapped_column(String(16), default=InjectionStatus.unchecked)
    injection_reason: Mapped[str | None] = mapped_column(Text)
    story_id: Mapped[int | None] = mapped_column(ForeignKey("stories.id", ondelete="SET NULL"), index=True)


class ChannelStory(Base):
    __tablename__ = "channel_stories"
    __table_args__ = (UniqueConstraint("channel_id", "story_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=StoryStatus.new)
    reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[bool] = mapped_column(Boolean, default=False)
    relevance: Mapped[float | None] = mapped_column()
    score: Mapped[int | None] = mapped_column(Integer)
    score_reason: Mapped[str | None] = mapped_column(Text)
    related_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    rubric: Mapped[str | None] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(16), default="text")
    topic: Mapped[str] = mapped_column(Text)
    reader_goal: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(32), default="strategy")
    note: Mapped[str] = mapped_column(Text, default="")
    vote: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=IdeaStatus.new)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("channel_id", "week_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    comment: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    auto_approve_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(String(36))


class Slot(TimestampMixin, Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rubric: Mapped[str | None] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(16), default="text")
    topic: Mapped[str] = mapped_column(Text, default="")
    reader_goal: Mapped[str] = mapped_column(Text, default="")
    key_idea: Mapped[str] = mapped_column(Text, default="")
    channel_position: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=SlotStatus.draft, index=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list[Any]] = mapped_column(default=list)
    comment: Mapped[str] = mapped_column(Text, default="")
    story_id: Mapped[int | None] = mapped_column(ForeignKey("stories.id", ondelete="SET NULL"))
    idea_id: Mapped[int | None] = mapped_column(ForeignKey("ideas.id", ondelete="SET NULL"))
    run_id: Mapped[str | None] = mapped_column(String(36))
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL", use_alter=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_embedding", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id", ondelete="SET NULL"))
    run_id: Mapped[str | None] = mapped_column(String(36))
    format: Mapped[str] = mapped_column(String(16), default="text")
    rubric: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    key_idea: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    media: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(24), default=PostStatus.draft, index=True)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_ids: Mapped[list[Any]] = mapped_column(default=list)
    telegram_poll_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reactions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    reactions_total: Mapped[int] = mapped_column(Integer, default=0)
    poll_results: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(Text)
    writer_text: Mapped[str] = mapped_column(Text, default="")
    review_attempts: Mapped[int] = mapped_column(Integer, default=0)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class PostEdit(Base):
    __tablename__ = "post_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    before: Mapped[str] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.queued, index=True)
    current_node: Mapped[str | None] = mapped_column(String(64))
    current_label: Mapped[str | None] = mapped_column(String(300))
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id", ondelete="SET NULL"))
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"))
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    waiting_for: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_seq", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    type: Mapped[str] = mapped_column(String(32))
    node: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"), index=True)
    node: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32), index=True)
    model_requested: Mapped[str] = mapped_column(String(200))
    model_used: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    generation_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ModelInfo(Base):
    __tablename__ = "model_catalog"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    context_length: Mapped[int] = mapped_column(Integer, default=0)
    prompt_price: Mapped[Decimal] = mapped_column(Numeric(18, 12), default=0)
    completion_price: Mapped[Decimal] = mapped_column(Numeric(18, 12), default=0)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    report: Mapped[dict[str, Any]] = mapped_column(default=dict)
    proposal: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    run_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    content_type: Mapped[str] = mapped_column(String(100))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
