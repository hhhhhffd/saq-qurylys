"""SAQ VISION: the finding status chosen with a review decision

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An ADD COLUMN is not an UPDATE, so the append-only trigger of vision_review does not fire.
    op.add_column("vision_review", sa.Column("status", sa.String(length=22), nullable=True))
    op.create_check_constraint(
        op.f("ck_vision_review_vision_review_status"),
        "vision_review",
        "status IN ('observed', 'possible_noncompliance', 'insufficient_evidence', 'not_applicable')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_vision_review_vision_review_status"), "vision_review", type_="check")
    op.drop_column("vision_review", "status")
