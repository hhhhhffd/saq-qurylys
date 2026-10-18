"""Add auditable ad triage state, separate from publication status.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ad_post",
        sa.Column("review_state", sa.String(length=10), server_default="unreviewed", nullable=False),
    )
    op.add_column("ad_post", sa.Column("reviewed_by", sa.BigInteger(), nullable=True))
    op.add_column("ad_post", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ad_post", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_ad_post_ad_review_state"),
        "ad_post",
        "review_state IN ('unreviewed', 'reviewed', 'deferred', 'irrelevant')",
    )
    op.create_foreign_key(op.f("fk_ad_post_reviewed_by_app_user"), "ad_post", "app_user", ["reviewed_by"], ["id"])
    op.create_index("ix_ad_post_territory_review_state", "ad_post", ["territory_id", "review_state"])
    op.create_index("ix_ad_post_source_account", "ad_post", ["source_account_id"])


def downgrade() -> None:
    op.drop_index("ix_ad_post_source_account", table_name="ad_post")
    op.drop_index("ix_ad_post_territory_review_state", table_name="ad_post")
    op.drop_constraint(op.f("fk_ad_post_reviewed_by_app_user"), "ad_post", type_="foreignkey")
    op.drop_constraint(op.f("ck_ad_post_ad_review_state"), "ad_post", type_="check")
    op.drop_column("ad_post", "review_note")
    op.drop_column("ad_post", "reviewed_at")
    op.drop_column("ad_post", "reviewed_by")
    op.drop_column("ad_post", "review_state")
