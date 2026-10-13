"""brief samples and per type fields

Revision ID: 2ac6065c9428
Revises: 7e1c348305f0
Create Date: 2026-10-12 22:35:31.938178

"""

from collections.abc import Sequence

from alembic import op

revision: str = "2ac6065c9428"
down_revision: str | Sequence[str] | None = "7e1c348305f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE channels
        SET brief = (brief - 'references' - 'topics') || jsonb_build_object('samples', COALESCE(brief -> 'references', '[]'::jsonb))
        WHERE brief ? 'references' OR brief ? 'topics'
        """
    )
    op.execute("UPDATE channels SET brief = brief - 'goal' - 'voice' - 'avoid' - 'positions' WHERE type = 'news'")
    op.execute(
        """
        UPDATE channels
        SET options = (options - 'reference_posts') || jsonb_build_object('sample_posts', options -> 'reference_posts')
        WHERE options ? 'reference_posts'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE channels
        SET brief = (brief - 'samples') || jsonb_build_object('references', COALESCE(brief -> 'samples', '[]'::jsonb))
        WHERE brief ? 'samples'
        """
    )
    op.execute(
        """
        UPDATE channels
        SET options = (options - 'sample_posts') || jsonb_build_object('reference_posts', options -> 'sample_posts')
        WHERE options ? 'sample_posts'
        """
    )
