"""Revocable access tokens: app_user.token_version

Every token carries the version; raising it (logout, new password, deactivation) revokes the tokens issued before.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("app_user", "token_version")
