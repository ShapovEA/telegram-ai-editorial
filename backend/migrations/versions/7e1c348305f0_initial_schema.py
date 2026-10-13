"""initial schema

Revision ID: 7e1c348305f0
Revises:
Create Date: 2026-10-12 20:32:54.186563

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7e1c348305f0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "model_catalog",
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("prompt_price", sa.Numeric(precision=18, scale=12), nullable=False),
        sa.Column("completion_price", sa.Numeric(precision=18, scale=12), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("reasoning", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "service_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("site_url", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("etag", sa.String(length=300), nullable=True),
        sa.Column("modified", sa.String(length=300), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_item_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_item_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("telegram_link_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("telegram_link_code"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("publish_mode", sa.String(length=16), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("telegram_title", sa.String(length=255), nullable=True),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("styleguide", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strategy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("models", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("budget_month_usd", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_channels_owner_id"), "channels", ["owner_id"], unique=False)
    op.create_table(
        "feed_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("injection_status", sa.String(length=16), nullable=False),
        sa.Column("injection_reason", sa.Text(), nullable=True),
        sa.Column("story_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_hash"),
    )
    op.create_index(
        "ix_feed_items_embedding",
        "feed_items",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_feed_items_fetched_at"), "feed_items", ["fetched_at"], unique=False)
    op.create_index(op.f("ix_feed_items_published_at"), "feed_items", ["published_at"], unique=False)
    op.create_index(op.f("ix_feed_items_source_id"), "feed_items", ["source_id"], unique=False)
    op.create_index(op.f("ix_feed_items_story_id"), "feed_items", ["story_id"], unique=False)
    op.create_index(op.f("ix_feed_items_text_hash"), "feed_items", ["text_hash"], unique=False)
    op.create_index(op.f("ix_feed_items_title_hash"), "feed_items", ["title_hash"], unique=False)
    op.create_table(
        "analytics_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proposal", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_reports_channel_id"), "analytics_reports", ["channel_id"], unique=False)
    op.create_table(
        "channel_doc_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_channel_doc_versions_channel_id"), "channel_doc_versions", ["channel_id"], unique=False)
    op.create_table(
        "channel_prompt_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_versions_lookup", "channel_prompt_versions", ["channel_id", "role", "key", "version"], unique=False)
    op.create_table(
        "channel_sources",
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("channel_id", "source_id"),
    )
    op.create_table(
        "ideas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("rubric", sa.String(length=200), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("reader_goal", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("vote", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ideas_channel_id"), "ideas", ["channel_id"], unique=False)
    op.create_table(
        "media_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_files_channel_id"), "media_files", ["channel_id"], unique=False)
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("auto_approve_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "week_start"),
    )
    op.create_index(op.f("ix_plans_channel_id"), "plans", ["channel_id"], unique=False)
    op.create_table(
        "slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rubric", sa.String(length=200), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("reader_goal", sa.Text(), nullable=False),
        sa.Column("key_idea", sa.Text(), nullable=False),
        sa.Column("channel_position", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=True),
        sa.Column("idea_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL", use_alter=True),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_slots_channel_id"), "slots", ["channel_id"], unique=False)
    op.create_index(op.f("ix_slots_plan_id"), "slots", ["plan_id"], unique=False)
    op.create_index(op.f("ix_slots_publish_at"), "slots", ["publish_at"], unique=False)
    op.create_index(op.f("ix_slots_status"), "slots", ["status"], unique=False)
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("rubric", sa.String(length=200), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("key_idea", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("media", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("telegram_poll_id", sa.String(length=64), nullable=True),
        sa.Column("reactions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reactions_total", sa.Integer(), nullable=False),
        sa.Column("poll_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("rating_comment", sa.Text(), nullable=True),
        sa.Column("writer_text", sa.Text(), nullable=False),
        sa.Column("review_attempts", sa.Integer(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_posts_channel_id"), "posts", ["channel_id"], unique=False)
    op.create_index(
        "ix_posts_embedding",
        "posts",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_posts_publish_at"), "posts", ["publish_at"], unique=False)
    op.create_index(op.f("ix_posts_status"), "posts", ["status"], unique=False)
    op.create_index(op.f("ix_posts_telegram_poll_id"), "posts", ["telegram_poll_id"], unique=False)
    op.create_foreign_key("slots_post_id_fkey", "slots", "posts", ["post_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "channel_stories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.Boolean(), nullable=False),
        sa.Column("relevance", sa.Double(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("related_post_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "story_id"),
    )
    op.create_index(op.f("ix_channel_stories_channel_id"), "channel_stories", ["channel_id"], unique=False)
    op.create_index(op.f("ix_channel_stories_story_id"), "channel_stories", ["story_id"], unique=False)
    op.create_table(
        "post_edits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("before", sa.Text(), nullable=False),
        sa.Column("after", sa.Text(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_post_edits_channel_id"), "post_edits", ["channel_id"], unique=False)
    op.create_index(op.f("ix_post_edits_post_id"), "post_edits", ["post_id"], unique=False)
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_node", sa.String(length=64), nullable=True),
        sa.Column("current_label", sa.String(length=300), nullable=True),
        sa.Column("slot_id", sa.Integer(), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("waiting_for", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_channel_id"), "runs", ["channel_id"], unique=False)
    op.create_index(op.f("ix_runs_created_at"), "runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_runs_status"), "runs", ["status"], unique=False)
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("node", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("model_requested", sa.String(length=200), nullable=False),
        sa.Column("model_used", sa.String(length=200), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generation_id", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_calls_channel_id"), "llm_calls", ["channel_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_created_at"), "llm_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_calls_post_id"), "llm_calls", ["post_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_role"), "llm_calls", ["role"], unique=False)
    op.create_index(op.f("ix_llm_calls_run_id"), "llm_calls", ["run_id"], unique=False)
    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("node", sa.String(length=64), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_run_seq", "run_events", ["run_id", "seq"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_events_run_seq", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index(op.f("ix_llm_calls_run_id"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_role"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_post_id"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_created_at"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_channel_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_runs_status"), table_name="runs")
    op.drop_index(op.f("ix_runs_created_at"), table_name="runs")
    op.drop_index(op.f("ix_runs_channel_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_index(op.f("ix_post_edits_post_id"), table_name="post_edits")
    op.drop_index(op.f("ix_post_edits_channel_id"), table_name="post_edits")
    op.drop_table("post_edits")
    op.drop_index(op.f("ix_channel_stories_story_id"), table_name="channel_stories")
    op.drop_index(op.f("ix_channel_stories_channel_id"), table_name="channel_stories")
    op.drop_table("channel_stories")
    op.drop_constraint("slots_post_id_fkey", "slots", type_="foreignkey")
    op.drop_index(op.f("ix_posts_telegram_poll_id"), table_name="posts")
    op.drop_index(op.f("ix_posts_status"), table_name="posts")
    op.drop_index(op.f("ix_posts_publish_at"), table_name="posts")
    op.drop_index("ix_posts_embedding", table_name="posts", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})
    op.drop_index(op.f("ix_posts_channel_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_slots_status"), table_name="slots")
    op.drop_index(op.f("ix_slots_publish_at"), table_name="slots")
    op.drop_index(op.f("ix_slots_plan_id"), table_name="slots")
    op.drop_index(op.f("ix_slots_channel_id"), table_name="slots")
    op.drop_table("slots")
    op.drop_index(op.f("ix_plans_channel_id"), table_name="plans")
    op.drop_table("plans")
    op.drop_index(op.f("ix_media_files_channel_id"), table_name="media_files")
    op.drop_table("media_files")
    op.drop_index(op.f("ix_ideas_channel_id"), table_name="ideas")
    op.drop_table("ideas")
    op.drop_table("channel_sources")
    op.drop_index("ix_prompt_versions_lookup", table_name="channel_prompt_versions")
    op.drop_table("channel_prompt_versions")
    op.drop_index(op.f("ix_channel_doc_versions_channel_id"), table_name="channel_doc_versions")
    op.drop_table("channel_doc_versions")
    op.drop_index(op.f("ix_analytics_reports_channel_id"), table_name="analytics_reports")
    op.drop_table("analytics_reports")
    op.drop_index(op.f("ix_feed_items_title_hash"), table_name="feed_items")
    op.drop_index(op.f("ix_feed_items_text_hash"), table_name="feed_items")
    op.drop_index(op.f("ix_feed_items_story_id"), table_name="feed_items")
    op.drop_index(op.f("ix_feed_items_source_id"), table_name="feed_items")
    op.drop_index(op.f("ix_feed_items_published_at"), table_name="feed_items")
    op.drop_index(op.f("ix_feed_items_fetched_at"), table_name="feed_items")
    op.drop_index(
        "ix_feed_items_embedding", table_name="feed_items", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}
    )
    op.drop_table("feed_items")
    op.drop_index(op.f("ix_channels_owner_id"), table_name="channels")
    op.drop_table("channels")
    op.drop_table("users")
    op.drop_table("stories")
    op.drop_table("sources")
    op.drop_table("service_settings")
    op.drop_table("model_catalog")
