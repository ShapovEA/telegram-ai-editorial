"""channel title from telegram

Revision ID: b41d7c2e9a10
Revises: 2ac6065c9428
Create Date: 2026-10-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b41d7c2e9a10"
down_revision: str | Sequence[str] | None = "2ac6065c9428"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE channels SET title = telegram_title WHERE telegram_title IS NOT NULL AND telegram_title <> ''")
    op.drop_column("channels", "telegram_title")


def downgrade() -> None:
    op.add_column("channels", sa.Column("telegram_title", sa.String(length=255), nullable=True))
    op.execute("UPDATE channels SET telegram_title = title WHERE telegram_chat_id IS NOT NULL")
